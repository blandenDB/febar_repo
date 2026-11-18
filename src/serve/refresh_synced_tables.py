"""Refresh the Lakebase synced tables (SNAPSHOT mode) by starting each table's
pipeline and waiting for it. Prints a JSON summary as the last line."""
import argparse, json, time
from databricks.sdk import WorkspaceClient

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tables", required=True, help="comma-separated UC names of synced tables")
    a = ap.parse_args()
    w = WorkspaceClient()
    started = {}
    for t in a.tables.split(","):
        st = w.postgres.get_synced_table(name=f"synced_tables/{t}")
        pid = st.status.pipeline_id
        started[t] = (pid, w.pipelines.start_update(pipeline_id=pid).update_id)
    result = {}
    for t, (pid, uid) in started.items():
        while True:
            u = w.pipelines.get_update(pipeline_id=pid, update_id=uid).update
            if u.state.value in ("COMPLETED", "FAILED", "CANCELED"):
                break
            time.sleep(15)
        state = w.postgres.get_synced_table(name=f"synced_tables/{t}").status.detailed_state
        result[t.split(".")[-1]] = {"update": u.state.value, "synced_table_state": str(getattr(state, "value", state))}
    ok = all(r["update"] == "COMPLETED" for r in result.values())
    print(json.dumps({"step": "refresh_synced_tables", "status": "ok" if ok else "failed", "tables": result}))
    if not ok:
        raise SystemExit("synced table refresh failed")

if __name__ == "__main__":
    main()
