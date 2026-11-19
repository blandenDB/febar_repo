# Business deck outline (problem-led, about 10 slides)

Audience: the EVP Data & Analytics (sponsor) and the Chief Data Officer (domain owner) of a regional bank. Format: Google Slides on the Databricks template, exported to `deck/deck.pdf`.

Starter deck (2026-11-19): built from `deck/deck_spec.json` as Google Slides (private to the author) and exported to `deck/deck.pdf`. Every slide's text and speaker notes are an AI-drafted starting point, marked DRAFT in the notes; rewrite them in your own words. Screenshots for slide 6 are in `deck/screens/` (synthetic customers, sidebar excluded).

How to use this file: each slide lists its **job**, a **[YOUR WORDS]** line for you to write, the **facts** you can draw on (all from this repo, with the source), and a **visual**. Slide text and the narrative are yours; the facts are there so every number is backed. When a slide is ready, replace its [YOUR WORDS] line and I will build it.

---

## 1. Title

- **Job:** name the outcome, not the technology.
- **[YOUR WORDS]** Title and one-line subtitle.
- **Facts:** 1.5% cross-sell response today, 4% or more is the 6-month win (`USE_CASE.md` section 1).
- **Visual:** title slide; small "synthetic data prototype" note.

## 2. The problem, in their words

- **Job:** make the CDO nod: "that is us".
- **[YOUR WORDS]** The quote and the one quantified pain.
- **Facts:** account lookup portal plus one Power BI dashboard per product line on on-prem SQL Server; about 15 minutes to prepare one customer conversation [ASSUMPTION]; no predictive model, so offers are untargeted; 1.5% response (`USE_CASE.md` section 2).
- **Visual:** a banker's screen today: portal + four dashboards, a question mark over "what to offer".

## 3. Why now

- **Job:** urgency for this year.
- **[YOUR WORDS]** Two or three pressures, in order of what this bank feels most.
- **Facts:** the bank's goal to move past descriptive BI to prediction and conversational AI; deposit and margin competition [CHECK]; explainable, governed targeting for fair-lending review [CHECK]; open-banking switching [CHECK] (`USE_CASE.md` section 3). Resolve every [CHECK] before presenting.
- **Visual:** three short tiles.

## 4. Today versus tomorrow

- **Job:** the change in one picture.
- **[YOUR WORDS]** Which of the four rows to lead with.
- **Facts:** customer view, what to offer, answering new questions, learning what works (`USE_CASE.md` section 5).
- **Visual:** two-column table, four rows.

## 5. What we built (the journey)

- **Job:** show it is one connected platform, not six demos.
- **[YOUR WORDS]** One sentence per stage on what it does for the CDO.
- **Facts:** four systems, Lakeflow, Unity Catalog, ML and GenAI, Lakebase, Genie, App; one job with 12 tasks, daily at 06:00 (`README.md`, `evidence/00_setup.txt`).
- **Visual:** left-to-right flow with the six stage icons; the feedback arrow from the app back to Genie.

## 6. Demo: a banker's morning

- **Job:** make it real in three screens.
- **[YOUR WORDS]** The customer you will open and the line you will say.
- **Facts:** My book (branch pie, product chart, table); Customer 360 with the "Why" and "Opener"; record the outcome; Genie answering "how have bankers responded?" (`evidence/09_feedback_loop.txt`). Use a synthetic customer.
- **Visual:** three screenshots (for the deck only; evidence stays text).

## 7. Value in customer lifetime value

- **Job:** a number with its assumptions on the same slide.
- **[YOUR WORDS]** Which number you will stand behind, and how you will say "illustrative".
- **Facts:** (4.0% minus 1.5%) x about 459,000 customers with 2 products or fewer, one targeted offer a year [ASSUMPTION] = about 11,500 added products x $1,900 average CLV gain [ASSUMPTION] = about $22M lifetime value a year; banker time about 2,100 hours a week returned (capacity, not cash) (`USE_CASE.md` section 6).
- **Visual:** a small value table: driver, baseline, change, assumption, value.

## 8. Proof it works (and how we judged it)

- **Job:** credibility: rules set before results, misses kept.
- **[YOUR WORDS]** How you explain "the bar was set before the test".
- **Facts:**
  - Model, out-of-time test: top-decile lift 8.2x, 1.27x a simple page-view baseline; bars 2.7x and 1.2x set before the test (`evidence/10_eval_protocol.txt`, `EVAL_PROTOCOL.md`).
  - Explanations: judge runs 93.5% then 97% grounded; passed on the third run (97% grounded, 95% all checks) after two documented fixes (`evidence/11_genai_judge.txt`).
  - Genie: 8/10, 8/10, then 10/10 benchmarks (`evidence/07_genie.txt`).
  - Data: duplicates and quarantine reconcile with what was planted; matching precision 1.0 (`evidence/02_pipeline.txt`).
- **Visual:** four proof tiles, each with its bar and result.

## 9. Governance and risk

- **Job:** answer the CDO's first worry before they ask.
- **[YOUR WORDS]** The one sentence on trust you want them to remember.
- **Facts:** analysts see all customers with identifiers masked; bankers see only their branches; proven with a non-admin service principal; access enforced again in Postgres; explanations use only listed facts, no inferences about creditworthiness (`evidence/03_governance.txt`, `evidence/12_access_test.txt`, `evidence/06_lakebase.txt`).
- **Visual:** persona x data matrix (analyst, banker, no access).

## 10. Path to the 6-month win and the ask

- **Job:** what happens next and what you need from them.
- **[YOUR WORDS]** The ask (for example: pilot branches, a real campaign, data access).
- **Facts:** win = 4% or more response, or data-driven explanations of why offers succeed or fail; stop if neither (`USE_CASE.md` section 4); real data needs about 2.7x lift (`USE_CASE.md` section 6); limits (`README.md`).
- **Visual:** a 6-month timeline: pilot, measure, scale or stop.

---

## Before building the slides

- [ ] Every [YOUR WORDS] line replaced.
- [ ] Every [CHECK] on slide 3 verified or removed.
- [ ] Numbers match `USE_CASE.md` and the evidence files.
- [ ] No real customer, person or internal system names; synthetic customers only.
