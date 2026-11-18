"""Run SQL against the Lakebase endpoint as the CLI user. The OAuth credential is
generated in memory through the Databricks SDK and never printed or stored.

Usage: .venv/bin/python tools/pg.py --profile febar "SELECT 1" | file.sql
"""
import argparse, os, sys
import psycopg
from databricks.sdk import WorkspaceClient

ENDPOINT = "projects/c360-serving/branches/production/endpoints/primary"


def connect(profile, dbname="c360"):
    w = WorkspaceClient(profile=profile)
    ep = w.postgres.get_endpoint(name=ENDPOINT)
    cred = w.postgres.generate_database_credential(endpoint=ENDPOINT)
    return psycopg.connect(host=ep.status.hosts.host, dbname=dbname, user=w.current_user.me().user_name,
                           password=cred.token, sslmode="require", autocommit=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("sql")
    a = ap.parse_args()
    sql = open(a.sql).read() if os.path.exists(a.sql) else a.sql
    with connect(a.profile) as conn, conn.cursor() as cur:
        cur.execute(sql)
        if cur.description:
            cols = [c.name for c in cur.description]
            print("\t".join(cols))
            for r in cur.fetchall():
                print("\t".join("NULL" if v is None else str(v) for v in r))


if __name__ == "__main__":
    main()
