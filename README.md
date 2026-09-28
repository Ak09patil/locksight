# RiskGate

[![Tests](https://github.com/Ak09patil/riskgate/actions/workflows/tests.yml/badge.svg)](https://github.com/Ak09patil/riskgate/actions/workflows/tests.yml)

A risk layer for AI-agent-initiated transactions. Built for Razorpay's AI Buildathon 2026, Track 2 (AI Risk Manager).

## Quick facts

Built and independently verified against a 284,807-transaction real-world dataset, benchmarked against 7 competing models, and stress-tested until it produced 18 real, fixed bugs — not a demo that happened to work once.

| | |
|---|---|
| Model | Logistic regression — tested against 7 alternatives (Random Forest, Gradient Boosting, XGBoost, LightGBM, SVM, Naive Bayes, KNN); wins on F2, competitive on AUC |
| Fraud-risk model | AUC ~0.72 (synthetic, cross-validated) · AUC 0.972 (validated on 284,807 real transactions) |
| Beats a naive rule | F2 0.699 vs. 0.045 — ~15x |
| Scores built | 4 — fraud-risk, intent-match, abuse-ring sentinel, fraud-spike detector — plus 1 heuristic (preference-fit) |
| Automated tests | 36, running in CI on every push |
| Real bugs found & fixed | 18, documented below with cause and fix |
| Load-tested throughput | ~220 req/sec, 0 errors, 1,000 requests at 50 concurrent |

## The problem

Razorpay is piloting AI agents that check out on a customer's behalf — Agent Studio, and the NPCI UAP pilot with Zomato, Swiggy, and Zepto. Every payment before this had one moment — a human typing a PIN — that did two jobs at once: stopped fraud, and caught honest mistakes, because the person looked once more before confirming. Agentic checkout removes that moment. Fraud detection still exists — Razorpay has Thirdwatch, 200+ signals. Job one is solved. Nobody's solving job two: catching a fully-authorized, non-malicious agent that still got the purchase wrong.

That gap — agent decision-quality risk — is what RiskGate targets. Not a second fraud detector. A signal category Thirdwatch's architecture, built for a world where a human always made the final call, wasn't designed to see. This is an inference from Thirdwatch's public description, not verified knowledge of its real feature set — stated as such.

## Model choice and the principles behind it

Logistic regression scores the fraud-risk model — tested against the field, not a default. `src/full_model_comparison.py` runs it against seven alternatives on identical data, features, split, and independently-tuned thresholds. Random Forest scores 0.005 higher AUC — smaller than this model's own seed-to-seed variance (std 0.025), so not treated as meaningful. On F2, the metric that actually sets the threshold, logistic regression is the single best model tested. Two automated tests guard both results. This holds at ~4,000 rows; more data generally favors more flexible models, so it's a staged decision — the comparison script reruns automatically and fails the build if that stops being true.

Four rules governed every decision in this build, the same way whether the decision was about a model or a line of UI copy: **explicit over opaque** (every score resolves to printable numbers with a stated reason, not a black box — the same core idea behind Anthropic's Constitutional AI approach, guiding a system by written, inspectable principles rather than an opaque preference); **test the claim, don't assert it** (every "why X over Y" has a script that ran the comparison); **self-critique and revise on a loop** (build, check against a stated standard, find the gap, fix the cause — repeated dozens of times, see "What broke"); **disclose limits as clearly as strengths** (every claim here has a stated boundary).

## Architecture and approach

The starting question wasn't "what model" — it was "what does this system need to be trusted with a real decision." Razorpay's own bar is that every money action be explainable and bounded. That ruled out black-box models and LLM-driven decisions before any accuracy comparison even started, and everything else followed from there.

**Three scores per transaction, not one:**
- **Fraud-risk** — is this a bad actor. Trained, validated below.
- **Intent-match** — did the purchase match what the customer asked for. Kept separate from fraud-risk on purpose: a bad actor needs blocking, an honest mistake needs a quick human nod, and one number can't hold both responses.
- **Preference-fit** — does this deviation match the customer's own history. Kept an honest heuristic, not a third trained model — no ground-truth label exists for "would this customer have preferred this," and training against a self-invented label would be false rigor. Tested directly (see "What broke") rather than assumed to work.

**The gate**, from these three: auto-approve, hold for a fraud analyst, hold for quick customer confirmation, or hold as a likely mistake. 39% of transactions get zero human involvement — the PIN genuinely replaced. Only 19% go back to the customer, only for real ambiguity; the rest goes to an analyst. The old PIN asked every time, blind to need. This only asks when needed.

**Circuit breaker**, alongside the three scores: any order over ~2x the largest value ever seen in training holds automatically, regardless of score. Added after a ₹4,00,000 grocery-order test sailed through as approved — training never taught the model that value existed, so the model has no real basis for an opinion there.

**Two more scores, built later and deliberately, genuinely different math each time:**
- **Abuse-ring sentinel** (`src/ring_detector.py`) — fraud-risk and intent-match look at one transaction at a time; a ring across several accounts is invisible to that. Links transactions sharing a pincode, fresh agents, tight time window; finds clusters via union-find. 92.3% precision, 100% recall on 15 injected rings; 0.07% false-positive rate on clean data.
- **Fraud-spike detector** (`src/spike_detector.py`) — time-series anomaly detection, not classification. Flags a time window if its fraud rate is far from typical, using median/MAD (not mean/std, since a real spike drags a mean-based baseline up too). 54.5% precision, 54.5% recall on 4 injected spikes — weaker than the ring detector, reported as-is.

**Where an LLM is used** — exactly once, `src/pattern_narrative.py`, and never for a decision. It phrases already-computed, deterministic pandas findings into a readable brief for an analyst. Detection stays plain groupby logic; no API key, no problem — a clean template covers the same facts.

**Why the shopping agent is simple, not agentic.** A multi-agent design and an LLM-driven negotiating agent were both cut. Multi-agent orchestration adds debugging surface to a part of the system that isn't the actual submission. The negotiating agent was cut for a sharper reason: it would have made RiskGate behave like a merchandising nudge, at odds with Razorpay's public identity as neutral infrastructure, not a recommendation business.

## Track alignment

This maps to all four of the track's named directions, and that's worth being direct about rather than letting it look like a checklist: it wasn't planned that way. Fraud-risk and intent-match came from one insight — the PIN did two jobs, agentic checkout removes both. The ring and spike detectors came later, as real extensions solving adjacent problems that came up during the build, not as boxes being ticked. Fraud-risk carries the real weight of this submission — the only score checked against a real external dataset, calibration-audited, fairness-audited, benchmarked against the full model field. The other three are genuinely validated too, at a lighter standard proportionate to their role as extensions, not three more attempts at the same depth. No chargeback responder was built: no ground-truth "did this evidence packet win the dispute" signal exists anywhere, so it can't be measured with real precision/recall, and building something untestable didn't seem right.

## The numbers

| Metric | Result |
|---|---|
| Fraud-risk CV AUC | ~0.72, stable across 5 seeds (std ~0.02) |
| Fraud-risk F2 | ~0.70 |
| Naive rule F2 (baseline) | 0.045 — model beats it ~15x |
| Real-data validation (284,807 real transactions) | AUC 0.972 |
| Calibration (Brier score) | 0.22 → 0.19 after Platt scaling |
| Geographic fairness — worst pincode disparity | 2.8x → 2.42x after shrinkage fix; spread tightened across all pincodes |
| False-positive rate at F2-optimal threshold | ~85% (why the live product gates at 0.5 instead, business-realistic) |
| Abuse-ring sentinel | 92.3% precision, 100% recall (15 injected rings), 0.07% FP on clean data |
| Fraud-spike detector | 54.5% precision, 54.5% recall (4 injected spikes) |
| Model comparison (7 alternatives) | Logistic regression: best F2 of all tested; AUC gap to best (Random Forest) within seed noise |
| Automated tests | 36 (17 unit, 19 integration), CI on every push |
| Load test | ~220 req/sec sustained, 0 errors at 1,000 requests / 50 concurrent |

## What broke

Three of these are worth reading in full, not just the compressed table below — they're the ones that actually show how this project was tested, not just what was found.

**The concurrency bug that passed twenty times, then failed anyway.** Five people confirming an outcome at close to the same moment silently lost four of the five records — while the system told all five it had succeeded. The first fix looked right and passed twenty times in a row in my own environment. It failed differently the moment I ran it on separate real hardware. The second fix — checking the file's actual size from the operating system instead of trusting a buffered stream position, which behaves differently across platforms — was verified thirty times on the machine that broke the first attempt, then again at a hundred simultaneous real HTTP requests before I trusted it.

**Watching my own demo, the UI caught itself lying.** The checkout screen labeled a match "within budget" even when the agent had explicitly picked something over budget because nothing else fit — a message that was simply wrong regardless of what had actually happened. Found by watching the product the way a stranger would, not by reading the code.

**The same duplication bug, found twice, at increasing scale.** Six files each hardcoded their own copy of the fraud feature list — found only because adding one new feature updated one copy and revealed the other five never got it. Fixed by centralizing the list. Months later, the identical pattern reappeared in a different form: eight files independently recomputing a pincode rate instead of sharing one function. Same root cause, same fix, found by explicitly searching for the pattern rather than assuming the first fix meant it couldn't happen again.

The full list, compressed:

| Bug | Found via | Fix |
|---|---|---|
| Data leakage — pincode-rate feature computed on full dataset, test rows included | Code review | Compute train-only, save as its own artifact |
| `gating.py` was a duplicate of `pipeline.py`'s logic — a threshold change updated one, not the other | Numbers stopped matching | Made `gating.py` a thin wrapper; one implementation |
| Same staleness bug, third occurrence, in a validation script | Systematic search after finding it twice | Import shared logic instead of duplicating |
| Preference-fit had ~zero real correlation with outcomes | Tested the correlation directly instead of assuming | Wired a real causal link in the data generator; verified (18% vs 9.5% mismatch rate) |
| Cross-platform `RuntimeWarning: overflow` during training | Only appeared on a second, real machine | Stronger regularization (C=0.1); found the same warning in 4 more files, fixed there too |
| `order_id` used `uuid.uuid4()` — not reproducible across reruns | A rebuilt dataset broke a recorded outcome lookup | Deterministic ID (`txn_{i:06d}`) |
| The `order_id` fix had its own bug — pandas read the zero-padded ID as an integer, stripping the padding | Checked dtype explicitly | Non-numeric prefix so pandas can't misread it |
| 6 files each hardcoded their own copy of the fraud feature list | Adding one feature required updating one copy, revealed the other 5 never got it | Import `FRAUD_FEATURES` from one place everywhere |
| Same duplication pattern again — 8 files independently recomputing pincode rate | Found while adding the shrinkage fix | Centralized into one shared function |
| `/score` and `/full_loop` crashed on empty/malformed input | Deliberate malformed-input testing | Added real input validation, clean error responses |
| Fraud queue's approve/reject buttons had no double-click protection | Reviewed for race conditions | Added disable-while-pending pattern |
| A broken JS comment silently killed the dashboard's interactivity | A real click did nothing | Fixed; added a real syntax check to the process |
| `HOLD_CONFIRM_WITH_HUMAN` / `HOLD_LIKELY_MISMATCH` finalized the order before explaining why — "confirmation" confirmed nothing | Asked directly why two outcomes existed if neither let the customer decide | Real pre-purchase gate; `HOLD_FRAUD_REVIEW` kept non-self-clearable |
| Concurrent writes to the outcomes log: 5 simultaneous requests, 4 records silently lost, system reported success to all 5 | Deliberate concurrency test | First fix (`f.tell()`) passed 20x sandbox, failed on real hardware; second fix (`os.fstat()`) verified 30x on that machine, then at 100 concurrent real HTTP requests |
| Negative/zero prices silently accepted and scored, one case auto-approved | Deliberate adversarial-input test | Explicit validation on both endpoints; found the same gap existed calling the shopping agent directly, fixed at the function itself |
| XGBoost's package installs via pip but its compiled internals need a library macOS doesn't ship by default | Crashed on a second machine, not the dev one | Broadened exception handling to the real failure type; fixed the accompanying test's shallow pre-check too |
| Committed model trained with a different scikit-learn version than a fresh install pulls | Fresh-clone test on the actual public repo | Pinned the dependency version |
| Checkout UI labeled an over-budget match "within budget"; customer asked to confirm before seeing any risk info, reasoning shown only after | Watching my own demo | Fixed the message; same screen now shows product and reasoning together, before the decision |

## Business case and scale

**Money, not just metrics** (`src/cost_sensitivity.py`) — every assumption stated, none hidden in a formula. At this project's real order values, fraud loss prevented outweighs revenue put at risk by false holds, at every threshold tested — directionally robust regardless of the exact illustrative volume or abandonment-rate assumption, since a caught fraud is a full order value and a false hold is a small fraction of one. Swap in Razorpay's real AOV, volume, and fraud rate and the same formula gives the real number.

**Load test** (`src/load_test.py`) — real concurrent HTTP requests against the live API, not a claimed number: ~220 req/sec sustained, 0 errors at 1,000 requests / 50 concurrent, on a single unoptimized process. This tests whether the architecture holds under load — a separate, honestly narrower question than whether model accuracy holds at real volume, which needs real data this project doesn't have.

## What I know is still missing

Every UX decision — confirmation-screen wording, whether "propose, then ask" is right for a borderline case — was reasoned from my own judgment, never tested against a real person; proper UX validation needs real users, which a solo submission on this timeline doesn't have. Every synthetic-data claim carries that limitation directly, which is exactly why the real-data validation exists. True cross-browser testing wasn't performed — every check was done in Safari; the JS used should be safe on any current browser, but that's reasoned confidence, not verified confidence.

## What I'd build next

- Replace synthetic fraud data with real dispute/return outcomes, re-derive both models empirically.
- Integrate real agent-authorization scope objects (UAP/AP2-style mandates) instead of conflating authorization with stated intent.
- Run RiskGate in shadow mode against Thirdwatch's real traffic before trusting any autonomous gating.
- Build a chargeback-evidence responder — deliberately not built here, since it can't be measured with real precision/recall the way everything else was.

## Running it

```
pip install -r requirements.txt
python3 src/generate_data.py
python3 src/train_fraud_model.py
python3 src/train_intent_model.py
python3 src/gating.py
python3 src/build_dashboard_data.py
python3 src/embed_dashboard_data.py
python3 src/api.py          # live API on localhost:5050
```

Open `dashboard/index.html` (operator view) or `demo/checkout.html` (consumer flow) — both work standalone from sample data, both switch to live scoring once `src/api.py` is running.

Every validation script, runnable directly:

```
python3 src/seed_validation.py
python3 src/drift_test.py
python3 src/baseline_comparison.py
python3 src/real_data_validation.py
python3 src/calibration_check.py
python3 src/fairness_check.py
python3 src/cost_sensitivity.py
python3 src/model_complexity_comparison.py
python3 src/full_model_comparison.py
python3 src/ring_detector.py
python3 src/spike_detector.py
python3 src/load_test.py       # needs src/api.py running first
```

Full test suite: `pytest tests/ -v`

`docs/ARCHITECTURE.md` structures this same reasoning against the buildathon's own four judging criteria. `TESTING.md` has the complete, unfiltered bug log.
