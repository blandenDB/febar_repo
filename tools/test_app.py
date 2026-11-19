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
ok = after_select == target == after_rerun and header_ok and all(picks) and not at.exception
print(json.dumps({"step": "app_test", "status": "ok" if ok else "failed", "my_book_rows": book_rows,
                  "customer_options": len(opts), "first_customer_selected_by_default": True,
                  "picked_4th_customer_kept_after_select": after_select == target,
                  "detail_header_matches_pick": header_ok,
                  "kept_after_rerun": after_select == after_rerun, "five_more_picks_kept": picks, "exceptions": len(at.exception)}))
raise SystemExit(0 if ok else 1)
