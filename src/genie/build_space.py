"""Build the Genie space definition (src/genie/c360_analyst.geniespace.json) from the
readable definitions below. The bundle deploys the JSON (resources/genie.yml).

[YOUR WORDS] The sample questions, instructions and benchmark questions are drafts.
Rewrite them in your own words; they are part of your story.

Usage: python3 src/genie/build_space.py
"""

import hashlib
import json
import os

FQ = "c360_bank.customer_lifetime_value"
TABLES = ["banker_feedback", "gold_cross_sell_recommendations", "gold_customer_360", "gold_customer_clv",
          "gold_product_holdings"]

SAMPLE_QUESTIONS = [
    "Which branches have the lowest average number of active products per customer?",
    "How many customers have a checking account but no credit card, by segment?",
    "What is the average CLV by number of products held?",
    "Which products are recommended most often as the next best product, and what is their total expected CLV uplift?",
    "How many affluent customers have a mortgage but no home equity line of credit?",
    "Do digitally enrolled customers hold more products than customers who are not enrolled?",
    "How have bankers responded to recommendations so far, by product?",
    "Which 10 branches have the most expected CLV uplift from next best product recommendations?",
]

INSTRUCTIONS = """\
You answer questions from business analysts at a regional bank about customers, the products they hold, customer lifetime value (CLV) and cross-sell recommendations. All data is synthetic.

Tables and keys:
- gold_customer_360 has one row per customer, keyed by customer_360_id. Every other table joins to it on customer_360_id.
- gold_product_holdings has one row per account. A product is active when status <> 'closed'. The has_* columns in gold_customer_360 are 1 when the customer holds that product actively.
- gold_customer_clv has one row per customer with annual_margin and clv.
- gold_cross_sell_recommendations has up to 3 rows per customer. recommendation_rank = 1 is the next best product. Only customers with a strong signal have recommendations.
- banker_feedback records what relationship bankers did with a recommendation (accepted, declined, follow_up, not_interested_now).

Definitions:
- Products: checking, savings, cd (certificate of deposit), money_market, mortgage, auto_loan, heloc (home equity line of credit), personal_loan, credit_card.
- Branch means home_branch_id. Segment is one of mass, mass_affluent, affluent. For the few records not matched to a core banking customer, segment is NULL in gold_customer_360 and 'unknown' in gold_customer_clv.
- "Product penetration" means the share of customers holding a product.
- Return shares, rates and penetration as a fraction between 0 and 1 (for example 0.627), not a percentage, unless the user asks for a percentage.
- When grouping by segment, keep the NULL segment as its own group (records not matched to core banking) unless the user asks to exclude it.
- CLV and expected CLV uplift are estimates based on illustrative margin and retention assumptions. Say so when you report CLV figures and round dollar amounts to whole dollars.
- Data is as of 2026-10-31.

Privacy: names, email and date of birth are masked for analysts. Answer with aggregates; never try to identify individual customers. Use age instead of date of birth.
"""

EXAMPLE_SQL = [
    ("What is product penetration by segment?",
     f"""SELECT segment, COUNT(*) AS customers,
  ROUND(AVG(has_savings), 3) AS savings_penetration, ROUND(AVG(has_credit_card), 3) AS credit_card_penetration,
  ROUND(AVG(has_mortgage), 3) AS mortgage_penetration, ROUND(AVG(active_products), 2) AS avg_active_products
FROM {FQ}.gold_customer_360
GROUP BY segment ORDER BY segment"""),
    ("What is the average CLV by number of products held?",
     f"""SELECT LEAST(active_products, 5) AS active_products_capped_at_5, COUNT(*) AS customers, ROUND(AVG(clv), 0) AS avg_clv_usd
FROM {FQ}.gold_customer_clv
GROUP BY 1 ORDER BY 1"""),
    ("Which products are recommended most often as the next best product?",
     f"""SELECT product, COUNT(*) AS customers, ROUND(SUM(expected_clv_uplift), 0) AS total_expected_clv_uplift_usd
FROM {FQ}.gold_cross_sell_recommendations
WHERE recommendation_rank = 1
GROUP BY product ORDER BY customers DESC"""),
]

BENCHMARKS = [
    ("How many customers are there?", f"SELECT COUNT(*) AS customers FROM {FQ}.gold_customer_360"),
    ("How many customers have a checking account but no credit card?",
     f"SELECT COUNT(*) AS customers FROM {FQ}.gold_customer_360 WHERE has_checking = 1 AND has_credit_card = 0"),
    ("What is the average number of active products per customer by segment?",
     f"SELECT segment, ROUND(AVG(active_products), 2) AS avg_active_products FROM {FQ}.gold_customer_360 GROUP BY segment ORDER BY segment"),
    ("How many affluent customers have a mortgage but no home equity line of credit?",
     f"SELECT COUNT(*) AS customers FROM {FQ}.gold_customer_360 WHERE segment = 'affluent' AND has_mortgage = 1 AND has_heloc = 0"),
    ("What is the total CLV by segment?",
     f"SELECT segment, ROUND(SUM(clv), 0) AS total_clv_usd FROM {FQ}.gold_customer_clv GROUP BY segment ORDER BY segment"),
    ("Which product is most often the next best product recommendation?",
     f"SELECT product, COUNT(*) AS customers FROM {FQ}.gold_cross_sell_recommendations WHERE recommendation_rank = 1 GROUP BY product ORDER BY customers DESC LIMIT 1"),
    ("How many customers have at least one recommendation?",
     f"SELECT COUNT(DISTINCT customer_360_id) AS customers FROM {FQ}.gold_cross_sell_recommendations"),
    ("Which 5 branches have the most total expected CLV uplift from next best product recommendations?",
     f"""SELECT home_branch_id, ROUND(SUM(expected_clv_uplift), 0) AS total_expected_clv_uplift_usd
FROM {FQ}.gold_cross_sell_recommendations WHERE recommendation_rank = 1
GROUP BY home_branch_id ORDER BY total_expected_clv_uplift_usd DESC LIMIT 5"""),
    ("What share of digitally enrolled customers hold 3 or more active products?",
     f"SELECT ROUND(AVG(IF(active_products >= 3, 1, 0)), 3) AS share_3plus FROM {FQ}.gold_customer_360 WHERE is_digitally_enrolled"),
    ("What is the average CLV of customers with 1 product compared with 3 products?",
     f"SELECT active_products, ROUND(AVG(clv), 0) AS avg_clv_usd FROM {FQ}.gold_customer_clv WHERE active_products IN (1, 3) GROUP BY active_products ORDER BY active_products"),
]


def hid(*parts):
    return hashlib.md5("|".join(parts).encode()).hexdigest()


def lines(text):
    """Genie stores text as a list of lines, each keeping its newline."""
    ls = text.splitlines(keepends=True)
    return ls if ls else [text]


def main():
    space = {
        "version": 2,
        "config": {"sample_questions": sorted(
            [{"id": hid("q", q), "question": [q]} for q in SAMPLE_QUESTIONS], key=lambda x: x["id"])},
        "data_sources": {"tables": [{"identifier": f"{FQ}.{t}"} for t in sorted(TABLES)]},
        "instructions": {
            "text_instructions": [{"id": hid("instructions"), "content": lines(INSTRUCTIONS)}],
            "example_question_sqls": sorted(
                [{"id": hid("ex", q), "question": [q], "sql": lines(s)} for q, s in EXAMPLE_SQL],
                key=lambda x: x["id"]),
        },
        "benchmarks": {"questions": sorted(
            [{"id": hid("bm", q), "question": [q], "answer": [{"format": "SQL", "content": lines(s)}]}
             for q, s in BENCHMARKS], key=lambda x: x["id"])},
    }
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "c360_analyst.geniespace.json")
    with open(out, "w") as f:
        json.dump(space, f, indent=2)
    print(f"wrote {out}: {len(TABLES)} tables, {len(SAMPLE_QUESTIONS)} sample questions, "
          f"{len(EXAMPLE_SQL)} example SQLs, {len(BENCHMARKS)} benchmarks")


if __name__ == "__main__":
    main()
