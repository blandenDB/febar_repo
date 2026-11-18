"""Cross-sell propensity model, CLV and recommendations.

1. Point-in-time training set: snapshots S_k = as_of - k x horizon (k = 1..n). For each,
   features use only data on or before S_k; the label is "opened product P in
   (S_k, S_k + horizon]". One row per (snapshot, customer, product not held at S_k).
2. Train one gradient-boosted model over all products (product is a feature) and
   report AUC and top-decile lift per product on a held-out set of customers.
   Logged to MLflow and registered in Unity Catalog with alias "champion".
3. Score the current snapshot (as_of), compute CLV from the assumption tables, and
   rank each customer's eligible products by expected CLV uplift = propensity x (CLV
   with the product - CLV today). Eligible: propensity >= min_lift x the product's
   base rate in training. Writes gold_customer_clv and gold_cross_sell_recommendations
   (both carry the branch row filter). INSERT OVERWRITE keeps reruns idempotent.
Prints a JSON summary as the last line.
"""

import argparse
import json
from datetime import date, timedelta

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from mlflow.models import infer_signature
from pyspark.sql import SparkSession
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import roc_auc_score

PRODUCTS = ["savings", "cd", "money_market", "mortgage", "auto_loan", "heloc", "personal_loan",
            "credit_card"]
ALL_PRODUCTS = ["checking"] + PRODUCTS
SEGMENTS = ["mass", "mass_affluent", "affluent", "unknown"]
FEATURES = (["product_code", "segment_code", "age", "tenure_years", "n_products",
             "deposit_balance", "loan_balance", "card_limit", "card_spend_12m",
             "is_digital", "digital_events_90d", "logins_90d", "views_product_90d",
             "app_starts_product_90d", "views_other_products_90d"]
            + [f"has_{p}" for p in ALL_PRODUCTS])
PRETTY = {"checking": "checking account", "savings": "savings account", "cd": "certificate of deposit",
          "money_market": "money market account", "mortgage": "mortgage", "auto_loan": "auto loan",
          "heloc": "home equity line of credit", "personal_loan": "personal loan",
          "credit_card": "credit card"}


def snapshot_features(spark, fq, snap, horizon_days=None):
    """(customer, candidate product) rows with features as of `snap`; label if horizon given."""
    label_sql = ""
    if horizon_days:
        label_sql = f""",
      CASE WHEN EXISTS (SELECT 1 FROM {fq}.gold_product_holdings h2
                        WHERE h2.customer_360_id = c.customer_360_id AND h2.product = p.product
                          AND h2.open_date > DATE '{snap}'
                          AND h2.open_date <= DATE_ADD(DATE '{snap}', {horizon_days}))
           THEN 1 ELSE 0 END AS label"""
    sql = f"""
    WITH c AS (
      SELECT customer_360_id, home_branch_id, COALESCE(segment, 'unknown') AS segment,
             age - CAST(DATEDIFF(DATE '{AS_OF}', DATE '{snap}') / 365.25 AS INT) AS age,
             MONTHS_BETWEEN(DATE '{snap}', customer_since) / 12 AS tenure_years
      FROM {fq}.gold_customer_360
      WHERE customer_since IS NULL OR customer_since <= DATE '{snap}'
    ),
    held AS (
      SELECT customer_360_id, product,
             SUM(IF(source_system = 'core_banking', balance, 0)) AS dep_bal,
             SUM(IF(source_system = 'loans', balance, 0)) AS loan_bal,
             SUM(COALESCE(credit_limit, 0)) AS card_limit
      FROM {fq}.gold_product_holdings
      WHERE open_date <= DATE '{snap}' AND status <> 'closed'
      GROUP BY customer_360_id, product
    ),
    hc AS (
      SELECT customer_360_id, COUNT(*) AS n_products, SUM(dep_bal) AS deposit_balance,
             SUM(loan_bal) AS loan_balance, SUM(card_limit) AS card_limit,
             {", ".join(f"MAX(IF(product = '{p}', 1, 0)) AS has_{p}" for p in ALL_PRODUCTS)}
      FROM held GROUP BY customer_360_id
    ),
    dig AS (
      SELECT m.customer_360_id, COUNT(*) AS digital_events_90d,
             SUM(IF(e.event_type = 'login', 1, 0)) AS logins_90d
      FROM {fq}.silver_digital_events e
      JOIN {fq}.customer_identity_map m ON m.system = 'digital' AND m.source_customer_id = e.dg_user_id
      WHERE e.event_ts > DATE_SUB(DATE '{snap}', 90) AND e.event_ts < DATE_ADD(DATE '{snap}', 1)
      GROUP BY m.customer_360_id
    ),
    interest AS (
      SELECT m.customer_360_id, e.product,
             SUM(IF(e.event_type = 'view_product_page', 1, 0)) AS views,
             SUM(IF(e.event_type = 'start_application', 1, 0)) AS app_starts
      FROM {fq}.silver_digital_events e
      JOIN {fq}.customer_identity_map m ON m.system = 'digital' AND m.source_customer_id = e.dg_user_id
      WHERE e.product IS NOT NULL
        AND e.event_ts > DATE_SUB(DATE '{snap}', 90) AND e.event_ts < DATE_ADD(DATE '{snap}', 1)
      GROUP BY m.customer_360_id, e.product
    ),
    interest_tot AS (
      SELECT customer_360_id, SUM(views) AS views_all FROM interest GROUP BY customer_360_id
    ),
    spend AS (
      SELECT m.customer_360_id, SUM(t.amount) AS card_spend_12m
      FROM {fq}.silver_card_transactions t
      JOIN {fq}.silver_card_accounts a USING (card_id)
      JOIN {fq}.customer_identity_map m ON m.system = 'cards' AND m.source_customer_id = a.cc_customer_id
      WHERE t.txn_ts > DATE_SUB(DATE '{snap}', 365) AND t.txn_ts < DATE_ADD(DATE '{snap}', 1)
      GROUP BY m.customer_360_id
    ),
    digital_users AS (
      SELECT DISTINCT customer_360_id FROM {fq}.customer_identity_map WHERE system = 'digital'
    ),
    p AS (SELECT EXPLODE(ARRAY({", ".join(f"'{x}'" for x in PRODUCTS)})) AS product)
    SELECT c.customer_360_id, c.home_branch_id, c.segment, p.product, c.age, c.tenure_years,
           COALESCE(hc.n_products, 0) AS n_products,
           COALESCE(hc.deposit_balance, 0) AS deposit_balance,
           COALESCE(hc.loan_balance, 0) AS loan_balance,
           COALESCE(hc.card_limit, 0) AS card_limit,
           COALESCE(s.card_spend_12m, 0) AS card_spend_12m,
           IF(du.customer_360_id IS NULL, 0, 1) AS is_digital,
           COALESCE(d.digital_events_90d, 0) AS digital_events_90d,
           COALESCE(d.logins_90d, 0) AS logins_90d,
           COALESCE(i.views, 0) AS views_product_90d,
           COALESCE(i.app_starts, 0) AS app_starts_product_90d,
           COALESCE(it.views_all, 0) - COALESCE(i.views, 0) AS views_other_products_90d,
           {", ".join(f"COALESCE(hc.has_{x}, 0) AS has_{x}" for x in ALL_PRODUCTS)}
           {label_sql}
    FROM c CROSS JOIN p
    LEFT JOIN hc ON hc.customer_360_id = c.customer_360_id
    LEFT JOIN held hp ON hp.customer_360_id = c.customer_360_id AND hp.product = p.product
    LEFT JOIN dig d ON d.customer_360_id = c.customer_360_id
    LEFT JOIN interest i ON i.customer_360_id = c.customer_360_id AND i.product = p.product
    LEFT JOIN interest_tot it ON it.customer_360_id = c.customer_360_id
    LEFT JOIN spend s ON s.customer_360_id = c.customer_360_id
    LEFT JOIN digital_users du ON du.customer_360_id = c.customer_360_id
    WHERE hp.customer_360_id IS NULL
    """
    df = spark.sql(sql).toPandas()
    df["product_code"] = df["product"].map({p: i for i, p in enumerate(PRODUCTS)})
    df["segment_code"] = df["segment"].map({s: i for i, s in enumerate(SEGMENTS)}).fillna(3)
    for col in FEATURES:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
    df["tenure_years"] = df["tenure_years"].fillna(0)
    return df


def top_decile_lift(y, p):
    if y.sum() == 0:
        return None
    k = max(1, int(len(y) * 0.1))
    top = np.argsort(-p)[:k]
    return float(y[top].mean() / y.mean())


def lifetime_multiplier(n_products, params):
    r = np.where(n_products >= 3, params["retention_3_plus"],
                 np.where(n_products == 2, params["retention_2_products"], params["retention_1_product"]))
    h, d = int(params["horizon_years"]), params["discount_rate"]
    return sum(r ** (t - 1) / (1 + d) ** t for t in range(1, h + 1)), r


def signals(row):
    """Plain facts a banker can say out loud; fed to the explanation model."""
    out = []
    if row.views_product_90d > 0:
        v = int(row.views_product_90d)
        out.append(f"Viewed the {PRETTY[row.product]} page {v} time{'s' if v != 1 else ''} online in the last 90 days")
    if row.app_starts_product_90d > 0:
        art = "an" if PRETTY[row.product][0] in "aeiou" else "a"
        out.append(f"Started an online application for {art} {PRETTY[row.product]} in the last 90 days")
    held = [PRETTY[p] for p in ALL_PRODUCTS if getattr(row, f"has_{p}") == 1]
    out.append("Currently holds: " + (", ".join(held) if held else "no active products"))
    if row.product == "heloc" and row.has_mortgage == 1:
        out.append("Has a mortgage with the bank, so home equity may be available")
    if row.product in ("cd", "money_market", "savings") and row.deposit_balance > 20000:
        out.append(f"Keeps ${row.deposit_balance:,.0f} in deposit accounts")
    if row.product == "credit_card" and row.has_checking == 1 and row.has_credit_card == 0:
        out.append("Banks with us for checking but has no card with us")
    tenure = ("joined the bank in the last month" if row.tenure_years < 0.1
              else f"customer for {row.tenure_years:.1f} years")
    out.append(f"{tenure[0].upper()}{tenure[1:]}, {row.segment.replace('_', ' ')} segment")
    return out


def main():
    global AS_OF
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--schema", required=True)
    ap.add_argument("--as-of", default="2026-10-31")
    ap.add_argument("--horizon-days", type=int, default=60)
    ap.add_argument("--experiment", required=True)
    ap.add_argument("--snapshots", type=int, default=4)
    ap.add_argument("--min-lift", type=float, default=3.0)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    AS_OF = a.as_of
    fq = f"{a.catalog}.{a.schema}"
    spark = SparkSession.builder.getOrCreate()
    snaps = [(date.fromisoformat(a.as_of) - timedelta(days=a.horizon_days * k)).isoformat()
             for k in range(1, a.snapshots + 1)]
    snap = ",".join(snaps)

    # ---------------------------------------------------------------- train
    train = pd.concat([snapshot_features(spark, fq, s_, a.horizon_days).assign(snapshot=s_)
                       for s_ in snaps], ignore_index=True)
    rng = np.random.default_rng(a.seed)
    custs = train["customer_360_id"].unique()
    test_c = set(rng.choice(custs, size=int(len(custs) * 0.25), replace=False))
    is_test = train["customer_360_id"].isin(test_c).to_numpy()
    X, y = train[FEATURES], train["label"].to_numpy()
    cat_mask = [f in ("product_code", "segment_code") for f in FEATURES]

    mlflow.set_registry_uri("databricks-uc")
    mlflow.set_experiment(a.experiment)
    model_name = f"{fq}.cross_sell_propensity"
    with mlflow.start_run(run_name=f"cross_sell_{a.as_of}") as run:
        params = dict(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0,
                      categorical_features=cat_mask, random_state=a.seed)
        clf = HistGradientBoostingClassifier(**params).fit(X[~is_test], y[~is_test])
        p_test = clf.predict_proba(X[is_test])[:, 1]
        y_test = y[is_test]
        metrics = {"auc_overall": float(roc_auc_score(y_test, p_test)),
                   "lift_top_decile_overall": top_decile_lift(y_test, p_test),
                   "train_rows": int((~is_test).sum()), "test_rows": int(is_test.sum()),
                   "train_positives": int(y[~is_test].sum()), "test_positives": int(y_test.sum())}
        per_product = {}
        test_products = train.loc[is_test, "product"].to_numpy()
        for prod in PRODUCTS:
            m = test_products == prod
            yt, pt = y_test[m], p_test[m]
            per_product[prod] = {
                "test_rows": int(m.sum()), "positives": int(yt.sum()),
                "base_rate": round(float(yt.mean()), 5) if m.sum() else None,
                "auc": round(float(roc_auc_score(yt, pt)), 4) if 0 < yt.sum() < len(yt) else None,
                "lift_top_decile": round(top_decile_lift(yt, pt), 2) if yt.sum() else None}
        sample = rng.choice(np.flatnonzero(is_test), size=min(20000, int(is_test.sum())), replace=False)
        imp = permutation_importance(clf, X.iloc[sample], y[sample], scoring="roc_auc", n_repeats=3,
                                     random_state=a.seed)
        importance = sorted(zip(FEATURES, imp.importances_mean), key=lambda t: -t[1])
        mlflow.log_params({k: v for k, v in params.items() if k != "categorical_features"})
        mlflow.log_params({"snapshot_dates": snap, "as_of": a.as_of, "horizon_days": a.horizon_days,
                           "min_lift": a.min_lift,
                           "products": ",".join(PRODUCTS), "n_features": len(FEATURES)})
        mlflow.log_metrics({k: v for k, v in metrics.items() if v is not None})
        for prod, d in per_product.items():
            if d["auc"] is not None:
                mlflow.log_metric(f"auc_{prod}", d["auc"])
                mlflow.log_metric(f"lift_top_decile_{prod}", d["lift_top_decile"])
        mlflow.log_dict({"per_product": per_product,
                         "permutation_importance_auc": {f: round(float(v), 5) for f, v in importance}},
                        "evaluation.json")
        sig = infer_signature(X.head(100), clf.predict_proba(X.head(100))[:, 1])
        info = mlflow.sklearn.log_model(clf, artifact_path="model", signature=sig,
                                        input_example=X.head(5), registered_model_name=model_name)
        version = info.registered_model_version
        mlflow.MlflowClient().set_registered_model_alias(model_name, "champion", version)
        run_id = run.info.run_id

    # ---------------------------------------------------------------- score current snapshot
    cur = snapshot_features(spark, fq, a.as_of)
    model = mlflow.sklearn.load_model(f"models:/{model_name}@champion")
    cur["propensity"] = model.predict_proba(cur[FEATURES])[:, 1]

    # ---------------------------------------------------------------- CLV
    pa = spark.table(f"{fq}.clv_product_assumptions").toPandas().set_index("product").astype(
        {"margin_pct_of_balance": float, "margin_pct_of_spend": float, "annual_fee_income": float})
    pr = {r.parameter: float(r.value) for r in spark.table(f"{fq}.clv_parameters").collect()}
    hold = spark.sql(f"""
      SELECT h.customer_360_id, h.product, COALESCE(c.segment, 'unknown') AS segment,
             SUM(h.balance) AS balance
      FROM {fq}.gold_product_holdings h JOIN {fq}.gold_customer_360 c USING (customer_360_id)
      WHERE h.status <> 'closed' GROUP BY h.customer_360_id, h.product, COALESCE(c.segment, 'unknown')
    """).toPandas()
    hold["balance"] = hold["balance"].astype(float)
    cust = spark.sql(f"""SELECT customer_360_id, home_branch_id, COALESCE(segment, 'unknown') AS segment,
                                active_products, CAST(card_spend_12m AS DOUBLE) AS card_spend_12m
                         FROM {fq}.gold_customer_360""").toPandas()
    hold = hold.join(pa, on="product")
    hold["margin"] = hold["balance"].abs() * hold["margin_pct_of_balance"] + hold["annual_fee_income"]
    margin = hold.groupby("customer_360_id")["margin"].sum()
    cust["annual_margin"] = cust["customer_360_id"].map(margin).fillna(0.0)
    cust["annual_margin"] += cust["card_spend_12m"] * pa.loc["credit_card", "margin_pct_of_spend"]
    mult, ret = lifetime_multiplier(cust["active_products"].to_numpy(), pr)
    cust["retention_rate"], cust["lifetime_multiplier"] = ret, mult
    cust["clv"] = cust["annual_margin"] * cust["lifetime_multiplier"]

    # Margin a newly sold product would add: median balance among current holders in the
    # same segment (overall median if the segment has none).
    med = hold.groupby(["product", "segment"])["balance"].median()
    med_all = hold.groupby("product")["balance"].median()
    spend_med = cust.loc[cust["card_spend_12m"] > 0].groupby("segment")["card_spend_12m"].median()

    def new_margin(prod, seg):
        bal = med.get((prod, seg), med_all.get(prod, 0.0))
        m = abs(bal) * pa.loc[prod, "margin_pct_of_balance"] + pa.loc[prod, "annual_fee_income"]
        if prod == "credit_card":
            m += spend_med.get(seg, spend_med.median()) * pa.loc[prod, "margin_pct_of_spend"]
        return float(m)

    nm = {(p, s): new_margin(p, s) for p in PRODUCTS for s in SEGMENTS}
    cur = cur.merge(cust[["customer_360_id", "annual_margin", "clv", "active_products"]], on="customer_360_id")
    cur["product_annual_margin"] = [nm[(p, s)] for p, s in zip(cur["product"], cur["segment"])]
    mult_next, _ = lifetime_multiplier(cur["active_products"].to_numpy() + 1, pr)
    cur["clv_with_product"] = (cur["annual_margin"] + cur["product_annual_margin"]) * mult_next
    cur["clv_uplift_if_adopted"] = cur["clv_with_product"] - cur["clv"]
    cur["expected_clv_uplift"] = cur["propensity"] * cur["clv_uplift_if_adopted"]
    base_rate = train.loc[~is_test].groupby("product")["label"].mean()
    cur["lift_vs_base_rate"] = cur["propensity"] / cur["product"].map(base_rate)
    eligible = cur[cur["lift_vs_base_rate"] >= a.min_lift].copy()
    eligible = eligible.sort_values(["customer_360_id", "expected_clv_uplift"], ascending=[True, False])
    eligible["rank"] = eligible.groupby("customer_360_id").cumcount() + 1
    recs = eligible[eligible["rank"] <= 3].copy()
    recs["signals"] = [signals(r) for r in recs.itertuples()]

    # ---------------------------------------------------------------- write (idempotent)
    spark.sql(f"""CREATE OR REPLACE TABLE {fq}.gold_customer_clv (
        customer_360_id STRING COMMENT 'Customer ID across all source systems',
        home_branch_id STRING COMMENT 'Customer home branch (drives the relationship banker row filter)',
        segment STRING COMMENT 'Customer segment',
        active_products BIGINT COMMENT 'Number of distinct active products',
        annual_margin DOUBLE COMMENT 'Estimated annual margin from current products, USD (illustrative assumptions)',
        retention_rate DOUBLE COMMENT 'Assumed annual retention given the number of products held',
        lifetime_multiplier DOUBLE COMMENT 'Discounted expected years of margin over the horizon',
        clv DOUBLE COMMENT 'Customer lifetime value = annual_margin x lifetime_multiplier, USD',
        as_of_date DATE COMMENT 'Data as-of date')
      WITH ROW FILTER {fq}.c360_branch_filter ON (home_branch_id)
      COMMENT 'Customer lifetime value per customer from illustrative margin and retention assumptions'""")
    spark.sql(f"""CREATE OR REPLACE TABLE {fq}.gold_cross_sell_recommendations (
        customer_360_id STRING COMMENT 'Customer ID across all source systems',
        home_branch_id STRING COMMENT 'Customer home branch (drives the relationship banker row filter)',
        recommendation_rank INT COMMENT '1 = best next product for this customer by expected CLV uplift',
        product STRING COMMENT 'Recommended product',
        propensity DOUBLE COMMENT 'Model probability the customer opens this product in the next 60 days',
        lift_vs_base_rate DOUBLE COMMENT 'propensity / the product base rate in training (eligible when >= 3)',
        product_annual_margin DOUBLE COMMENT 'Annual margin the product would add, USD (illustrative)',
        clv_current DOUBLE COMMENT 'CLV today, USD',
        clv_with_product DOUBLE COMMENT 'CLV if the customer adopts the product (includes higher retention), USD',
        clv_uplift_if_adopted DOUBLE COMMENT 'clv_with_product - clv_current, USD',
        expected_clv_uplift DOUBLE COMMENT 'propensity x clv_uplift_if_adopted, USD (ranking score)',
        signals ARRAY<STRING> COMMENT 'Plain facts supporting the recommendation, used for the banker explanation',
        model_version STRING COMMENT 'Registered model version used for scoring',
        as_of_date DATE COMMENT 'Data as-of date')
      WITH ROW FILTER {fq}.c360_branch_filter ON (home_branch_id)
      COMMENT 'Up to 3 next-best products per customer: products with propensity at least 3x their base rate, ranked by expected CLV uplift'""")

    clv_out = cust[["customer_360_id", "home_branch_id", "segment", "active_products", "annual_margin",
                    "retention_rate", "lifetime_multiplier", "clv"]].copy()
    clv_out["active_products"] = clv_out["active_products"].astype("int64")
    spark.createDataFrame(clv_out).createOrReplaceTempView("clv_out")
    spark.sql(f"INSERT OVERWRITE {fq}.gold_customer_clv SELECT *, DATE '{a.as_of}' FROM clv_out")

    rec_out = recs[["customer_360_id", "home_branch_id", "rank", "product", "propensity", "lift_vs_base_rate",
                    "product_annual_margin", "clv", "clv_with_product", "clv_uplift_if_adopted",
                    "expected_clv_uplift", "signals"]].copy()
    rec_out["rank"] = rec_out["rank"].astype("int32")
    rec_out["model_version"] = str(version)
    spark.createDataFrame(rec_out).createOrReplaceTempView("rec_out")
    spark.sql(f"""INSERT OVERWRITE {fq}.gold_cross_sell_recommendations
                  SELECT customer_360_id, home_branch_id, rank, product, propensity, lift_vs_base_rate,
                         product_annual_margin,
                         clv, clv_with_product, clv_uplift_if_adopted, expected_clv_uplift, signals,
                         model_version, DATE '{a.as_of}' FROM rec_out""")

    top1 = recs[recs["rank"] == 1]
    summary = {
        "step": "train_and_score", "status": "ok", "snapshot_date": snap, "as_of": a.as_of,
        "model": model_name, "model_version": str(version), "mlflow_run_id": run_id,
        "metrics": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in metrics.items()},
        "per_product": per_product,
        "top_features": [f for f, _ in importance[:6]],
        "customers_scored": int(cur["customer_360_id"].nunique()),
        "customers_with_recommendation": int(recs["customer_360_id"].nunique()),
        "base_rate_by_product": {k: round(float(v), 5) for k, v in base_rate.items()},
        "recommendation_rows": int(len(recs)),
        "top1_product_mix": top1["product"].value_counts().to_dict(),
        "total_clv_musd": round(float(cust["clv"].sum()) / 1e6, 1),
        "total_expected_clv_uplift_top1_musd": round(float(top1["expected_clv_uplift"].sum()) / 1e6, 2),
    }
    print(json.dumps(summary))


AS_OF = None

if __name__ == "__main__":
    main()
