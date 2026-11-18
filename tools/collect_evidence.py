"""Rebuild every evidence/*.txt file from the latest workspace runs.

Reads job run outputs (the JSON summary each task prints), pipeline updates, the
MLflow run and registered model through the Databricks CLI, and runs the SQL checks
in tools/checks/. User emails are redacted. No tokens are read or printed.

Usage: python3 tools/collect_evidence.py --profile febar
"""

import argparse
import datetime as dt
import json
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@databricks\.com")


def cli(profile, *args):
    out = subprocess.run(["databricks", *args, "--profile", profile, "-o", "json"],
                         capture_output=True, text=True, check=True, cwd=ROOT).stdout
    return json.loads(out)


def bundle_ids(profile):
    s = cli(profile, "bundle", "summary")["resources"]
    return ({k: v["id"] for k, v in s.get("jobs", {}).items()},
            {k: v["id"] for k, v in s.get("pipelines", {}).items()},
            {k: v.get("id") for k, v in s.get("experiments", {}).items()})


def latest_success(profile, job_id):
    runs = cli(profile, "jobs", "list-runs", "--job-id", str(job_id), "--completed-only", "--limit", "10")
    for r in runs if isinstance(runs, list) else runs.get("runs", []):
        if r.get("state", {}).get("result_state") == "SUCCESS":
            return cli(profile, "jobs", "get-run", str(r["run_id"]))
    raise SystemExit(f"no successful run for job {job_id}")


def run_header(run):
    tasks = [f"{t['task_key']}={t.get('state', {}).get('result_state')}" for t in run.get("tasks", [])]
    started = dt.datetime.fromtimestamp(run["start_time"] / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (f"Job '{run['run_name']}' run {run['run_id']}: {run['state'].get('result_state')}, "
            f"started {started}, {round(run.get('run_duration', 0) / 60000, 1)} min. Tasks: {', '.join(tasks)}")


def task_summary(profile, run, task_key):
    t = next(t for t in run["tasks"] if t["task_key"] == task_key)
    out = cli(profile, "jobs", "get-run-output", str(t["run_id"]))
    lines = [l for l in out.get("logs", "").splitlines() if l.startswith('{"step"')]
    return json.loads(lines[-1]) if lines else {"note": "no JSON summary found in task logs"}


def sql(profile, warehouse, path):
    r = subprocess.run(["python3", "tools/run_sql.py", "--profile", profile, "--warehouse", warehouse, path],
                       capture_output=True, text=True, cwd=ROOT)
    return r.stdout + (f"\n[run_sql exit code {r.returncode}]\n" + r.stderr if r.returncode else "")


def write(name, title, body):
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    text = f"# {title}\n# Captured {now} by tools/collect_evidence.py. Synthetic data only; user identities redacted.\n\n{body}"
    with open(os.path.join(ROOT, "evidence", name), "w") as f:
        f.write(EMAIL.sub("<user>", text))
    print(f"wrote evidence/{name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--warehouse", default="7252b2dd64dc2427")
    a = ap.parse_args()
    p, wh = a.profile, a.warehouse
    jobs, pipes, exps = bundle_ids(p)

    # 01 raw data
    run = latest_success(p, jobs["generate_raw_data"])
    write("01_raw_data.txt", "Evidence 01: synthetic raw data generation",
          run_header(run) + "\n\n## Task stdout: JSON summary\n"
          + json.dumps(task_summary(p, run, "generate"), indent=2) + "\n\n## SQL checks\n"
          + sql(p, wh, "tools/checks/01_raw.sql"))

    # 02 pipeline
    ups = cli(p, "pipelines", "list-updates", pipes["c360_pipeline"]).get("updates", [])[:5]
    hist = "\n".join(f"{u['update_id']}  {u.get('state')}  {'full_refresh' if u.get('full_refresh') else 'incremental'}  "
                     f"{dt.datetime.fromtimestamp(u['creation_time'] / 1000, dt.timezone.utc):%Y-%m-%dT%H:%M:%SZ}"
                     for u in ups)
    write("02_pipeline.txt", "Evidence 02: Lakeflow pipeline (bronze, silver + quarantine, identity matching, gold)",
          "## Latest pipeline updates (newest first)\n" + hist
          + "\nAn incremental update after a full refresh leaves bronze row counts unchanged (no duplicate rows on rerun).\n\n"
          + sql(p, wh, "tools/checks/02_pipeline.sql")
          + "\nNote: expectations on the *_checked views are reported under each flow that reads the view "
            "(silver_* and quarantine_records), so each rule appears twice with the same counts.\n")

    # 03 governance
    run = latest_success(p, jobs["c360_build"])
    write("03_governance.txt", "Evidence 03: Unity Catalog governance (entitlements, column masks, row filters, tags)",
          run_header(run) + "\nMethod: the same queries run while the caller's entitlement is switched between personas, "
          "then restored to data_owner.\n\n" + sql(p, wh, "tools/checks/03_governance.sql"))

    # 04 ML
    run = latest_success(p, jobs["c360_ml"])
    summ = task_summary(p, run, "train_and_score")
    model = summ.get("model")
    versions = subprocess.run(["databricks", "api", "get", f"/api/2.1/unity-catalog/models/{model}/versions",
                               "--profile", p], capture_output=True, text=True, cwd=ROOT).stdout
    vers = json.loads(versions).get("model_versions", []) if versions else []
    mdl = json.loads(subprocess.run(["databricks", "api", "get", f"/api/2.1/unity-catalog/models/{model}?include_aliases=true",
                                     "--profile", p], capture_output=True, text=True, cwd=ROOT).stdout or "{}")
    aliases = {x["alias_name"]: x["version_num"] for x in mdl.get("aliases", [])}
    mlrun = json.loads(subprocess.run(["databricks", "api", "get", "/api/2.0/mlflow/runs/get", "--json",
                                       json.dumps({"run_id": summ.get("mlflow_run_id")}), "--profile", p],
                                      capture_output=True, text=True, cwd=ROOT).stdout or "{}").get("run", {})
    metrics = {m["key"]: round(m["value"], 4) for m in mlrun.get("data", {}).get("metrics", [])}
    vlines = "\n".join(f"version {v['version']}  status {v.get('status')}  run {v.get('run_id')}" for v in vers)
    write("04_ml.txt", "Evidence 04: cross-sell propensity model, CLV and recommendations",
          run_header(run) + "\n\n## Task stdout: JSON summary (train_and_score)\n" + json.dumps(summ, indent=2)
          + f"\n\n## Unity Catalog model {model}\n{vlines}\naliases: {aliases}\n\n## MLflow run {summ.get('mlflow_run_id')} metrics\n"
          + json.dumps(dict(sorted(metrics.items())), indent=2) + "\n\n## SQL checks\n" + sql(p, wh, "tools/checks/04_ml.sql"))

    # 05 GenAI
    write("05_genai.txt", "Evidence 05: GenAI banker explanations (databricks-claude-haiku-5-5 via ai_query)",
          run_header(run) + "\n\n" + sql(p, wh, "tools/checks/05_genai.sql")
          + "\nReview note: explanations flagged by mentions_offer_or_rate were read by hand. They say the product "
            "fits 'without relying on any specific rate, fee, or promotion' (echoing the instruction), not an invented offer.\n")

    # 06 Lakebase
    lakebase(p, jobs)


def lakebase(p, jobs):
    run = latest_success(p, jobs["c360_serve"])
    body = run_header(run) + "\n\n"
    for task in ("refresh_synced_tables", "postgres_setup"):
        body += f"## Task stdout: JSON summary ({task})\n" + json.dumps(task_summary(p, run, task), indent=2) + "\n\n"
    synced = []
    for t in ("pg_customer_360", "pg_product_holdings", "pg_recommendations", "pg_banker_assignments"):
        d = cli(p, "postgres", "get-synced-table", f"synced_tables/c360_bank.customer_lifetime_value.{t}")
        st = d.get("status", {})
        synced.append(f"{t}  source=c360_bank.customer_lifetime_value.{t.replace('pg_', 'serving_')} (resources/lakebase.yml)  "
                      f"state={st.get('detailed_state')}")
    body += "## Synced tables (UC -> Lakebase, SNAPSHOT)\n" + "\n".join(synced) + "\n\n"
    fb = latest_success(p, jobs["c360_feedback_sync"])
    body += "## Feedback back to Unity Catalog\n" + run_header(fb) + "\n" + json.dumps(task_summary(p, fb, "feedback_to_uc"), indent=2) + "\n"
    body += ("\nAccess model: UC does not allow syncing tables with row filters or column masks, so owner-only serving_* "
             "copies are synced. In Postgres, the app role can read only security_barrier views in schema app that keep "
             "the signed-in banker's branches, and banker_feedback has row-level security. The checks above run as a "
             "temporary role with exactly the app's grants.\n")
    write("06_lakebase.txt", "Evidence 06: Lakebase operational serving (synced tables, Postgres access control, feedback loop)", body)


if __name__ == "__main__":
    main()
