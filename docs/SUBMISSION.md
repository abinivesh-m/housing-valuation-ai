# Submission note

**Hero Housing Fintech Challenge — Problem Statement 1: AI-Powered Digital Property Valuation Engine**
E-Cell IIT Bombay × Hero Housing Finance · submission deadline 12 November 2026

- **Live product:** https://housing-valuation-ai.vercel.app
- **Repository:** https://github.com/abinivesh-m/housing-valuation-ai (MIT, public)
- **API docs:** https://housing-valuation-ai.vercel.app/docs

---

## 1. What the brief asks, and what this submission does

The problem statement asks for an AI/ML engine that estimates fair market value for **residential
and commercial** property **across India**, using transaction data, government records, satellite
imagery, geo-spatial information, market trends and property attributes — with **reliable,
explainable and scalable** outputs. This table maps each clause to a concrete, verifiable artefact.
It is a mapping to the published brief, not a claim about a private judging rubric.

| Brief requirement | Where it is answered | Status |
|---|---|---|
| AI/ML valuation engine | 320-tree Huber gradient booster on `log(price)`, pure-numpy inference | **Live** |
| Residential property | Apartment, Villa, Independent House, Studio, Penthouse | **Live**, covered |
| Commercial property | Commercial Office, Retail Shop, Warehouse | **Live**, with a separate per-type conformal band and a commercial policy flag |
| Across India | 8 cities, 64 micro-markets | **Live**; expansion path documented |
| Transaction data | Comparable-sales engine: 3,000-row pool, 12 km radius, adjustment grid, recency weighting | **Live** on the prototype corpus; registry feed **planned** |
| Government records | Circle/guidance rates, registry deeds, ULPIN parcel identity | **Planned** — specified in `DATA_STRATEGY.md` §3, not faked |
| Satellite imagery | Built-up-area validation via Sentinel-2 / Open Buildings | **Planned** — the largest known accuracy lever, stated as a gap in `MODEL_CARD.md` |
| Geo-spatial information | Live OpenStreetMap overpass density within 1.5 km; haversine comparable filter | **Live** |
| Market trends | Recency adjustment in the comps grid; time-drift monitoring plan | Partially live (comps), partial (index) |
| Property attributes | 20 features: 6 categorical, 14 numeric | **Live** |
| Reliable | 79.1% empirical coverage for a nominal 80% band; deterministic outputs; 29 tests | **Live and measured** |
| Explainable | Exact baseline-substitution attribution in ₹, plus an independent comparable cross-check | **Live** |
| Scalable | Stateless inference, 55 ms warm, 24-property batch, no database | **Live** |

---

## 2. The honest headline

| Model (identical 1,200 holdout rows) | MAPE | R² | Within ±10% |
|---|---|---|---|
| Global median ₹/sqft × area | 42.08% | 0.346 | 15.8% |
| Locality × type median ₹/sqft rate card | 12.86% | 0.945 | 47.2% |
| Ridge hedonic regression, same features | 25.99% | 0.679 | 26.3% |
| **This engine** | **11.16%** | **0.944** | **54.3%** |

- **Unseen micro-market (GroupKFold by locality): 23.5% MAPE.** Error roughly doubles when a locality
  has no training history. The engine lowers confidence and raises `UNSEEN_MICROMARKET` rather than
  hiding it.
- **Calibration:** 79.1% coverage vs 80% nominal; median p10–p90 width 35.2%.
- **Corpus:** a documented parametric synthetic generator, because no national redistributable
  transaction dataset exists in India. **These are within-corpus numbers and are presented as such.**

The margin over a locality rate card is real but modest: **−1.7 points of MAPE and +7.1 points of ±10%
hit rate**. The submission does not claim "significantly higher accuracy than existing AVMs"; proving
that requires the registry-transaction holdout described in `DATA_STRATEGY.md`.

---

## 3. Why this is a product, not a notebook

Three things most valuation prototypes omit, and this one ships:

### a. A decision, not just a number

```
AUTO_APPROVE_DESKTOP      straight-through, no valuer
APPROVE_WITH_CONDITIONS   accept with attached reason codes
REFER_PHYSICAL_VALUATION  desktop file cannot support a collateral decision
REFER_CREDIT              the issue is not only the property
```

Six named checks, eight machine-readable reason codes, an A–E risk grade, and a max-loan
recommendation computed against the **p10** value — not the point estimate.

### b. Attribution that reconciles

Every valuation returns the drivers in rupees, computed by baseline substitution and batched into a
single prediction pass. `log(value) − log(baseline) = Σ effects + residual`, and the residual
(interaction term) is reported rather than hidden. It is exact and model-agnostic, so it does not
depend on a second, approximate explainer.

### c. A tamper-evident trail

`hash = SHA-256(prev_hash | seq | ts | kind | ref | payload_digest)`. Every valuation and decision is
appended; `GET /api/audit/verify` recomputes the chain and reports the first broken link. Editing a
past valuation is detectable, not just discouraged.

---

## 4. Demo script (3 minutes)

Use this as the recording plan. Record at 1440×900 or larger, light UI, no browser chrome.

| Time | Screen | What to say |
|---|---|---|
| 0:00–0:20 | Landing / Valuation | "An Indian HFC prices collateral with a site visit and a valuer's judgement. That takes days, and the number is hard to audit. This engine answers three questions in 55 milliseconds." |
| 0:20–0:50 | Load the Koramangala sample | "Point value ₹2.08 crore, p10–p90 ₹1.78–2.41 crore, 87.9% confidence. The band is conformal — measured at 79.1% coverage on holdout, not a hand-set ±10%." |
| 0:50–1:25 | Drivers panel | "Every driver is in rupees and they add up. Location +₹X, size +₹Y, and the residual is reported. This is exact baseline substitution, not a sampled approximation." |
| 1:25–1:55 | Comparables table | "Eight sales within 12 km, each adjusted for age, floor, furnishing, size and market drift — from a grid that is deliberately independent of the model, so the cross-check is real." |
| 1:55–2:25 | Lending panel | "Auto-approve desktop, grade A. Push the loan to ₹1.5 crore and it becomes approve-with-conditions at grade B. Set a 95% LTV and it refers for physical valuation, with the reason code." |
| 2:25–2:45 | Governance | "Every call is hash-chained. Verify recomputes the chain. Tamper with one line and it names the exact sequence number that broke." |
| 2:45–3:00 | Model & data | "11.16% MAPE against 12.86% for the locality rate card, 23.5% on unseen micro-markets, and the corpus is synthetic — the data plan is in the repo, not in a promise." |

**Do not skip the synthetic-corpus sentence.** It is the single strongest credibility signal in the
submission, and a judge who finds it unaided will discount everything else.

---

## 5. Likely judge questions, answered

**"Your data is synthetic. Why should we believe any number?"**
You shouldn't believe them as market accuracy — and the submission doesn't ask you to. The synthetic
corpus is a test fixture for the *system*: feature contract, calibration, attribution, comparable
reconciliation, policy, audit. Every metric is labelled within-corpus. The production plan names the
registry sources, the label-quality problems (circle-rate anchoring, delayed registration, area
definitions) and the validation protocol (out-of-time, grouped, geographic holdout, rolling
conformal). The honest claim is "the engine is ready for a real feed and here is exactly what that
feed must satisfy."

**"Why not scrape 99acres or MagicBricks?"**
Terms of service, and asking prices are not sale prices. A model trained on listing prices learns
seller optimism, not market value.

**"How is this different from a locality rate card?"**
The rate card is the benchmark, and it is strong: 12.86% MAPE. This engine gets 11.16%, but the
larger difference is what it produces around the number — a calibrated interval, rupee attribution,
an independent comparable reconciliation, and a policy decision. A rate card cannot refer a file for
inspection because its comparables disagree with its model.

**"How does it scale to 500 cities?"**
A new micro-market needs a coordinate and a locality label; the model falls back to city behaviour and
flags `UNSEEN_MICROMARKET`. A new city needs a training slice. Inference is stateless and O(trees ×
depth) per property — 55 ms — so scale is a data-coverage problem, not a compute problem.

**"What does it cost per valuation?"**
Model compute is negligible. The real cost is the registry lookup, which is contractual and
state-specific. That is why valuation and enrichment are separate calls: the lender pays for data only
when it needs deed-level evidence, not on every page view.

**"What happens when the model is wrong?"**
The interval widens, confidence falls, the comparable cross-check diverges, and the policy refers the
file. The failure mode is a slower decision, not a silently wrong number. That is the design
objective.

**"Is this fair lending compliant?"**
No borrower attributes enter the model — not name, gender, religion, caste, or income. The policy is
applied to collateral and confidence only. Geographic error parity still needs monitoring on real
data; that is in the validation protocol, not claimed as done.

---

## 6. Deliverables checklist

| Item | Status |
|---|---|
| Deployed, publicly reachable product | ✅ https://housing-valuation-ai.vercel.app |
| Public repository with MIT licence | ✅ https://github.com/abinivesh-m/housing-valuation-ai |
| README with architecture, metrics, API and run instructions | ✅ `README.md` |
| Model card, data strategy, lending policy, architecture | ✅ `docs/` |
| Reproducible training | ✅ `python data_gen.py && python train.py` |
| Test suite | ✅ 29 tests, `python -m pytest -q` |
| Screenshots in the repo | ✅ `docs/screenshots/` |
| 3-minute demo video | ⬜ to be recorded |
| Devpost / Unstop form | ⬜ to be submitted |

---

## 7. What is deliberately not claimed

- Not a certified valuation. Not a valuer's report.
- Not a credit decision. The engine never sees the borrower.
- Not validated on Indian market transactions. The corpus is synthetic and labelled as such.
- Not satellite-enabled. Built-up-area validation is specified and planned, not faked.
- Not a durable audit system. The hash chain is real; the storage is a demo.
- Not a title or fraud check. Encumbrance, litigation and document verification are out of scope.

Every one of those gaps is written down in the repository, with the fix and the phase it belongs to.
