"""Copy banker feedback from Lakebase (app.banker_feedback) into Unity Catalog so
analysts can query recommendation outcomes in Genie. MERGE on feedback_id keeps reruns
idempotent. The target carries the branch row filter. Banker identities are replaced
by a stable pseudonymous key. Prints a JSON summary as the last line."""
import argparse, hashlib, json
import pandas as pd
import psycopg
from databricks.sdk import WorkspaceClient
from pyspark.sql import SparkSession

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--schema", required=True)
    ap.add_argument("--endpoint", default="projects/c360-serving/branches/production/endpoints/primary")
    ap.add_argument("--database", default="c360")
    a = ap.parse_args()
    fq = f"{a.catalog}.{a.schema}"
    w = WorkspaceClient()
    ep = w.postgres.get_endpoint(name=a.endpoint)
    cred = w.postgres.generate_database_credential(endpoint=a.endpoint)
    with psycopg.connect(host=ep.status.hosts.host, dbname=a.database, user=w.current_user.me().user_name,
                         password=cred.token, sslmode="require") as conn:
        df = pd.read_sql("SELECT feedback_id::text AS feedback_id, customer_360_id, home_branch_id, product, action, "
                         "note, banker_principal, created_at FROM app.banker_feedback", conn)
    df["banker_key"] = df["banker_principal"].map(lambda s: "banker_" + hashlib.sha256(s.encode()).hexdigest()[:10])
    df = df.drop(columns=["banker_principal"])
    spark = SparkSession.builder.getOrCreate()
    spark.sql(f"""CREATE TABLE IF NOT EXISTS {fq}.banker_feedback (
        feedback_id STRING COMMENT 'Feedback ID from the app',
        customer_360_id STRING COMMENT 'Customer the feedback is about',
        home_branch_id STRING COMMENT 'Customer home branch (drives the relationship banker row filter)',
        product STRING COMMENT 'Recommended product the banker acted on',
        action STRING COMMENT 'accepted, declined, follow_up or not_interested_now',
        note STRING COMMENT 'Free-text banker note',
        created_at TIMESTAMP COMMENT 'When the banker recorded the feedback',
        banker_key STRING COMMENT 'Pseudonymous banker identifier')
      WITH ROW FILTER {fq}.c360_branch_filter ON (home_branch_id)
      COMMENT 'Relationship banker feedback on cross-sell recommendations, copied from Lakebase'""")
    before = spark.table(f"{fq}.banker_feedback").count()
    if len(df):
        df["created_at"] = pd.to_datetime(df["created_at"], utc=True).dt.tz_localize(None)
        spark.createDataFrame(df).createOrReplaceTempView("fb")
        spark.sql(f"""MERGE INTO {fq}.banker_feedback t USING fb s ON t.feedback_id = s.feedback_id
                      WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *""")
    after = spark.table(f"{fq}.banker_feedback").count()
    print(json.dumps({"step": "feedback_to_uc", "status": "ok", "lakebase_rows": int(len(df)),
                      "uc_rows_before": before, "uc_rows_after": after,
                      "actions": df["action"].value_counts().to_dict() if len(df) else {}}))

if __name__ == "__main__":
    main()
