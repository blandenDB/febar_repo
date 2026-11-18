"""Apply src/serve/02_postgres_setup.sql to Lakebase, optionally grant the app's role,
and verify row-level access. Runs as the job owner; the OAuth credential is generated
in memory and never printed. Prints a JSON summary as the last line.

Verification uses a temporary Postgres role with exactly the app's grants, so the
checks show what a banker session (and someone outside the roster) can see.
"""

import argparse
import json
import os
import uuid

import psycopg
from psycopg import sql
from databricks.sdk import WorkspaceClient

APP_GRANTS = """
GRANT USAGE ON SCHEMA app TO {role};
GRANT SELECT ON app.my_branches, app.customers, app.holdings, app.recommendations TO {role};
GRANT SELECT, INSERT ON app.banker_feedback TO {role};
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="projects/c360-serving/branches/production/endpoints/primary")
    ap.add_argument("--database", default="c360")
    ap.add_argument("--sql-file", default="src/serve/02_postgres_setup.sql")
    ap.add_argument("--app-role", default="", help="Postgres role of the Databricks App service principal")
    a = ap.parse_args()

    w = WorkspaceClient()
    me = w.current_user.me().user_name
    ep = w.postgres.get_endpoint(name=a.endpoint)
    cred = w.postgres.generate_database_credential(endpoint=a.endpoint)
    summary = {"step": "postgres_setup", "status": "ok"}

    with psycopg.connect(host=ep.status.hosts.host, dbname=a.database, user=me, password=cred.token,
                         sslmode="require", autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(open(a.sql_file).read())
        if a.app_role:
            cur.execute(APP_GRANTS.format(role=sql.Identifier(a.app_role).as_string(conn)))
            summary["app_role_granted"] = True

        # Verify with a throwaway role that has exactly the app's grants.
        test_role = f"c360_rls_check_{uuid.uuid4().hex[:8]}"
        cur.execute(f"CREATE ROLE {test_role} NOLOGIN")
        cur.execute(f"GRANT {test_role} TO CURRENT_USER")
        cur.execute(APP_GRANTS.format(role=test_role))
        try:
            cur.execute("SELECT count(*) FROM customer_lifetime_value.pg_customer_360")
            total = cur.fetchone()[0]
            checks = {"synced_customers_total": total}
            cur.execute(f"SET ROLE {test_role}")
            for label, banker in [("roster_banker", me), ("not_in_roster", "someone.else@example.com"),
                                  ("no_identity_set", "")]:
                cur.execute("BEGIN")
                cur.execute("SELECT set_config('app.banker', %s, true)", (banker,))
                cur.execute("SELECT count(*), count(DISTINCT home_branch_id), "
                            "string_agg(DISTINCT home_branch_id, ',' ORDER BY home_branch_id) FROM app.customers")
                n, nb, br = cur.fetchone()
                cur.execute("SELECT count(*) FROM app.recommendations")
                nrec = cur.fetchone()[0]
                checks[label] = {"customers": n, "branches": br, "recommendations": nrec}
                cur.execute("ROLLBACK")
            # Direct access to synced base tables must be denied for the app's role.
            try:
                cur.execute("SELECT 1 FROM customer_lifetime_value.pg_customer_360 LIMIT 1")
                checks["base_table_access"] = "ALLOWED (unexpected)"
            except psycopg.errors.InsufficientPrivilege:
                checks["base_table_access"] = "denied"
            # Feedback RLS: insert for an own branch succeeds, another branch is rejected.
            cur.execute("BEGIN")
            cur.execute("SELECT set_config('app.banker', %s, true)", (me,))
            cur.execute("SELECT customer_360_id, home_branch_id FROM app.recommendations LIMIT 1")
            cid, br = cur.fetchone()
            cur.execute("INSERT INTO app.banker_feedback (customer_360_id, home_branch_id, product, action, note) "
                        "VALUES (%s, %s, 'test', 'follow_up', 'rls check (rolled back)')", (cid, br))
            checks["feedback_insert_own_branch"] = "allowed"
            cur.execute("SAVEPOINT s")
            try:
                cur.execute("INSERT INTO app.banker_feedback (customer_360_id, home_branch_id, product, action) "
                            "VALUES ('C0', 'BR025', 'test', 'follow_up')")
                checks["feedback_insert_other_branch"] = "ALLOWED (unexpected)"
            except psycopg.errors.InsufficientPrivilege:
                checks["feedback_insert_other_branch"] = "rejected by RLS"
                cur.execute("ROLLBACK TO SAVEPOINT s")
            cur.execute("ROLLBACK")
        finally:
            cur.execute("RESET ROLE")
            cur.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA app FROM {test_role}")
            cur.execute(f"REVOKE USAGE ON SCHEMA app FROM {test_role}")
            cur.execute(f"DROP ROLE {test_role}")

    ok = (checks["roster_banker"]["customers"] > 0 and checks["not_in_roster"]["customers"] == 0
          and checks["no_identity_set"]["customers"] == 0 and checks["base_table_access"] == "denied"
          and checks["feedback_insert_other_branch"] == "rejected by RLS")
    summary.update({"status": "ok" if ok else "failed", "checks": checks})
    out = json.dumps(summary).replace(me, "<roster banker>")
    print(out)
    if not ok:
        raise SystemExit("row-level access checks failed")


if __name__ == "__main__":
    main()
