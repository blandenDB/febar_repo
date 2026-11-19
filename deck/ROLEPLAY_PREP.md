# AI role-play prep

The role-play is a conversation with the bank's EVP Data & Analytics and Chief Data Officer. Answers are yours: every **[YOUR WORDS]** line is for you to write. The **evidence** column tells you what in this repo backs the answer, so you can cite a real number instead of a claim.

## 1. Likely questions

| # | Question | What backs your answer | Your answer |
|---|---|---|---|
| 1 | What exactly changes for my bankers on Monday? | App screens: My book, Customer 360, record outcome (`README.md`, `evidence/08_app_test.txt`) | [YOUR WORDS] |
| 2 | How do you get to 4% from 1.5%? | Needs about 2.7x targeting lift; out-of-time test shows 8.2x on synthetic data (`USE_CASE.md` s6, `evidence/10_eval_protocol.txt`) | [YOUR WORDS] |
| 3 | Where does the $22M come from? | (4.0% - 1.5%) x 459,000 x $1,900, all assumptions labeled (`USE_CASE.md` s6) | [YOUR WORDS] |
| 4 | How do I know the customer view is right? | Duplicates and quarantine reconcile to planted counts; matching precision 1.0 vs ground truth (`evidence/02_pipeline.txt`) | [YOUR WORDS] |
| 5 | Who can see customer names? | Analysts: masked; bankers: own branches only; no entitlement: nothing (`evidence/03_governance.txt`, `evidence/12_access_test.txt`) | [YOUR WORDS] |
| 6 | Can a regulator see why a customer got an offer? | Facts behind each recommendation are stored; explanations use only those facts; judge checks groundedness (`evidence/05_genai.txt`, `evidence/11_genai_judge.txt`) | [YOUR WORDS] |
| 7 | What if the explanation says something wrong? | Judge missed twice and was fixed; strict no-inference rule; banker sees the facts beside the text (`evidence/11_genai_judge*.txt`) | [YOUR WORDS] |
| 8 | How do my analysts use this without new dashboards? | Genie space, 10/10 benchmarks, answers on banker outcomes (`evidence/07_genie.txt`, `evidence/09_feedback_loop.txt`) | [YOUR WORDS] |
| 9 | How do we learn which offers work? | Outcomes recorded in the app flow to UC and Genie (`evidence/09_feedback_loop.txt`) | [YOUR WORDS] |
| 10 | Does this replace our Power BI? | Out of scope; Power BI stays (`USE_CASE.md` s9) | [YOUR WORDS] |
| 11 | Our systems are end-of-day batch. Does that work? | One job daily at 06:00 after the batch window (`evidence/00_setup.txt`) | [YOUR WORDS] |
| 12 | What does my data engineering team maintain? | One bundle, one pipeline in SQL, one job (`README.md` repository table) | [YOUR WORDS] |
| 13 | What does it cost to run? | Serverless throughout; daily run about 18 minutes; LLM calls for about 6,900 explanations a day [CHECK cost estimate before quoting] | [YOUR WORDS] |
| 14 | Why Databricks rather than Power BI plus Azure ML? | One governed platform for pipeline, access policies, serving store with write-back, conversational AI and the app (`README.md`) | [YOUR WORDS] |
| 15 | What do you need from us to start a pilot? | Win and stop criteria (`USE_CASE.md` s4); limits (`README.md`) | [YOUR WORDS] |

## 2. Hard objections, and what is honest to say

| Objection | Honest facts | Your answer |
|---|---|---|
| "This is synthetic data. Why should I believe 8.2x?" | You should not expect 8.2x. The bar real data must clear is about 2.7x. The protocol was set before the test, and the model beat a simple baseline by 27% (`EVAL_PROTOCOL.md`, `evidence/10_eval_protocol.txt`). | [YOUR WORDS] |
| "The lift looks too good to be true." | Synthetic browsing signals are clean; the simple baseline alone reaches 6.5x. The meaningful number is the 1.27x over that baseline. HELOC is excluded for too few positives. | [YOUR WORDS] |
| "Why do I need Lakebase? Read the warehouse." | The app writes outcomes as transactions and needs fast single-customer lookups; branch security is enforced again in Postgres (`evidence/06_lakebase.txt`). | [YOUR WORDS] |
| "An entitlement table is not how we manage access." | Correct for production: use account-level groups. The prototype workspace cannot create them; the masks and filters are written so groups can replace the table (`DECISIONS.md`). | [YOUR WORDS] |
| "Your file trigger did not work. Is this production-ready?" | It is a prototype. The trigger never evaluated in this workspace; a schedule after the batch window is reliable and documented (`DECISIONS.md`, `BUILD_LOG.md`). | [YOUR WORDS] |

## 3. Practice script

**Opening (about 30 seconds).** [YOUR WORDS] Who you are, the problem in one sentence, the outcome in one number.

**Demo path (about 3 minutes, synthetic data):**

1. App, **My book**: the branch pie and the next best product chart; click a product to filter. Say what the banker sees first.
2. Click a customer row to open **Customer 360**: products held, balances, the next best product with its "Why" and "Opener", and the facts behind it.
3. **Record an outcome** (for example, follow up later) and save.
4. **Genie**: ask "How have bankers responded to recommendations so far, by product and outcome?" and show the answer includes the outcome you just recorded (after the feedback copy runs).
5. If asked about trust: show a masked analyst view (`evidence/03_governance.txt`).

**Close (about 30 seconds).** [YOUR WORDS] The ask, and what the 6-month win and stop look like.

## 4. Before the role-play

- [ ] Every [YOUR WORDS] answer written and said out loud once.
- [ ] The [CHECK] on cost resolved, or say you will follow up.
- [ ] The app opened and one outcome recorded the day before, so the demo path works.
- [ ] Feedback copy job run after recording, so Genie can see the outcome.
