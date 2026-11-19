"""Relationship banker app: my book of customers, the customer 360 view, the next best
product with its explanation, and recording what happened.

Reads only the Lakebase `app` views and writes app.banker_feedback. The signed-in
banker comes from the X-Forwarded-Email header that Databricks Apps sets; every query
runs in a transaction that sets app.banker, so Postgres views and row-level security
return only that banker's branches. All data is synthetic.
"""

import os
import time

import altair as alt
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


def open_customer_from_book():
    """Row click in My book: remember the customer and switch to Customer 360.
    Runs as a callback, before the next script run, so it can set other widgets' state."""
    rows = st.session_state["book_table"].selection.rows
    if rows:
        st.session_state["customer_select"] = st.session_state["book_ids"][rows[0]]
        st.session_state["page"] = "Customer 360"


def back_to_book():
    st.session_state["page"] = "My book"


page = st.sidebar.radio("View", ["My book", "Customer 360"], key="page")

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
    pick_branch = st.multiselect("Branch", branches, default=branches)
    in_branch = book[book["branch"].isin(pick_branch)]

    # Next best product, ranked: click a bar to filter the table (shift-click for several,
    # click the background to clear). One hue; unselected bars fade to gray.
    counts = (in_branch.groupby("product")
              .agg(customers=("customer_360_id", "count"), expected_uplift=("expected_clv_uplift", "sum"))
              .reset_index())
    counts["product_name"] = counts["product"].map(PRODUCT_NAMES)
    counts["uplift_label"] = counts["expected_uplift"].map(money)
    pick = alt.selection_point(name="product_pick", fields=["product"], toggle="event.shiftKey")
    base = alt.Chart(counts).encode(
        y=alt.Y("product_name:N", sort="-x", title=None, axis=alt.Axis(ticks=False, domain=False, labelPadding=8)),
        x=alt.X("customers:Q", title="Customers with this as their next best product",
                axis=alt.Axis(grid=True, gridOpacity=0.15, domain=False, ticks=False, tickCount=4)))
    bars = base.mark_bar(size=18, cornerRadiusEnd=4).encode(
        color=alt.condition(pick, alt.value("#2a78d6"), alt.value("#c9c8c3")),
        tooltip=[alt.Tooltip("product_name:N", title="Product"), alt.Tooltip("customers:Q", title="Customers"),
                 alt.Tooltip("uplift_label:N", title="Expected CLV uplift")],
    ).add_params(pick)
    labels = base.mark_text(align="left", dx=6, fontSize=12).encode(text="customers:Q")
    st.markdown("**Next best product in my book**")
    event = st.altair_chart((bars + labels).properties(height=34 * max(len(counts), 1)),
                            on_select="rerun", key="product_chart", width="stretch")
    pick_prod = [p["product"] for p in (event.selection.get("product_pick") or []) if "product" in p]
    st.caption("Click a bar to filter the table; shift-click to add products; click the background to clear."
               + (f" Showing: {', '.join(PRODUCT_NAMES.get(p, p) for p in pick_prod)}." if pick_prod else ""))
    view = in_branch[in_branch["product"].isin(pick_prod)] if pick_prod else in_branch
    view = view.assign(product=view["product"].map(PRODUCT_NAMES),
                       likelihood=(view["propensity"] * 100).round(1).astype(str) + "%",
                       expected_clv_uplift=view["expected_clv_uplift"].map(money),
                       clv_uplift_if_adopted=view["clv_uplift_if_adopted"].map(money),
                       last_outcome=view["last_outcome"].map(lambda a: ACTIONS.get(a, "") if a else ""))
    st.caption("Click a row to open that customer's 360 profile.")
    view = view.reset_index(drop=True)
    st.session_state["book_ids"] = view["customer_360_id"].tolist()
    st.dataframe(view[["customer_360_id", "customer", "branch", "segment", "active_products", "product", "likelihood",
                       "expected_clv_uplift", "clv_uplift_if_adopted", "last_outcome"]],
                 hide_index=True, width="stretch", key="book_table",
                 on_select=open_customer_from_book, selection_mode="single-row")

else:
    st.button("← Back to My book", on_click=back_to_book)
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
        st.dataframe(hold, hide_index=True, width="stretch")

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
        st.dataframe(hist, hide_index=True, width="stretch")
