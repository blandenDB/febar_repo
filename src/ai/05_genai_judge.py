"""LLM judge for the banker explanations, as defined in EVAL_PROTOCOL.md.

A random sample of 200 explanations (fixed seed) is judged with MLflow GenAI
evaluation using three guideline judges. The judge model differs from the model that
wrote the explanations. Applies the protocol bars (grounded >= 95%, all checks
>= 90%) and prints a JSON summary as the last line.
"""

import argparse
import json

import mlflow
import pandas as pd
from mlflow.genai.scorers import Guidelines
from pyspark.sql import SparkSession

GUIDELINES = {
    "grounded": ("The response only states facts that appear in the customer facts given in the request. "
                 "It does not invent numbers, rates, fees, promotions, life events or any other details."),
    "relevant": "The response explains why the recommended product fits this particular customer.",
    "opener": "The response includes one natural, non-pushy question a banker could ask the customer.",
}
GROUNDED_BAR, ALL_PASS_BAR = 0.95, 0.90


def passed(v):
    return str(v).strip().lower() in ("yes", "true", "pass", "1")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--schema", required=True)
    ap.add_argument("--experiment", required=True)
    ap.add_argument("--judge-endpoint", default="databricks-claude-sonnet-5-5")
    ap.add_argument("--sample", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    spark = SparkSession.builder.getOrCreate()
    rows = spark.sql(f"""
        SELECT customer_360_id, product, CONCAT_WS('; ', signals) AS facts, explanation, llm_endpoint
        FROM {a.catalog}.{a.schema}.gold_recommendation_explanations
        WHERE explanation IS NOT NULL
        ORDER BY xxhash64(customer_360_id, {a.seed}) LIMIT {a.sample}""").toPandas()

    data = [{"inputs": {"request": f"Recommended product: {r.product}. Customer facts: {r.facts}"},
             "outputs": r.explanation} for r in rows.itertuples()]
    judge = f"databricks:/{a.judge_endpoint}"
    scorers = [Guidelines(name=n, guidelines=g, model=judge) for n, g in GUIDELINES.items()]

    mlflow.set_experiment(a.experiment)
    with mlflow.start_run(run_name="genai_judge_explanations") as run:
        result = mlflow.genai.evaluate(data=data, scorers=scorers)
        run_id = run.info.run_id

    df = result.result_df if hasattr(result, "result_df") and result.result_df is not None else pd.DataFrame()
    value_cols = {n: next((c for c in df.columns if c.startswith(n) and c.endswith("value")), None) for n in GUIDELINES}
    rat_cols = {n: next((c for c in df.columns if c.startswith(n) and "rationale" in c), None) for n in GUIDELINES}
    pass_rates, per_row = {}, pd.DataFrame(index=df.index)
    for n, c in value_cols.items():
        if c is not None:
            per_row[n] = df[c].map(passed)
            pass_rates[n] = round(float(per_row[n].mean()), 3)
    all_pass = round(float(per_row.all(axis=1).mean()), 3) if len(per_row.columns) == len(GUIDELINES) else None

    failures = []
    for i in per_row.index[~per_row.all(axis=1)][:8] if all_pass is not None else []:
        failed = [n for n in GUIDELINES if not per_row.at[i, n]]
        failures.append({"product": rows.at[i, "product"], "failed": failed,
                         "explanation": rows.at[i, "explanation"][:400],
                         "rationale": {n: str(df.at[i, rat_cols[n]])[:300] for n in failed if rat_cols[n]}})

    grounded_ok = pass_rates.get("grounded", 0) >= GROUNDED_BAR
    all_ok = (all_pass or 0) >= ALL_PASS_BAR
    print(json.dumps({
        "step": "genai_judge", "status": "ok" if value_cols["grounded"] else "no_judge_columns",
        "sample": len(rows), "generator": rows["llm_endpoint"].iloc[0] if len(rows) else None,
        "judge": a.judge_endpoint, "pass_rates": pass_rates, "all_checks_pass_rate": all_pass,
        "aggregate_metrics": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in (result.metrics or {}).items()},
        "verdict": {"grounded_bar": GROUNDED_BAR, "grounded_met": grounded_ok,
                    "all_checks_bar": ALL_PASS_BAR, "all_checks_met": all_ok,
                    "claim": ("explanations meet the protocol bar" if grounded_ok and all_ok
                              else "explanations do NOT meet the protocol bar")},
        "examples_of_failures": failures, "result_columns": list(df.columns)[:30], "mlflow_run_id": run_id}))


if __name__ == "__main__":
    main()
