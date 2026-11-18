"""Generate synthetic raw source files for the FE Bar customer 360 build.

Everything here is synthetic. Names are random combinations from short generic
lists, emails use the reserved example.com/example.net domains, phones use the
fictional 555 prefix, and tax IDs are opaque tokens (not SSN shaped).

Four source systems, each with its own customer ID:
  core_banking: customers, deposit_accounts            (CSV)
  loans:        customers, loans                       (CSV)
  cards:        customers, card_accounts, card_transactions (JSON lines)
  digital:      users, events                          (JSON lines)

Planted issues (see DECISIONS.md): cross-system identity variants, exact
duplicate rows, orphan accounts, bad values, missing keys. Ground truth (which
source IDs are the same person, and how many issues were planted) goes to a
separate volume so the pipeline never reads it.

Idempotent: fixed seed and fixed as-of date; every output folder is deleted
and rewritten on each run. Prints a JSON summary as the last line.
"""

import argparse
import json
import os
import shutil
import tempfile

import numpy as np
import pandas as pd

AS_OF = pd.Timestamp("2026-10-31")

FIRST = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "William", "Elizabeth", "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Lisa", "Daniel", "Nancy",
    "Matthew", "Betty", "Anthony", "Sandra", "Mark", "Margaret", "Steven", "Ashley",
    "Andrew", "Kimberly", "Joshua", "Emily", "Kevin", "Donna", "Brian", "Michelle",
    "Maria", "Carlos", "Ana", "Luis", "Priya", "Wei", "Mei", "Omar", "Fatima", "Kenji",
]
LAST = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
    "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
    "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
    "Carter", "Patel",
]
NICKNAMES = {
    "William": "Bill", "Robert": "Bob", "Elizabeth": "Liz", "Michael": "Mike",
    "James": "Jim", "Jennifer": "Jen", "Christopher": "Chris", "Daniel": "Dan",
    "Thomas": "Tom", "Joseph": "Joe", "Richard": "Rick", "Matthew": "Matt",
    "Anthony": "Tony", "Steven": "Steve", "Andrew": "Andy", "Joshua": "Josh",
}
STREETS = ["Oak", "Maple", "Cedar", "Pine", "Elm", "Main", "Lake", "Hill", "River", "Park",
           "Sunset", "Meadow", "Willow", "Highland", "Church", "Mill"]
STREET_TYPES = ["St", "Ave", "Rd", "Ln", "Dr", "Ct"]
# (city, state, zip prefix): a fictional regional footprint
REGIONS = [
    ("Riverton", "TX", "750"), ("Lakeview", "TX", "751"), ("Cedar Hill", "TX", "752"),
    ("Brookfield", "OK", "730"), ("Fairview", "OK", "731"), ("Maple Grove", "AR", "720"),
    ("Oakridge", "AR", "721"), ("Pinecrest", "LA", "700"), ("Bayside", "LA", "701"),
    ("Westfield", "TX", "760"),
]
SEGMENTS = np.array(["mass", "mass_affluent", "affluent"])
SEG_P = [0.60, 0.30, 0.10]
SEG_MULT = {"mass": 1.0, "mass_affluent": 2.5, "affluent": 6.0}
MCC = ["grocery", "fuel", "dining", "travel", "retail", "utilities", "healthcare",
       "entertainment", "online_shopping", "home_improvement"]
EVENT_TYPES = ["login", "view_balance", "transfer", "bill_pay", "view_product_page",
               "start_application"]
EVENT_P = [0.45, 0.20, 0.10, 0.08, 0.12, 0.05]
ALL_PRODUCTS = ["checking", "savings", "cd", "money_market", "mortgage", "auto_loan",
                "heloc", "personal_loan", "credit_card"]

SECONDS_PER_DAY = 86400
# Scales the lifetime chance of holding each non-checking product. Products are opened
# at onboarding or acquired later (see open_dates), so this sets the yearly cross-sell
# rate. Tuned so about 10% of customers open a new product per year.
CROSS_SELL_BOOST = 1.8


# ---------------------------------------------------------------- helpers
def unique_ids(rng, prefix, n, width=8):
    """n distinct random IDs of `width` digits, without materializing the ID space."""
    lo = 10 ** (width - 1)
    nums = np.empty(0, dtype=np.int64)
    while len(nums) < n:
        draw = rng.integers(lo, lo * 10, size=int((n - len(nums)) * 1.1) + 16, dtype=np.int64)
        nums = pd.unique(np.concatenate([nums, draw]))
    return np.array([f"{prefix}{x}" for x in nums[:n]], dtype=object)


def iso_date(ts):
    return pd.Series(pd.to_datetime(np.asarray(ts))).dt.strftime("%Y-%m-%d").to_numpy()


def iso_ts(ts):
    return pd.Series(pd.to_datetime(np.asarray(ts))).dt.strftime("%Y-%m-%dT%H:%M:%SZ").to_numpy()


def rand_dates_between(rng, start, end):
    """Random timestamps between start and end (arrays of Timestamps)."""
    start = pd.to_datetime(pd.Series(start)).to_numpy()
    end = pd.to_datetime(pd.Series(end)).to_numpy()
    span = (end - start).astype("timedelta64[s]").astype(np.int64)
    span = np.maximum(span, 1)
    off = (rng.random(len(span)) * span).astype(np.int64)
    return start + off.astype("timedelta64[s]")


def fmt_phone(digits, style):
    d = pd.Series(digits, dtype=object)
    a, b, c = d.str[0:3], d.str[3:6], d.str[6:10]
    if style == "paren":
        return ("(" + a + ") " + b + "-" + c).to_numpy()
    if style == "dash":
        return (a + "-" + b + "-" + c).to_numpy()
    if style == "plain":
        return d.to_numpy()
    return ("+1 " + a + "." + b + "." + c).to_numpy()


def pick(rng, n, rate):
    """Indices of a random `rate` share of n rows (at least 1 when n > 0)."""
    k = max(1, int(round(n * rate))) if n else 0
    return rng.choice(n, size=k, replace=False)


def open_dates(rng, since, p_onboard=0.2, scale_years=4.0):
    """Open date for each account a customer would hold, plus a keep mask.

    p_onboard of accounts open within 30 days of joining. The rest are acquired later
    at a constant rate (exponential wait, mean scale_years); accounts whose acquisition
    date would fall after AS_OF are not held yet (keep=False). A constant rate means a
    new customer is no more likely to open a product in a given window than a long-
    standing one, apart from onboarding itself.
    """
    since = pd.to_datetime(pd.Series(since)).to_numpy()
    n = len(since)
    onboard = rng.random(n) < p_onboard
    wait_days = np.where(onboard, rng.random(n) * 30, rng.exponential(scale_years * 365.25, n))
    opened = since + (wait_days * SECONDS_PER_DAY).astype("int64").astype("timedelta64[s]")
    keep = opened <= AS_OF.to_datetime64()
    return opened, keep


# ---------------------------------------------------------------- people
def make_people(rng, n):
    region_idx = rng.integers(0, len(REGIONS), n)
    city = np.array([REGIONS[i][0] for i in region_idx], dtype=object)
    state = np.array([REGIONS[i][1] for i in region_idx], dtype=object)
    zip_ = np.array([REGIONS[i][2] + f"{z:02d}" for i, z in
                     zip(region_idx, rng.integers(0, 100, n))], dtype=object)
    first = rng.choice(FIRST, n).astype(object)
    last = rng.choice(LAST, n).astype(object)
    pid = np.arange(1, n + 1)
    dob = AS_OF - pd.to_timedelta(rng.integers(18 * 365, 85 * 365, n), unit="D")
    age = ((AS_OF - dob).days / 365.25).to_numpy()
    email = (pd.Series(first).str.lower() + "." + pd.Series(last).str.lower()
             + pd.Series(pid).astype(str) + "@example.com").to_numpy()
    phone = np.array([f"555{x:07d}" for x in rng.integers(0, 10_000_000, n)], dtype=object)
    addr = np.array([f"{num} {s} {t}" for num, s, t in zip(
        rng.integers(100, 9999, n), rng.choice(STREETS, n), rng.choice(STREET_TYPES, n))],
        dtype=object)
    tax = unique_ids(rng, "TT", n, width=9)
    segment = rng.choice(SEGMENTS, n, p=SEG_P).astype(object)
    max_tenure = np.clip((age - 18) * 365, 0, 30 * 365).astype(int)  # never after AS_OF
    since = AS_OF - pd.to_timedelta((rng.random(n) * max_tenure).astype(int), unit="D")
    branch = np.array([f"BR{(i * 3 + b) % 25 + 1:03d}" for i, b in
                       zip(region_idx, rng.integers(0, 3, n))], dtype=object)
    return pd.DataFrame({
        "person_id": pid, "first_name": first, "last_name": last, "dob": dob,
        "age": age, "email": email, "phone": phone, "address_line": addr, "city": city,
        "state": state, "zip": zip_, "tax_token": tax, "segment": segment,
        "customer_since": since, "home_branch_id": branch,
    })


def identity_copy(rng, people, rows, prefix, p_tax_missing, p_email_old, p_zip_move,
                  p_name_variant, upper_names=False):
    """A source system's own copy of identity fields, with realistic drift."""
    df = people.iloc[rows].reset_index(drop=True).copy()
    n = len(df)
    df["source_customer_id"] = unique_ids(rng, prefix, n)
    if p_tax_missing is not None:
        miss = rng.random(n) < p_tax_missing
        df.loc[miss, "tax_token"] = None
    old = rng.random(n) < p_email_old
    df.loc[old, "email"] = (df.loc[old, "first_name"].str[0].str.lower()
                            + df.loc[old, "last_name"].str.lower()
                            + pd.Series(rng.integers(10, 99, old.sum()), index=df.index[old]).astype(str)
                            + "@example.net")
    moved = rng.random(n) < p_zip_move
    df.loc[moved, "zip"] = [REGIONS[i][2] + f"{z:02d}" for i, z in
                            zip(rng.integers(0, len(REGIONS), moved.sum()),
                                rng.integers(0, 100, moved.sum()))]
    var = rng.random(n) < p_name_variant
    for i in np.flatnonzero(var):
        fn = df.at[i, "first_name"]
        if fn in NICKNAMES and rng.random() < 0.6:
            df.at[i, "first_name"] = NICKNAMES[fn]
        else:
            ln = df.at[i, "last_name"]
            j = int(rng.integers(1, len(ln)))
            df.at[i, "last_name"] = ln[:j] + ln[j + 1:]
    if upper_names:
        df["first_name"] = df["first_name"].str.upper()
        df["last_name"] = df["last_name"].str.upper()
    return df


# ---------------------------------------------------------------- products
def deposit_accounts(rng, people):
    n = len(people)
    seg = people["segment"].to_numpy()
    mult = np.vectorize(SEG_MULT.get)(seg)
    specs = {  # product: (base prob, prob boost per segment mult, log-mean balance, sigma)
        "checking": (0.92, 0.0, 7.6, 1.0),
        "savings": (0.45, 0.04, 8.6, 1.2),
        "cd": (0.06, 0.03, 9.9, 0.8),
        "money_market": (0.04, 0.03, 10.2, 0.9),
    }
    parts = []
    for prod, (p0, boost, mu, sd) in specs.items():
        p_hold = p0 + boost * mult
        if prod != "checking":
            p_hold = p_hold * CROSS_SELL_BOOST
        has = rng.random(n) < np.minimum(p_hold, 0.97)
        idx = np.flatnonzero(has)
        if prod == "checking":  # the anchor account is opened when the customer joins
            opened = people["customer_since"].to_numpy()[idx]
            keep = np.ones(len(idx), dtype=bool)
        else:
            opened, keep = open_dates(rng, people["customer_since"].to_numpy()[idx])
        idx, opened = idx[keep], opened[keep]
        bal = np.round(rng.lognormal(mu, sd, len(idx)) * np.sqrt(mult[idx]), 2)
        parts.append(pd.DataFrame({"person_id": people["person_id"].to_numpy()[idx],
                                   "product_type": prod, "open_date": opened,
                                   "balance": bal}))
    acc = pd.concat(parts, ignore_index=True)
    acc["status"] = np.where(rng.random(len(acc)) < 0.04, "closed", "open")
    acc["account_id"] = unique_ids(rng, "DA", len(acc), width=9)
    return acc


def loan_accounts(rng, people):
    n = len(people)
    seg = people["segment"].to_numpy()
    age = people["age"].to_numpy()
    seg_p = {"mass": 0.12, "mass_affluent": 0.28, "affluent": 0.38}
    p_mort = np.minimum(np.vectorize(seg_p.get)(seg) * CROSS_SELL_BOOST, 0.9) * ((age > 25) & (age < 75))
    has_mort = rng.random(n) < p_mort
    specs = [
        ("mortgage", has_mort, (3.0, 7.5), [180, 360], 12.2, 0.5),
        ("auto_loan", rng.random(n) < min(0.20 * CROSS_SELL_BOOST, 0.9), (4.0, 11.0), [36, 48, 60, 72], 10.1, 0.4),
        ("heloc", has_mort & (rng.random(n) < 0.30), (6.0, 10.0), [120], 10.6, 0.6),
        ("personal_loan", rng.random(n) < min(0.07 * CROSS_SELL_BOOST, 0.9), (8.0, 18.0), [24, 36, 48, 60], 9.2, 0.5),
    ]
    parts = []
    for prod, mask, (rlo, rhi), terms, mu, sd in specs:
        idx = np.flatnonzero(mask)
        opened, keep = open_dates(rng, people["customer_since"].to_numpy()[idx])
        idx, opened = idx[keep], opened[keep]
        orig = np.round(rng.lognormal(mu, sd, len(idx)), -2)
        parts.append(pd.DataFrame({
            "person_id": people["person_id"].to_numpy()[idx], "product_type": prod,
            "origination_date": opened, "original_amount": orig,
            "current_balance": np.round(orig * rng.uniform(0.15, 1.0, len(idx)), 2),
            "interest_rate": np.round(rng.uniform(rlo, rhi, len(idx)), 3),
            "term_months": rng.choice(terms, len(idx)),
        }))
    ln = pd.concat(parts, ignore_index=True)
    ln["status"] = rng.choice(["current", "delinquent_30", "delinquent_90"], len(ln),
                              p=[0.95, 0.04, 0.01])
    ln["loan_id"] = unique_ids(rng, "LA", len(ln), width=9)
    return ln


def card_accounts(rng, people):
    n = len(people)
    seg = people["segment"].to_numpy()
    seg_p = {"mass": 0.32, "mass_affluent": 0.50, "affluent": 0.60}
    holder = rng.random(n) < np.minimum(np.vectorize(seg_p.get)(seg) * CROSS_SELL_BOOST, 0.95)
    idx = np.flatnonzero(holder)
    idx = np.concatenate([idx, idx[rng.random(len(idx)) < 0.10]])  # some hold two cards
    opened, keep = open_dates(rng, people["customer_since"].to_numpy()[idx])
    idx, opened = idx[keep], opened[keep]
    s = seg[idx]
    ptype = np.where(s == "mass", rng.choice(["cash_back", "secured"], len(idx), p=[0.8, 0.2]),
                     rng.choice(["cash_back", "travel_rewards"], len(idx), p=[0.5, 0.5]))
    limit = np.round(np.vectorize(SEG_MULT.get)(s) * rng.uniform(1500, 6000, len(idx)), -2)
    cards = pd.DataFrame({
        "person_id": people["person_id"].to_numpy()[idx], "product_type": ptype.astype(object),
        "open_date": opened, "credit_limit": limit,
        "current_balance": np.round(limit * rng.uniform(0, 0.6, len(idx)), 2),
        "status": np.where(rng.random(len(idx)) < 0.03, "closed", "open"),
    })
    cards["card_id"] = unique_ids(rng, "CA", len(cards), width=9)
    return cards


def card_transactions(rng, cards, total):
    w = cards["credit_limit"].to_numpy() * (cards["status"].to_numpy() == "open")
    counts = rng.multinomial(total, w / w.sum())
    rep = np.repeat(np.arange(len(cards)), counts)
    start = np.maximum(cards["open_date"].to_numpy()[rep],
                       (AS_OF - pd.Timedelta(days=365)).to_datetime64())
    ts = rand_dates_between(rng, start, np.repeat(AS_OF.to_datetime64(), len(rep)))
    return pd.DataFrame({
        "txn_id": unique_ids(rng, "TX", len(rep), width=10),
        "card_id": cards["card_id"].to_numpy()[rep], "txn_ts": iso_ts(ts),
        "amount": np.round(rng.lognormal(3.4, 1.0, len(rep)), 2),
        "merchant_category": rng.choice(MCC, len(rep)),
    })


def digital_events(rng, people, users, recent_acq, total):
    """Events per user; recent product acquisitions get a leading browse signal."""
    w = rng.lognormal(0, 1.0, len(users))
    counts = rng.multinomial(total, w / w.sum())
    rep = np.repeat(np.arange(len(users)), counts)
    ts = AS_OF.to_datetime64() - (rng.random(len(rep)) * 365 * SECONDS_PER_DAY).astype(
        "timedelta64[s]")
    etype = rng.choice(EVENT_TYPES, len(rep), p=EVENT_P).astype(object)
    product = np.where(np.isin(etype, ["view_product_page", "start_application"]),
                       rng.choice(ALL_PRODUCTS, len(rep)), None)
    ev = pd.DataFrame({"dg_user_id": users["source_customer_id"].to_numpy()[rep],
                       "event_ts": ts, "event_type": etype, "product": product})

    # Leading signal: views (and often an application start) in the 60 days before
    # a recently opened product, for digitally enrolled customers.
    uid_by_person = dict(zip(users["person_id"], users["source_customer_id"]))
    acq = recent_acq[recent_acq["person_id"].isin(uid_by_person)].reset_index(drop=True)
    k = rng.integers(2, 8, len(acq))
    rep2 = np.repeat(np.arange(len(acq)), k)
    open_ts = acq["open_ts"].to_numpy()[rep2]
    lead = (rng.random(len(rep2)) * 60 * SECONDS_PER_DAY + 3600).astype("timedelta64[s]")
    sig = pd.DataFrame({
        "dg_user_id": acq["person_id"].map(uid_by_person).to_numpy()[rep2],
        "event_ts": open_ts - lead,
        "event_type": np.where(rng.random(len(rep2)) < 0.2, "start_application",
                               "view_product_page").astype(object),
        "product": acq["product"].to_numpy()[rep2],
    })
    ev = pd.concat([ev, sig], ignore_index=True)
    ev["channel"] = rng.choice(["mobile", "web"], len(ev), p=[0.65, 0.35])
    ev = ev.sort_values("event_ts", kind="stable").reset_index(drop=True)
    ev["event_id"] = unique_ids(rng, "EV", len(ev), width=10)
    ev["event_ts"] = iso_ts(ev["event_ts"])
    return ev, len(sig)


# ---------------------------------------------------------------- planting
def plant_duplicates(rng, df, rate):
    dup = df.iloc[pick(rng, len(df), rate)]
    return pd.concat([df, dup], ignore_index=True).sample(frac=1, random_state=7) \
        .reset_index(drop=True), len(dup)


# ---------------------------------------------------------------- output
def write(df, folder, name, fmt):
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder, exist_ok=True)
    fname = f"{name}.{'csv' if fmt == 'csv' else 'json'}"
    with tempfile.TemporaryDirectory() as tmp:
        local = os.path.join(tmp, fname)
        if fmt == "csv":
            df.to_csv(local, index=False)
        else:
            df.to_json(local, orient="records", lines=True)
        shutil.copy(local, os.path.join(folder, fname))
    return len(df)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-root", required=True, help="e.g. /Volumes/<cat>/<schema>/raw")
    ap.add_argument("--truth-root", required=True, help="e.g. /Volumes/<cat>/<schema>/ground_truth")
    ap.add_argument("--customers", type=int, default=50_000)
    ap.add_argument("--card-txns", type=int, default=800_000)
    ap.add_argument("--digital-events", type=int, default=1_200_000)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    rng = np.random.default_rng(a.seed)
    people = make_people(rng, a.customers)
    n = len(people)
    planted = {}

    # ---- products, keyed by person
    dep = deposit_accounts(rng, people)
    lns = loan_accounts(rng, people)
    crd = card_accounts(rng, people)

    # ---- source identity copies
    core = identity_copy(rng, people, np.arange(n), "CB", None, 0.0, 0.0, 0.0)
    loan_people = np.flatnonzero(people["person_id"].isin(lns["person_id"]))
    card_people = np.flatnonzero(people["person_id"].isin(crd["person_id"]))
    dig_people = np.flatnonzero(rng.random(n) < np.clip(0.95 - people["age"].to_numpy() / 150, 0.2, 0.9))
    lcust = identity_copy(rng, people, loan_people, "LN", 0.04, 0.12, 0.06, 0.04, upper_names=True)
    ccust = identity_copy(rng, people, card_people, "CC", 0.03, 0.10, 0.05, 0.04)
    dusers = identity_copy(rng, people, dig_people, "DG", 1.0, 0.08, 0.05, 0.03)

    def map_ids(frame, ident):
        return frame["person_id"].map(dict(zip(ident["person_id"], ident["source_customer_id"])))

    dep["cb_customer_id"] = map_ids(dep, core)
    lns["ln_customer_id"] = map_ids(lns, lcust)
    crd["cc_customer_id"] = map_ids(crd, ccust)

    # ---- acquisitions in the last 365 days drive the digital browse signal
    recent = pd.concat([
        dep.rename(columns={"open_date": "open_ts", "product_type": "product"})[["person_id", "product", "open_ts"]],
        lns.rename(columns={"origination_date": "open_ts", "product_type": "product"})[["person_id", "product", "open_ts"]],
        crd.assign(product="credit_card").rename(columns={"open_date": "open_ts"})[["person_id", "product", "open_ts"]],
    ], ignore_index=True)
    recent = recent[recent["open_ts"] >= AS_OF - pd.Timedelta(days=300)]
    recent = recent[recent["product"] != "checking"]

    txns = card_transactions(rng, crd, a.card_txns)
    events, signal_events = digital_events(rng, people, dusers, recent, a.digital_events)

    # ---- issue 4: bad values
    i = pick(rng, len(dep), 0.01); dep.loc[dep.index[i], "balance"] *= -1
    planted["deposit_negative_balance"] = len(i)
    i = pick(rng, len(dep), 0.01)
    dep.loc[dep.index[i], "open_date"] = AS_OF + pd.to_timedelta(rng.integers(10, 400, len(i)), unit="D")
    planted["deposit_future_open_date"] = len(i)
    i = pick(rng, len(lns), 0.01)
    lns.loc[lns.index[i], "origination_date"] = AS_OF + pd.to_timedelta(rng.integers(10, 400, len(i)), unit="D")
    planted["loan_future_origination_date"] = len(i)
    i = pick(rng, len(lns), 0.01)
    lns.loc[lns.index[i], "interest_rate"] = rng.choice([-1.5, 0.0, 45.0, 99.9], len(i))
    planted["loan_rate_out_of_range"] = len(i)

    # ---- issue 3: orphans (customer IDs that exist nowhere)
    i = pick(rng, len(lns), 0.015)
    lns.loc[lns.index[i], "ln_customer_id"] = [f"LN9{x:07d}" for x in rng.integers(0, 10**7, len(i))]
    planted["loan_orphan_customer_id"] = len(i)
    i = pick(rng, len(crd), 0.015)
    crd.loc[crd.index[i], "cc_customer_id"] = [f"CC9{x:07d}" for x in rng.integers(0, 10**7, len(i))]
    planted["card_orphan_customer_id"] = len(i)

    # ---- issue 6: missing keys
    i = pick(rng, len(events), 0.02); events.loc[events.index[i], "dg_user_id"] = None
    planted["event_null_user_id"] = len(i)
    i = pick(rng, len(crd), 0.015); crd.loc[crd.index[i], "product_type"] = None
    planted["card_null_product_type"] = len(i)

    # ---- shape source tables
    def ident_cols(df, id_col, phone_style, has_tax=True):
        out = pd.DataFrame({id_col: df["source_customer_id"], "first_name": df["first_name"],
                            "last_name": df["last_name"], "date_of_birth": iso_date(df["dob"]),
                            "email": df["email"], "phone": fmt_phone(df["phone"], phone_style),
                            "address_line": df["address_line"], "city": df["city"],
                            "state": df["state"], "zip": df["zip"]})
        if has_tax:
            out.insert(1, "tax_id_token", df["tax_token"])
        return out

    core_t = ident_cols(core, "cb_customer_id", "paren")
    core_t["segment"] = core["segment"]
    core_t["home_branch_id"] = core["home_branch_id"]
    core_t["customer_since"] = iso_date(core["customer_since"])
    dep_t = dep[["account_id", "cb_customer_id", "product_type", "open_date", "balance", "status"]].copy()
    dep_t["open_date"] = iso_date(dep_t["open_date"])
    lcust_t = ident_cols(lcust, "ln_customer_id", "dash")
    lns_t = lns[["loan_id", "ln_customer_id", "product_type", "origination_date", "original_amount",
                 "current_balance", "interest_rate", "term_months", "status"]].copy()
    lns_t["origination_date"] = iso_date(lns_t["origination_date"])
    ccust_t = ident_cols(ccust, "cc_customer_id", "plain")
    crd_t = crd[["card_id", "cc_customer_id", "product_type", "open_date", "credit_limit",
                 "current_balance", "status"]].copy()
    crd_t["open_date"] = iso_date(crd_t["open_date"])
    dusers_t = ident_cols(dusers, "dg_user_id", "intl", has_tax=False)
    dusers_t["enrolled_date"] = iso_date(rand_dates_between(
        rng, np.maximum(dusers["customer_since"].to_numpy(), (AS_OF - pd.Timedelta(days=3650)).to_datetime64()),
        np.repeat((AS_OF - pd.Timedelta(days=30)).to_datetime64(), len(dusers))))
    events_t = events[["event_id", "dg_user_id", "event_ts", "event_type", "product", "channel"]]

    # ---- issue 2: exact duplicate rows
    core_t, planted["core_customer_duplicate_rows"] = plant_duplicates(rng, core_t, 0.02)
    dep_t, planted["deposit_account_duplicate_rows"] = plant_duplicates(rng, dep_t, 0.02)
    crd_t, planted["card_account_duplicate_rows"] = plant_duplicates(rng, crd_t, 0.02)

    # ---- write raw
    r = a.raw_root
    rows = {
        "core_banking/customers": write(core_t, f"{r}/core_banking/customers", "customers", "csv"),
        "core_banking/deposit_accounts": write(dep_t, f"{r}/core_banking/deposit_accounts", "deposit_accounts", "csv"),
        "loans/customers": write(lcust_t, f"{r}/loans/customers", "customers", "csv"),
        "loans/loans": write(lns_t, f"{r}/loans/loans", "loans", "csv"),
        "cards/customers": write(ccust_t, f"{r}/cards/customers", "customers", "json"),
        "cards/card_accounts": write(crd_t, f"{r}/cards/card_accounts", "card_accounts", "json"),
        "cards/card_transactions": write(txns, f"{r}/cards/card_transactions", "card_transactions", "json"),
        "digital/users": write(dusers_t, f"{r}/digital/users", "users", "json"),
        "digital/events": write(events_t, f"{r}/digital/events", "events", "json"),
    }

    # ---- ground truth (separate volume; never read by the pipeline)
    truth = pd.concat([
        pd.DataFrame({"system": s, "source_customer_id": d["source_customer_id"], "person_id": d["person_id"]})
        for s, d in [("core_banking", core), ("loans", lcust), ("cards", ccust), ("digital", dusers)]
    ], ignore_index=True)
    t = a.truth_root
    write(truth, f"{t}/identity_map", "identity_map", "csv")
    variants = {
        "loans_tax_token_missing": int(lcust["tax_token"].isna().sum()),
        "cards_tax_token_missing": int(ccust["tax_token"].isna().sum()),
    }
    manifest = {"seed": a.seed, "as_of": str(AS_OF.date()), "people": n,
                "planted_issues": planted, "identity_variants": variants,
                "digital_signal_events": signal_events, "raw_rows": rows}
    shutil.rmtree(f"{t}/manifest", ignore_errors=True)
    os.makedirs(f"{t}/manifest", exist_ok=True)
    with open(f"{t}/manifest/manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    summary = {"step": "generate_raw_data", "status": "ok", "seed": a.seed,
               "people": n, "raw_rows": rows, "total_raw_rows": int(sum(rows.values())),
               "planted_issues": planted, "identity_rows": int(len(truth))}
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
