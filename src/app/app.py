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
    "checking": "Checking", "savings": "Savings", "cd": "CD", "money_market": "Money market",
    "mortgage": "Mortgage", "auto_loan": "Auto loan", "heloc": "HELOC",
    "personal_loan": "Personal loan", "credit_card": "Credit card",
}
# Categorical palette (validated: adjacent CVD dE >= 9.1, normal-vision dE >= 19.6). Fixed order so each
# product keeps its color everywhere; values and names are printed on the marks for contrast relief.
PRODUCT_COLORS = {"savings": "#2a78d6", "cd": "#eb6834", "money_market": "#1baf7a", "mortgage": "#eda100",
                  "auto_loan": "#e87ba4", "heloc": "#008300", "personal_loan": "#6250d6", "credit_card": "#e34948"}
# Branch colors: navy and burnt orange (chosen by the user), then slate tones for any extra branches.
BRANCH_COLORS = ["#1f3a68", "#cc5500", "#4b5563", "#c4c9d0"]
ACTIONS = {"accepted": "Accepted", "follow_up": "Follow up later", "not_interested_now": "Not interested now",
           "declined": "Declined"}

st.set_page_config(page_title="Customer 360: next best product", layout="wide")

# Every widget sits in a keyed container ("w_*"); this draws a 2pt black border around each,
# and around the outcome form.
st.markdown("""<style>
div[class*="st-key-w_"], div[data-testid="stForm"] {
  border: 2pt solid #000000 !important; border-radius: 8px; padding: 12px 14px;
}
</style>""", unsafe_allow_html=True)


def box(name):
    """A bordered container for one widget."""
    return st.container(key=f"w_{name}")


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
    with col1, box("book_metric_customers"):
        st.metric("Customers with a recommendation", f"{len(book):,}")
    with col2, box("book_metric_uplift"):
        st.metric("Expected CLV uplift (sum)", money(book["expected_clv_uplift"].sum()))
    with col3, box("book_metric_outcomes"):
        st.metric("Outcomes recorded", int(book["last_outcome"].notna().sum()))
    # Branch pie and product columns, cross-filtered: click a slice or a column to filter
    # (shift-click to add), click the background to clear. Selections from the last run
    # are read first so each chart counts only what the other chart has selected.
    def picked(key, param, field):
        ev = st.session_state.get(key)
        sel = (ev or {}).get("selection", {}).get(param) or []
        return [p[field] for p in sel if field in p]

    pick_branch = [b for b in picked("branch_chart", "branch_pick", "branch") if b in branches]
    pick_prod = picked("product_chart", "product_pick", "product")
    for_pie = book[book["product"].isin(pick_prod)] if pick_prod else book
    for_bars = book[book["branch"].isin(pick_branch)] if pick_branch else book

    by_branch = for_pie.groupby("branch").agg(customers=("customer_360_id", "count")).reindex(branches, fill_value=0).reset_index()
    # Label ink per slice: white on navy, burnt orange and dark slate; near-black on light slate.
    by_branch["label_ink"] = ["#0b0b0b" if i == 3 else "#ffffff" for i in range(len(by_branch))]
    bsel = alt.selection_point(name="branch_pick", fields=["branch"], toggle="event.shiftKey")
    pie_base = alt.Chart(by_branch).encode(
        theta=alt.Theta("customers:Q", stack=True),
        color=alt.Color("branch:N", scale=alt.Scale(domain=branches, range=BRANCH_COLORS[:len(branches)]),
                        legend=alt.Legend(title=None, orient="bottom")),
        tooltip=[alt.Tooltip("branch:N", title="Branch"), alt.Tooltip("customers:Q", title="Customers")])
    pie = pie_base.mark_arc(outerRadius=110, stroke="#ffffff", strokeWidth=2).encode(
        opacity=alt.condition(bsel, alt.value(1.0), alt.value(0.3))).add_params(bsel)
    pie_labels = pie_base.mark_text(radius=72, fontSize=13, fontWeight="bold").encode(
        text="customers:Q", color=alt.Color("label_ink:N", scale=None))

    counts = (for_bars.groupby("product")
              .agg(customers=("customer_360_id", "count"), expected_uplift=("expected_clv_uplift", "sum"))
              .reset_index())
    counts["product_name"] = counts["product"].map(PRODUCT_NAMES)
    counts["uplift_label"] = counts["expected_uplift"].map(money)
    psel = alt.selection_point(name="product_pick", fields=["product"], toggle="event.shiftKey")
    order = list(PRODUCT_COLORS)
    bar_base = alt.Chart(counts).encode(
        x=alt.X("product_name:N", sort=counts.sort_values("customers", ascending=False)["product_name"].tolist(),
                title=None, scale=alt.Scale(paddingInner=0.25, paddingOuter=0.1),
                axis=alt.Axis(labelAngle=0, ticks=False, domain=False, labelPadding=8, labelLimit=120)),
        y=alt.Y("customers:Q", title="Customers",
                scale=alt.Scale(domain=[0, max(1, int(counts["customers"].max() * 1.15))], nice=False),
                axis=alt.Axis(grid=True, gridOpacity=0.15, domain=False, ticks=False, tickCount=4)))
    bars = bar_base.mark_bar(cornerRadiusEnd=4).encode(
        color=alt.Color("product:N", scale=alt.Scale(domain=order, range=[PRODUCT_COLORS[p] for p in order]),
                        legend=None),
        opacity=alt.condition(psel, alt.value(1.0), alt.value(0.3)),
        tooltip=[alt.Tooltip("product_name:N", title="Product"), alt.Tooltip("customers:Q", title="Customers"),
                 alt.Tooltip("uplift_label:N", title="Expected CLV uplift")],
    ).add_params(psel)
    bar_labels = bar_base.mark_text(baseline="bottom", dy=-4, fontSize=12).encode(text="customers:Q")

    left, right = st.columns([1, 2])
    with left, box("branch_pie"):
        st.markdown("**Customers by branch**")
        st.altair_chart((pie + pie_labels).properties(height=280).configure_view(strokeWidth=0),
                        on_select="rerun", key="branch_chart",
                        width="stretch")
    with right, box("product_chart"):
        st.markdown("**Next best product**")
        st.altair_chart((bars + bar_labels).properties(height=280).configure_view(strokeWidth=0),
                        on_select="rerun", key="product_chart",
                        width="stretch")
    showing = []
    if pick_branch:
        showing.append("branch " + ", ".join(pick_branch))
    if pick_prod:
        showing.append(", ".join(PRODUCT_NAMES.get(p, p) for p in pick_prod))
    st.caption("Click a slice or a column to filter; shift-click to add; click the background to clear."
               + (f" Showing: {'; '.join(showing)}." if showing else ""))
    in_branch = book[book["branch"].isin(pick_branch)] if pick_branch else book
    view = in_branch[in_branch["product"].isin(pick_prod)] if pick_prod else in_branch
    view = view.assign(product=view["product"].map(PRODUCT_NAMES),
                       likelihood=(view["propensity"] * 100).round(1).astype(str) + "%",
                       expected_clv_uplift=view["expected_clv_uplift"].map(money),
                       clv_uplift_if_adopted=view["clv_uplift_if_adopted"].map(money),
                       last_outcome=view["last_outcome"].map(lambda a: ACTIONS.get(a, "") if a else ""))
    st.caption("Click a row to open that customer's 360 profile.")
    view = view.reset_index(drop=True)
    st.session_state["book_ids"] = view["customer_360_id"].tolist()
    with box("book_table"):
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
    for col, (name, label, value) in zip(m, [
            ("products", "Active products", int(cust.active_products)),
            ("deposits", "Deposits", money(cust.total_deposit_balance)),
            ("loans", "Loans", money(cust.total_loan_balance)),
            ("spend", "Card spend, 12 months", money(cust.card_spend_12m)),
            ("digital", "Digital events, 90 days", int(cust.digital_events_90d))]):
        with col, box(f"profile_metric_{name}"):
            st.metric(label, value)

    recs = run(banker, "SELECT * FROM app.recommendations WHERE customer_360_id = %s ORDER BY recommendation_rank", (cid,))
    top = recs.iloc[0]
    left, right = st.columns([3, 2])
    with left, box("recommendation"):
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
    with right, box("holdings"):
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
        with box("history"):
            st.markdown("#### Outcomes recorded")
            st.dataframe(hist, hide_index=True, width="stretch")
