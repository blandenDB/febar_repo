"""Run SQL statements on the bundle's SQL warehouse and print results as text tables.

Used to verify each stage and capture text evidence. Auth comes from the Databricks
CLI profile (no tokens are read or printed here).

Usage:
  python3 tools/run_sql.py --profile febar --warehouse <id> file.sql [file2.sql ...]
Statements are separated by ';' at the end of a line. A line starting
with '-- title:' before a statement sets the heading printed above its result.
"""

import argparse
import json
import re
import subprocess
import sys


def run(profile, warehouse, sql):
    body = json.dumps({"warehouse_id": warehouse, "statement": sql, "wait_timeout": "50s",
                       "on_wait_timeout": "CONTINUE"})
    out = subprocess.run(["databricks", "api", "post", "/api/2.0/sql/statements", "--json", body,
                          "--profile", profile], capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    while d["status"]["state"] in ("PENDING", "RUNNING"):
        out = subprocess.run(["databricks", "api", "get", f"/api/2.0/sql/statements/{d['statement_id']}",
                              "--profile", profile], capture_output=True, text=True, check=True).stdout
        d = json.loads(out)
    return d


def table(d):
    if d["status"]["state"] != "SUCCEEDED":
        return f"ERROR: {d['status'].get('error', {}).get('message', d['status'])}"
    cols = [c["name"] for c in d.get("manifest", {}).get("schema", {}).get("columns", [])]
    if not cols:
        return "OK"
    rows = d.get("result", {}).get("data_array", []) or []
    rows = [["NULL" if v is None else str(v) for v in r] for r in rows]
    w = [max([len(c)] + [len(r[i]) for r in rows]) for i, c in enumerate(cols)]
    line = lambda vals: "  ".join(v.ljust(w[i]) for i, v in enumerate(vals))
    return "\n".join([line(cols), line(["-" * x for x in w])] + [line(r) for r in rows])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--warehouse", required=True)
    ap.add_argument("files", nargs="+")
    a = ap.parse_args()
    ok = True
    for f in a.files:
        chunks = re.split(r";[ \t]*(?:\n|$)", open(f).read())
        for chunk in chunks:
            lines = [l for l in chunk.strip().splitlines()]
            title = next((l[len("-- title:"):].strip() for l in lines if l.startswith("-- title:")), None)
            sql = "\n".join(l for l in lines if not l.startswith("-- title:")).strip()
            if not sql:
                continue
            d = run(a.profile, a.warehouse, sql)
            ok &= d["status"]["state"] == "SUCCEEDED"
            first = next((l for l in sql.splitlines() if l.strip() and not l.startswith("--")), sql)
            print(f"## {title or first[:100]}")
            print(table(d))
            print()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
