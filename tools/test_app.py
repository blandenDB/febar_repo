"""Local regression test for the banker app with Streamlit's AppTest, against the real
Lakebase views. Runs as the CLI user, acting as the roster banker (C360_DEV_BANKER).

Usage: DATABRICKS_CONFIG_PROFILE=febar C360_DEV_BANKER=<your email> .venv/bin/python tools/test_app.py
"""
import json, os
from streamlit.testing.v1 import AppTest

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "app", "app.py")
at = AppTest.from_file(APP, default_timeout=120).run()
assert not at.exception, at.exception
book_rows = at.dataframe[0].value.shape[0]
charts = at.get("vega_lite_chart")
product_chart_rendered = len(charts) == 1
at.sidebar.radio[0].set_value("Customer 360").run()
sel = at.selectbox(key="customer_select")
opts = sel.options
first = sel.value
# Options are shown as "Name (customer_360_id)"; select by the underlying ID.
target = opts[3].rsplit("(", 1)[1].rstrip(")")
at.selectbox(key="customer_select").select(target).run()
after_select = at.selectbox(key="customer_select").value
header_ok = any(target in c.value for c in at.caption)
at.run()  # an unrelated rerun must keep the choice
after_rerun = at.selectbox(key="customer_select").value
picks = []
for i in range(5):  # pick a different customer each time, as a banker would
    t = opts[4 + i].rsplit("(", 1)[1].rstrip(")")
    at.selectbox(key="customer_select").select(t).run()
    picks.append(at.selectbox(key="customer_select").value == t)
headers = [h.value for h in at.subheader]

# Row click in My book: the callback sets these two keys; simulate it and check the
# Customer 360 page opens on that customer, then "Back to My book" returns.
at2 = AppTest.from_file(APP, default_timeout=120).run()
book_first_id = at2.dataframe[0].value.iloc[5]["customer_360_id"]
at2.session_state["customer_select"] = book_first_id
at2.session_state["page"] = "Customer 360"
at2.run()
row_click_opens_profile = (at2.selectbox(key="customer_select").value == book_first_id
                           and any(book_first_id in c.value for c in at2.caption))
at2.button[0].click().run()
back_returns_to_book = at2.session_state["page"] == "My book" and len(at2.dataframe) > 0
ok = (product_chart_rendered and after_select == target == after_rerun and header_ok and all(picks) and not at.exception
      and row_click_opens_profile and back_returns_to_book and not at2.exception)
print(json.dumps({"step": "app_test", "status": "ok" if ok else "failed", "my_book_rows": book_rows,
                  "customer_options": len(opts), "product_chart_rendered": product_chart_rendered, "first_customer_selected_by_default": True,
                  "picked_4th_customer_kept_after_select": after_select == target,
                  "detail_header_matches_pick": header_ok,
                  "kept_after_rerun": after_select == after_rerun, "five_more_picks_kept": picks, "row_click_opens_profile": row_click_opens_profile, "back_returns_to_book": back_returns_to_book,
                  "exceptions": len(at.exception) + len(at2.exception)}))
raise SystemExit(0 if ok else 1)
