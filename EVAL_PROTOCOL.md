# Evaluation protocol: cross-sell propensity model

**Written and committed 2026-11-19, before the out-of-time test below was run.**

Honesty note: model versions v1 to v6 were trained and evaluated on 2026-11-18, before this protocol existed, using a 25% held-out set of customers (results in `evidence/04_ml.txt` and `BUILD_LOG.md`). Those results stay on record unchanged. The out-of-time test defined here has never been run on any version. Any change to this protocol after today is added as a dated note at the end; the original text and any results stay.

## Question

Does the next best product model find customers likely to open a product well enough to support the bank's win threshold: a cross-sell campaign response rate of 4% or more, from 1.5% today (`USE_CASE.md`)?

## Data and timing rule

- Snapshots S = 2026-03-05, 2026-05-04, 2026-07-03, 2026-09-01 (60 days apart; data as of 2026-10-31).
- For each snapshot, one row per (customer, product the customer did not hold at S). Label = the customer opened that product in (S, S + 60 days].
- **Timing rule:** every feature, for the model and for the baseline, uses only data on or before S: holdings opened on or before S, digital events in the 90 days up to S, card spend in the 365 days up to S, tenure and age at S. Nothing after S is used except the label.

## Held-out data

1. **Out-of-time (main):** train on the three oldest snapshots (2026-03-05, 2026-05-04, 2026-07-03). Test on the newest (2026-09-01 to 2026-10-31). The test window is never seen in training.
2. **Out-of-customer (secondary):** within the out-of-time test, report results separately for customers who never appear in training as well.

## Simple baseline

What a capable analyst could do without a model: for each (customer, product) pair, score = product page views in the 90 days up to S, with ties broken by the product's overall opening rate in training. Same rows, same timing rule.

## Main measure

**Top-decile lift on the out-of-time test:** the opening rate among the 10% of test rows with the highest score, divided by the opening rate across all test rows. Reported overall and per product, with the number of positives.

Supporting measures: AUC overall and per product; top-decile lift of the baseline; the same measures on the out-of-customer subset.

## Success bar (decided before results)

The model supports a targeting claim only if both hold on the out-of-time test:

1. Top-decile lift **2.7x or more** (the uplift needed to go from a 1.5% response rate to 4%).
2. Top-decile lift at least **20% higher than the simple baseline's** (model lift / baseline lift >= 1.2).

## What means no claim

- If either condition fails, we state that the model does not support a targeting claim and do not present the 4% path as evidenced.
- Per-product results with fewer than 30 positives in the test window are reported but not used for any claim.
- Synthetic data: even if both conditions hold, the claim is "the method clears the bar on synthetic data". Real-data performance will be lower, and the bank's 4% target is measured on real campaigns at 6 months.

## GenAI explanations (evaluated separately)

- Rule checks on every explanation (built): no percentages, no dollar amounts that are not in the facts, no offers or rates, no mention of models or scores, Why/Opener format.
- LLM judge (MLflow GenAI evaluation) on a random sample of 200 explanations: grounded in the facts given, relevant to the product, includes a non-pushy opening question.
- **Bar:** 95% or more of the sample passes groundedness and 90% or more passes every judge check. Below that, the explanations are not presented as reliable.

## Where results go

`evidence/10_eval_protocol.txt` (model) and `evidence/11_genai_judge.txt` (explanations), produced by the jobs in `BUILD_PLAN.md`.

## Change notes

- **2026-11-19, GenAI explanations, after judge run 1.** Run 1 (200 sampled explanations, judge databricks-claude-sonnet-5-5): grounded 93.5% (bar 95%, not met), all checks 92.0% (bar 90%, met). Result kept in `evidence/11_genai_judge_run1.txt`. Change: the explanation prompt now forbids inferences about creditworthiness, income, capacity, needs or life events, and asks for fewer words when facts are thin. The bars, judge model, guidelines and sample (same 200 customers, same seed) are unchanged. Run 2 is reported next to run 1, not instead of it.
