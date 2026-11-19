# Use case: next best product from a complete customer 360

**A regional bank, Banking.** Executive sponsor: EVP Data & Analytics. Domain owner: Chief Data Officer. Success metric: customer lifetime value (CLV).

All data in this prototype is synthetic. Markers: **[YOUR WORDS]** = rewrite in your own words; **[ASSUMPTION]** = a number we chose, to be confirmed; **[CHECK]** = an external fact to verify before presenting.

## 1. One-line outcome

[YOUR WORDS] Relationship bankers in 522 branches open one screen that shows each customer's full product picture and an explained next best product, lifting the cross-sell campaign response rate from **1.5% today to 4% or more**, worth about **$22M of illustrative lifetime value** at the bank's scale (section 6).

## 2. The problem, in the customer's words

[YOUR WORDS] "To see what a customer holds, a banker has to look up each account in the Bankwide Account Lookup Portal or go through the Power BI dashboards that each product line built for itself. Nothing tells them which product to offer next, so every offer is a guess. Our quarterly C-suite dashboard shows how many customers adopted each product, but not who should be offered what or why an offer worked."

**Quantified pain:** preparing one customer conversation takes about **15 minutes** across the portal and up to four product dashboards [ASSUMPTION]. With no predictive model, offers are untargeted, and the bank's cross-sell campaign response rate is **1.5%**. The bank cannot tell which customers were likely to buy, so it cannot aim its offers.

## 3. Why now

1. **Moving beyond descriptive BI.** The bank's own stated goal: move past dashboards to a predictive next best product and conversational questions on the data. The per-product dashboards run on an on-premises SQL Server with end-of-day batch loads. Each new question needs a new dashboard.
2. **Deposit and margin competition.** Digital banks and large national banks compete hard for deposits. Customers who hold several products stay longer and cost less to keep, so deepening relationships is a direct defense of margin [CHECK: cite a current industry source on primary-relationship retention].
3. **Explainable, governed targeting.** Any offer model must be explainable and auditable for fair-lending and consumer-protection review, and customer data access must be governed by role [CHECK: confirm which exam focus areas apply to this bank, for example fair lending and UDAAP]. Easier account switching under US open-banking rules raises the cost of a thin relationship [CHECK: status and compliance dates of the CFPB personal financial data rights rule, Section 1033].

## 4. Personas

| | EVP Data & Analytics (executive sponsor) | Chief Data Officer (domain owner) |
|---|---|---|
| What they must tell their committee | [YOUR WORDS] Quarterly product adoption by offering, with monthly adoption rates, from one consolidated Power BI dashboard. Today: what happened, not what to do next or why. | [YOUR WORDS] Whether customer data is trustworthy, governed and delivered fast enough to support growth. |
| How their team works today | Business analysts consume one dashboard per product line on on-prem SQL Server. | Four direct reports: Data Engineering, Data Governance, Platform Administration, Data Analytics. End-of-day batch from 4 systems; each product line owns its own extracts. |
| KPI they own | **Cross-sell campaign response rate** (1.5% today) and next best product adoption, rolling up to CLV | **Time to a governed, trusted customer view**; data quality pass rates; access controlled by role |
| Win at 6 months | Cross-sell campaign response rate of **4% or more**, or at least data-driven explanations of why offers succeed or fail | One governed 360 view serving bankers, analysts and the board from the same data |
| Stop at 6 months | Neither a response rate of 4% or more nor explanations | |

## 5. Today versus tomorrow

| | Today | Tomorrow |
|---|---|---|
| Customer view | Account-by-account lookup in the portal, plus up to four product dashboards | One customer 360 across core banking, loans, cards and digital, with records matched across systems |
| What to offer | No model; offers are untargeted | Next best product ranked by expected CLV uplift, with a plain-English reason and an opening question for the banker |
| Answering new questions | A new Power BI dashboard per question; quarterly descriptive totals | Analysts ask in plain language (Genie) and get governed answers in seconds |
| Learning what works | Adoption totals only; no record of what bankers offered or how customers responded | Bankers record each outcome in the app; it flows back for analysis of why offers succeed or fail |

## 6. Value hypothesis in customer lifetime value

[YOUR WORDS] All values are illustrative, built from the CLV assumptions in `DECISIONS.md` (product margins, retention of 85%, 90% and 94% for 1, 2 and 3 or more products, a 10-year horizon and an 8% discount rate) and the synthetic data. They are not a forecast.

| Value driver | Current baseline | Expected change | Assumption | Illustrative value |
|---|---|---|---|---|
| Cross-sell campaign response rate | **1.5%** today (bank figure) | **4% or more** with targeted, explained offers (the bank's win threshold) | [ASSUMPTION] each of the about 459,000 customers holding 2 products or fewer (35% of 1.3M, from the synthetic data) receives one targeted offer a year: (4.0% - 1.5%) x 459,000 = about 11,500 additional products | Volume behind the next row |
| Lifetime value of the additional products | | about 11,500 additional products a year | [ASSUMPTION] average CLV gain per added product **$1,900**, blended from the synthetic CLV by product count (1 to 2 products: +$1,400; 2 to 3: +$2,400) | **about $22M** lifetime value a year |
| Targeting strength | Offers today are untargeted | The 4% target needs about 2.7x today's response rate | The synthetic held-out test shows 8.2x top-decile lift, which real data will not match; 2.7x is the bar real data must clear | Evidence for the rows above, not added to them |
| Banker preparation time | About 15 minutes per customer conversation [ASSUMPTION] | About 3 minutes with one screen | 522 branches x 4 bankers x 5 prepared conversations a week [ASSUMPTION] | about 2,100 banker hours a week returned to selling (522 x 4 x 5 x 12 minutes; capacity, not cash) |
| Retention from deeper relationships | Included in CLV through the retention assumptions above | Moving from 2 to 3 products raises assumed retention from 90% to 94% | [ASSUMPTION] retention by product count | Already inside the $22M; not double counted |

## 7. The data

The bank's customer and product data sits in 4 operational systems, all end-of-day batch. The prototype uses synthetic versions of all 4.

| System | Tables | Rows at the bank (estimate) | Rows in the prototype (synthetic) | What is messy |
|---|---|---|---|---|
| Core banking | customers, deposit accounts | 1.3M customers, about 2.5M deposit accounts [ASSUMPTION] | 51,000 customer rows (50,000 people), 101,261 accounts | Re-exported duplicate rows (2%), negative balances, open dates in the future |
| Loans | loan customers, loans | about 0.6M loans [ASSUMPTION] | 24,888 customers, 34,022 loans | Its own customer ID; names in capitals; missing tax IDs; loans pointing at customers who do not exist; interest rates out of range |
| Cards | card customers, card accounts, card transactions | about 0.7M cards, about 20M transactions a month [ASSUMPTION] | 29,361 customers, 32,612 cards, 800,000 transactions | Its own customer ID and phone format; duplicates; cards with no product type or no known customer |
| Digital banking | users, events | about 0.8M users, about 30M events a month [ASSUMPTION] | 30,450 users, 1.22M events | No tax ID at all; old email addresses; moved ZIP codes; events with no user ID |

The same person appears under a different ID in every system, with small differences in name, email, phone and ZIP code. Matching them is the core of the 360 view.

## 8. How the six stages serve the story

- **Lakeflow:** lands the end-of-day files from four systems as they arrive, removes duplicates, quarantines bad rows with the rule they broke, and matches each person across systems into one customer 360. For the CDO, this replaces separate product-line extracts with one tested pipeline.
- **Unity Catalog:** governs the 360 view by role. Analysts see every customer with names, email and date of birth masked; bankers see full detail only for their branches. Lineage, tags and comments make it auditable. For the CDO, one access policy instead of one per dashboard.
- **ML and GenAI:** a propensity model scores every customer for each product they do not hold, ranked by expected CLV uplift. A foundation model turns the facts behind each top recommendation into a short reason and an opening question. For the CDO, a predictive capability that is explainable, as fair-lending review requires.
- **Lakebase:** serves the 360 view and recommendations to the app with fast lookups, and stores each banker's recorded outcome as a transaction, under Postgres row-level security by branch. For the CDO, the operational store that closes the loop.
- **Genie:** lets the EVP's analysts ask about adoption, CLV, recommendations and banker outcomes in plain language, with tested answers. For the CDO, it moves past the quarterly descriptive dashboard and answers why offers succeed or fail.
- **Databricks App:** the relationship banker's screen: my book, the customer 360 profile, the next best product with its reason, and recording what happened. For the CDO, the point where the data changes a customer conversation.

## 9. What we will NOT build

- CRM data, campaign management or outbound offer delivery (email, SMS, call lists).
- Real-time or streaming ingestion; the bank's systems are end-of-day batch.
- Replacing the existing Power BI dashboards.
- A production model lifecycle (automatic retraining, drift monitoring, champion and challenger testing).
- A formal fair-lending or model-risk review; the design supports one but does not perform it.
- Production identity groups. The prototype uses an entitlement table because its workspace cannot create account-level groups.
- Pricing, rate offers or credit decisions.
- Real customer data of any kind.
