"""Access test with a real non-admin identity (the service principal c360-access-tester).

The data owner (CLI user) sets the principal's entitlement; the principal then runs the
same queries as business_analyst, as relationship_banker (BR003, BR004) and with no
entitlement. A short-lived OAuth secret is created for the principal, used only in
memory, and deleted at the end. Nothing secret is printed or stored.

Usage: .venv/bin/python tools/access_test.py --profile febar > evidence/12_access_test.txt
"""

import argparse
import datetime as dt
import re
import time

import requests
from databricks.sdk import WorkspaceClient

FQ = "c360_bank.customer_lifetime_value"
SP_NAME = "c360-access-tester"
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@databricks\.com")

QUERIES = [
    ("who am I", "SELECT current_user() AS principal"),
    ("call the policy function directly (no EXECUTE grant)", "SELECT " + FQ + ".c360_current_persona() AS persona"),
    ("rows visible", f"""SELECT (SELECT COUNT(*) FROM {FQ}.gold_customer_360) AS customers,
        (SELECT CONCAT_WS(',', ARRAY_SORT(COLLECT_SET(home_branch_id))) FROM {FQ}.gold_customer_360) AS branches,
        (SELECT COUNT(*) FROM {FQ}.gold_product_holdings) AS holdings"""),
    ("sample rows", f"""SELECT customer_360_id, first_name, last_name, email, date_of_birth, age, home_branch_id
        FROM {FQ}.gold_customer_360 ORDER BY customer_360_id LIMIT 3"""),
    ("read silver PII (not granted)", f"SELECT COUNT(*) AS n FROM {FQ}.silver_core_customers"),
    ("read the entitlement table (not granted)", f"SELECT COUNT(*) AS n FROM {FQ}.c360_access_entitlements"),
    ("change own entitlement (not granted)",
     f"UPDATE {FQ}.c360_access_entitlements SET persona = 'data_owner' WHERE principal = current_user()"),
]


def run_sql(host, token, warehouse, sql):
    r = requests.post(f"{host}/api/2.0/sql/statements", headers={"Authorization": f"Bearer {token}"},
                      json={"warehouse_id": warehouse, "statement": sql, "wait_timeout": "50s"}, timeout=120)
    d = r.json()
    while d.get("status", {}).get("state") in ("PENDING", "RUNNING"):
        time.sleep(2)
        d = requests.get(f"{host}/api/2.0/sql/statements/{d['statement_id']}",
                         headers={"Authorization": f"Bearer {token}"}, timeout=60).json()
    return d


def fmt(d):
    st = d.get("status", {})
    if st.get("state") != "SUCCEEDED":
        msg = st.get("error", {}).get("message", str(d))
        return "DENIED/ERROR: " + msg.splitlines()[0][:220]
    cols = [c["name"] for c in d.get("manifest", {}).get("schema", {}).get("columns", [])]
    rows = [["NULL" if v is None else str(v) for v in r] for r in d.get("result", {}).get("data_array", []) or []]
    if not cols:
        return "OK"
    w = [max([len(c)] + [len(r[i]) for r in rows]) for i, c in enumerate(cols)]
    line = lambda vals: "  ".join(v.ljust(w[i]) for i, v in enumerate(vals))
    return "\n".join([line(cols), line(["-" * x for x in w])] + [line(r) for r in rows])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="", help="CLI profile; omit when running as a job task")
    ap.add_argument("--warehouse", default="7252b2dd64dc2427")
    a = ap.parse_args()
    w = WorkspaceClient(profile=a.profile) if a.profile else WorkspaceClient()
    host = w.config.host.rstrip("/")
    sp = next(iter(w.service_principals.list(filter=f'displayName eq "{SP_NAME}"')))
    app_id = sp.application_id
    owner_token = w.config.authenticate()["Authorization"].split(" ", 1)[1]  # in memory only

    def as_owner(sql):
        d = run_sql(host, owner_token, a.warehouse, sql)
        assert d["status"]["state"] == "SUCCEEDED", d["status"]
        return d

    is_admin = any(g.display == "admins" for g in (sp.groups or []))
    print('{"step": "access_test", "status": "starting"}')
    print("# Evidence 12: access test with a real non-admin identity")
    print(f"# Captured {dt.datetime.now(dt.timezone.utc):%Y-%m-%dT%H:%M:%SZ} by tools/access_test.py. Synthetic data; user identities redacted.")
    print(f"\nPrincipal: service principal '{SP_NAME}' (application ID {app_id}); workspace admin: {is_admin}; "
          f"workspace entitlements: {[e.value for e in (sp.entitlements or [])]}")
    print("UC grants: USE CATALOG c360_bank, USE SCHEMA customer_lifetime_value, SELECT on gold_customer_360 and "
          "gold_product_holdings only. SQL warehouse: CAN_USE. Entitlements are set by the data owner, not the principal.")

    secret = w.service_principal_secrets_proxy.create(service_principal_id=sp.id)
    try:
        tok = requests.post(f"{host}/oidc/v1/token", auth=(app_id, secret.secret),
                            data={"grant_type": "client_credentials", "scope": "all-apis"}, timeout=60).json()["access_token"]
        scenarios = [
            ("business_analyst", f"""MERGE INTO {FQ}.c360_access_entitlements t USING (SELECT '{app_id}' AS p) s ON t.principal = s.p
                 WHEN MATCHED THEN UPDATE SET persona = 'business_analyst', branch_ids = NULL, updated_at = current_timestamp()
                 WHEN NOT MATCHED THEN INSERT (principal, persona, branch_ids, updated_at)
                 VALUES (s.p, 'business_analyst', NULL, current_timestamp())"""),
            ("relationship_banker (BR003, BR004)", f"""UPDATE {FQ}.c360_access_entitlements
                 SET persona = 'relationship_banker', branch_ids = ARRAY('BR003', 'BR004'), updated_at = current_timestamp()
                 WHERE principal = '{app_id}'"""),
            ("no entitlement (row removed)", f"DELETE FROM {FQ}.c360_access_entitlements WHERE principal = '{app_id}'"),
        ]
        for label, setup in scenarios:
            as_owner(setup)
            print(f"\n==================== {label} ====================")
            for title, sql in QUERIES:
                print(f"\n## {title}")
                print(fmt(run_sql(host, tok, a.warehouse, sql)))
        print("\n==================== data owner check (expected banker count) ====================")
        print(fmt(as_owner(f"""SELECT home_branch_id, COUNT(*) AS customers FROM {FQ}.gold_customer_360
                              WHERE home_branch_id IN ('BR003', 'BR004') GROUP BY 1 ORDER BY 1""")))
    finally:
        as_owner(f"DELETE FROM {FQ}.c360_access_entitlements WHERE principal = '{app_id}'")
        w.service_principal_secrets_proxy.delete(service_principal_id=sp.id, secret_id=secret.id)
        print("\nCleanup: test entitlement removed; the principal's OAuth secret was deleted after the test.")


if __name__ == "__main__":
    import contextlib, io, sys
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main()
    sys.stdout.write(EMAIL.sub("<user>", buf.getvalue()))
