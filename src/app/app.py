"""Relationship banker app: my book of customers, the customer 360 view, the next best
product with its explanation, and recording what happened.

Reads only the Lakebase `app` views and writes app.banker_feedback. The signed-in
banker comes from the X-Forwarded-Email header that Databricks Apps sets; every query
runs in a transaction that sets app.banker, so Postgres views and row-level security
return only that banker's branches. All data is synthetic.
"""

import os
import time

import pandas as pd
import psycopg
import streamlit as st
from databricks.sdk import WorkspaceClient

ENDPOINT = os.environ.get("LAKEBASE_ENDPOINT", "projects/c360-serving/branches/production/endpoints/primary")
PRODUCT_NAMES = {
    "checking": "Checking", "savings": "Savings", "cd": "Certificate of deposit", "money_market": "Money market",
    "mortgage": "Mortgage", "auto_loan": "Auto loan", "heloc": "Home equity line of credit",
    "personal_loan": "Personal loan", "credit_card": "Credit card",
}
ACTIONS = {"accepted": "Accepted", "follow_up": "Follow up later", "not_interested_now": "Not interested now",
           "declined": "Declined"}

st.set_page_config(page_title="Customer 360: next best product", layout="wide")


@st.cache_resource
def workspace():
    return WorkspaceClient()


@st.cache_resource(ttl=40 * 60)  # OAuth database tokens last about an hour
def credential():
    w = workspace()
    return {"token": w.postgres.generate_database_credential(endpoint=ENDPOINT).token,
            "user": os.environ.get("PGUSER") or w.current_user.me().user_name,
            "host": os.environ.get("PGHOST") or w.postgres.get_endpoint(name=ENDPOINT).status.hosts.host,
            "dbname": os.environ.get("PGDATABASE", "c360")}


def run(banker, sql, params=None, write=False):
    c = credential()
    with psycopg.connect(host=c["host"], dbname=c["dbname"], user=c["user"], password=c["token"],
                         sslmode="require", connect_timeout=10) as conn:
        with conn.transaction():
            cur = conn.cursor()
            cur.execute("SELECT set_config('app.banker', %s, true)", (banker,))
            cur.execute(sql, params or ())
            if write:
                return None
            cols = [d.name for d in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=cols)


def money(x):
    return "n/a" if x is None or pd.isna(x) else f"${x:,.0f}"


banker = st.context.headers.get("X-Forwarded-Email", "")
if not banker and not os.environ.get("DATABRICKS_APP_NAME"):
    banker = os.environ.get("C360_DEV_BANKER", "")  # local testing only; never used inside Databricks Apps
if not banker:
    st.error("No signed-in user was forwarded to the app. Open it from the Databricks Apps URL.")
    st.stop()

branches = run(banker, "SELECT branch_id FROM app.my_branches ORDER BY branch_id")["branch_id"].tolist()
st.sidebar.markdown("### Relationship banker")
st.sidebar.write(banker)
if not branches:
    st.sidebar.warning("You are not assigned to any branch.")
    st.title("Customer 360: next best product")
    st.info("Ask your data owner to add you to the banker roster (c360_banker_assignments).")
    st.stop()
st.sidebar.write("Branches: " + ", ".join(branches))
st.sidebar.caption("Synthetic data. Recommendations come from a propensity model ranked by expected CLV uplift; "
                   "CLV uses illustrative assumptions.")
page = st.sidebar.radio("View", ["My book", "Customer 360"])

if page == "My book":
    st.title("My book: next best product")
    book = run(banker, """
        SELECT c.customer_360_id, c.first_name || ' ' || c.last_name AS customer, c.home_branch_id AS branch,
               c.segment, c.active_products, r.product, r.propensity, r.expected_clv_uplift,
               r.clv_uplift_if_adopted,
               (SELECT f.action FROM app.banker_feedback f
                 WHERE f.customer_360_id = c.customer_360_id ORDER BY f.created_at DESC LIMIT 1) AS last_outcome
        FROM app.recommendations r JOIN app.customers c USING (customer_360_id)
        WHERE r.recommendation_rank = 1
        ORDER BY r.expected_clv_uplift DESC, c.customer_360_id""")
    col1, col2, col3 = st.columns(3)
    col1.metric("Customers with a recommendation", f"{len(book):,}")
    col2.metric("Expected CLV uplift (sum)", money(book["expected_clv_uplift"].sum()))
    col3.metric("Outcomes recorded", int(book["last_outcome"].notna().sum()))
    f1, f2 = st.columns(2)
    pick_branch = f1.multiselect("Branch", branches, default=branches)
    pick_prod = f2.multiselect("Product", sorted(book["product"].unique()),
                               format_func=lambda p: PRODUCT_NAMES.get(p, p))
    view = book[book["branch"].isin(pick_branch)]
    if pick_prod:
        view = view[view["product"].isin(pick_prod)]
    view = view.assign(product=view["product"].map(PRODUCT_NAMES),
                       likelihood=(view["propensity"] * 100).round(1).astype(str) + "%",
                       expected_clv_uplift=view["expected_clv_uplift"].map(money),
                       clv_uplift_if_adopted=view["clv_uplift_if_adopted"].map(money),
                       last_outcome=view["last_outcome"].map(lambda a: ACTIONS.get(a, "") if a else ""))
    st.dataframe(view[["customer_360_id", "customer", "branch", "segment", "active_products", "product", "likelihood",
                       "expected_clv_uplift", "clv_uplift_if_adopted", "last_outcome"]],
                 hide_index=True, use_container_width=True)
    st.caption("Open a customer in the Customer 360 view to see the reasons and record the outcome.")

else:
    st.title("Customer 360")
    ids = run(banker, """SELECT c.customer_360_id, c.first_name || ' ' || c.last_name AS customer
                         FROM app.customers c JOIN app.recommendations r USING (customer_360_id)
                         WHERE r.recommendation_rank = 1
                         ORDER BY r.expected_clv_uplift DESC, c.customer_360_id""")
    if ids.empty:
        st.info("No customers with recommendations in your branches.")
        st.stop()
    options = ids["customer_360_id"].tolist()
    label = dict(zip(options, (ids["customer"] + " (" + ids["customer_360_id"] + ")").tolist()))
    # A stable key keeps the banker's choice across reruns even if the list is re-fetched.
    cid = st.selectbox("Customer (type to search)", options, format_func=label.get, key="customer_select")
    cust = run(banker, "SELECT * FROM app.customers WHERE customer_360_id = %s", (cid,)).iloc[0]
    st.subheader(f"{cust.first_name} {cust.last_name}")
    st.caption(f"{cust.customer_360_id} | {cust.city}, {cust.state} | branch {cust.home_branch_id} | "
               f"{str(cust.segment).replace('_', ' ')} | customer for {cust.tenure_years} years | age {cust.age}")
    m = st.columns(5)
    m[0].metric("Active products", int(cust.active_products))
    m[1].metric("Deposits", money(cust.total_deposit_balance))
    m[2].metric("Loans", money(cust.total_loan_balance))
    m[3].metric("Card spend, 12 months", money(cust.card_spend_12m))
    m[4].metric("Digital events, 90 days", int(cust.digital_events_90d))

    recs = run(banker, "SELECT * FROM app.recommendations WHERE customer_360_id = %s ORDER BY recommendation_rank", (cid,))
    top = recs.iloc[0]
    left, right = st.columns([3, 2])
    with left:
        st.markdown(f"#### Next best product: {PRODUCT_NAMES.get(top['product'], top['product'])}")
        if top["explanation"]:
            for line in str(top["explanation"]).splitlines():
                if line.strip():
                    st.write(line)
        st.caption("Facts behind it: " + str(top["signals"]))
        st.caption(f"Likelihood {top['propensity']:.1%} (x{top['lift_vs_base_rate']:.0f} the usual rate) | "
                   f"CLV today {money(top['clv_current'])}, with product {money(top['clv_with_product'])}")
        if len(recs) > 1:
            st.markdown("**Also worth discussing**")
            for r in recs.iloc[1:].itertuples():
                st.write(f"- {PRODUCT_NAMES.get(r.product, r.product)}: likelihood {r.propensity:.1%}, "
                         f"expected CLV uplift {money(r.expected_clv_uplift)}")
    with right:
        st.markdown("#### Products held")
        hold = run(banker, """SELECT product, product_variant, open_date, balance, status FROM app.holdings
                              WHERE customer_360_id = %s ORDER BY open_date""", (cid,))
        hold["product"] = hold["product"].map(PRODUCT_NAMES)
        hold["balance"] = hold["balance"].map(money)
        st.dataframe(hold, hide_index=True, use_container_width=True)

    st.markdown("#### Record the outcome")
    with st.form("feedback", clear_on_submit=True):
        prod = st.selectbox("Product discussed", recs["product"], format_func=lambda p: PRODUCT_NAMES.get(p, p))
        action = st.radio("Outcome", list(ACTIONS), format_func=ACTIONS.get, horizontal=True)
        note = st.text_area("Note (optional)", max_chars=1000)
        if st.form_submit_button("Save outcome"):
            run(banker, """INSERT INTO app.banker_feedback (customer_360_id, home_branch_id, product, action, note)
                           VALUES (%s, %s, %s, %s, %s)""",
                (cid, cust.home_branch_id, prod, action, note or None), write=True)
            st.success("Saved.")
            time.sleep(0.5)
            st.rerun()
    hist = run(banker, """SELECT created_at, product, action, note FROM app.banker_feedback
                          WHERE customer_360_id = %s ORDER BY created_at DESC""", (cid,))
    if not hist.empty:
        hist["product"] = hist["product"].map(PRODUCT_NAMES)
        hist["action"] = hist["action"].map(ACTIONS)
        st.dataframe(hist, hide_index=True, use_container_width=True)
