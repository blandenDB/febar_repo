"""Run the evaluation defined in EVAL_PROTOCOL.md (committed before this ran).

Out-of-time test: train on the three oldest 60-day snapshots, test on the newest.
Compares the model with the simple baseline (recent product page views, ties broken
by the product's opening rate in training) on the same rows, with the same timing
rule. Applies the success bar written in the protocol and prints a JSON summary as
the last line. Logged to MLflow; nothing is registered.
"""

import argparse
import importlib.util
import json
import os

import mlflow
import numpy as np
import pandas as pd
from pyspark.sql import SparkSession
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

TRAIN_SNAPSHOTS = ["2026-03-05", "2026-05-04", "2026-07-03"]
TEST_SNAPSHOT = "2026-09-01"
HORIZON_DAYS = 60
LIFT_BAR = 2.7          # 1.5% -> 4% response
BASELINE_RATIO_BAR = 1.2
MIN_POSITIVES = 30


def load_training_module(code_dir):
    spec = importlib.util.spec_from_file_location("train_and_score", os.path.join(code_dir, "02_train_and_score.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def top_decile_lift(y, score):
    if len(y) == 0 or y.sum() == 0:
        return None
    k = max(1, int(len(y) * 0.1))
    top = np.argsort(-score, kind="stable")[:k]
    return float(y[top].mean() / y.mean())


def auc(y, score):
    return float(roc_auc_score(y, score)) if 0 < y.sum() < len(y) else None


def r(x, n=3):
    return None if x is None else round(x, n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--schema", required=True)
    ap.add_argument("--code-dir", required=True, help="workspace folder holding 02_train_and_score.py")
    ap.add_argument("--experiment", required=True)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    fq = f"{a.catalog}.{a.schema}"
    m = load_training_module(a.code_dir)
    m.AS_OF = "2026-10-31"
    spark = SparkSession.builder.getOrCreate()

    train = pd.concat([m.snapshot_features(spark, fq, s, HORIZON_DAYS).assign(snapshot=s) for s in TRAIN_SNAPSHOTS],
                      ignore_index=True)
    test = m.snapshot_features(spark, fq, TEST_SNAPSHOT, HORIZON_DAYS).assign(snapshot=TEST_SNAPSHOT)
    cat_mask = [f in ("product_code", "segment_code") for f in m.FEATURES]
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0,
                                         categorical_features=cat_mask, random_state=a.seed)
    clf.fit(train[m.FEATURES], train["label"])

    y = test["label"].to_numpy()
    model_score = clf.predict_proba(test[m.FEATURES])[:, 1]
    open_rate = train.groupby("product")["label"].mean()
    # Baseline: recent page views; the product's training opening rate (< 1) only breaks ties.
    base_score = test["views_product_90d"].to_numpy() + test["product"].map(open_rate).fillna(0).to_numpy()

    train_customers = set(train["customer_360_id"])
    new_cust = ~test["customer_360_id"].isin(train_customers).to_numpy()

    overall = {"test_rows": int(len(y)), "positives": int(y.sum()), "base_rate": r(float(y.mean()), 5),
               "model_top_decile_lift": r(top_decile_lift(y, model_score)),
               "baseline_top_decile_lift": r(top_decile_lift(y, base_score)),
               "model_auc": r(auc(y, model_score)), "baseline_auc": r(auc(y, base_score))}
    overall["model_vs_baseline_lift_ratio"] = (r(overall["model_top_decile_lift"] / overall["baseline_top_decile_lift"])
                                               if overall["baseline_top_decile_lift"] else None)

    per_product = {}
    prods = test["product"].to_numpy()
    for p in m.PRODUCTS:
        k = prods == p
        yp = y[k]
        per_product[p] = {"test_rows": int(k.sum()), "positives": int(yp.sum()),
                          "model_lift": r(top_decile_lift(yp, model_score[k])),
                          "baseline_lift": r(top_decile_lift(yp, base_score[k])),
                          "model_auc": r(auc(yp, model_score[k])),
                          "usable_for_claims": bool(yp.sum() >= MIN_POSITIVES)}

    yn = y[new_cust]
    out_of_customer = {"test_rows": int(new_cust.sum()), "positives": int(yn.sum()),
                       "model_top_decile_lift": r(top_decile_lift(yn, model_score[new_cust])),
                       "baseline_top_decile_lift": r(top_decile_lift(yn, base_score[new_cust]))}

    lift_ok = overall["model_top_decile_lift"] is not None and overall["model_top_decile_lift"] >= LIFT_BAR
    ratio_ok = overall["model_vs_baseline_lift_ratio"] is not None and overall["model_vs_baseline_lift_ratio"] >= BASELINE_RATIO_BAR
    verdict = {"lift_bar": LIFT_BAR, "lift_met": lift_ok, "baseline_ratio_bar": BASELINE_RATIO_BAR,
               "baseline_ratio_met": ratio_ok,
               "claim": ("SUPPORTED on synthetic data: the method clears the bar" if lift_ok and ratio_ok
                         else "NOT SUPPORTED: no targeting claim")}

    mlflow.set_experiment(a.experiment)
    with mlflow.start_run(run_name="eval_protocol_out_of_time") as run:
        mlflow.log_params({"train_snapshots": ",".join(TRAIN_SNAPSHOTS), "test_snapshot": TEST_SNAPSHOT,
                           "horizon_days": HORIZON_DAYS, "lift_bar": LIFT_BAR, "baseline_ratio_bar": BASELINE_RATIO_BAR})
        mlflow.log_metrics({k: v for k, v in overall.items() if isinstance(v, (int, float)) and v is not None})
        mlflow.log_dict({"overall": overall, "per_product": per_product, "out_of_customer": out_of_customer,
                         "verdict": verdict}, "eval_protocol_results.json")
        run_id = run.info.run_id

    print(json.dumps({"step": "eval_protocol", "status": "ok", "protocol": "EVAL_PROTOCOL.md (2026-11-19)",
                      "train_snapshots": TRAIN_SNAPSHOTS, "test_window": f"{TEST_SNAPSHOT} to 2026-10-31",
                      "train_rows": int(len(train)), "train_positives": int(train["label"].sum()),
                      "overall": overall, "per_product": per_product, "out_of_customer": out_of_customer,
                      "verdict": verdict, "mlflow_run_id": run_id}))


if __name__ == "__main__":
    main()
