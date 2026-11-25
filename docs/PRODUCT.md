# Product note

**HousingValuation AI — a reference implementation of an explainable, auditable
automated valuation model (AVM) for Indian residential and commercial property.**
Shipped as a runnable engine, a local agent skill, and an MCP server. Bring your
own transaction data.

- **Live product:** https://housing-valuation-ai.vercel.app
- **Repository:** https://github.com/abinivesh-m/housing-valuation-ai (MIT)
- **API reference:** https://housing-valuation-ai.vercel.app/docs

---

## 1. The problem it prices

An Indian housing finance company decides collateral value from a site visit and a valuer's
judgement. That takes days, scales with headcount, and produces a number that is hard to defend
eighteen months later when a file is reviewed.

An automated valuation model is only usable by a lender if it answers three questions for every
number it produces:

1. **What is this worth?** — a point estimate *and* an honest interval.
2. **Why?** — the drivers, in rupees, traceable to input fields.
3. **Can I act on it?** — a policy position: desktop decision, desk review, or physical inspection.

The engine answers all three and writes each answer to a hash-chained audit ledger.

---

## 2. What it returns

| Output | Detail |
|---|---|
| Point value | gradient-boosted trees on `log(price)`, 20 features over 6 categoricals and 14 numerics |
| Interval | **split-conformal** calibration on out-of-fold residuals — measured **79.1%** coverage against a nominal 80% |
| Attribution | **baseline-substitution** effects, exact and model-agnostic, in ₹ per driver group, with the interaction residual reported |
| Cross-check | **comparable sales** with an explicit adjustment grid and recency weighting, built independently of the model |
| Geo context | **OpenStreetMap Overpass** POI density within 1.5 km, degrading honestly when unavailable |
| Lending position | policy engine with RBI/NHB LTV bands, confidence haircut, six named checks, reason codes, A–E grade |
| Batch | up to 40 properties per call, with decision mix and straight-through rate |
| Governance | SHA-256 hash chain with a verification endpoint that names the first broken link |
| Latency | **55 ms median** per valuation (warm), single vCPU |

---

## 3. Accuracy, stated honestly

Measured on the holdout split of this project's corpus. **The corpus is synthetic** (see
[Data provenance](#5-data-provenance)); replicate with `python train.py`.

| Model (identical test rows) | MAPE | R² | Within ±10% |
|---|---|---|---|
| Global median ₹/sqft × area | 42.08% | 0.346 | 15.8% |
| **Locality × type median ₹/sqft × area** (the rate card most lenders run today) | **12.86%** | 0.945 | 47.2% |
| Ridge hedonic regression (same features) | 25.99% | 0.679 | 26.3% |
| **This engine — gradient boosting** | **11.16%** | **0.944** | **54.3%** |

- **Unseen micro-market test:** grouped 5-fold CV by locality → **23.5% MAPE** (worst fold 29.7%).
  Error roughly doubles when a locality has no training history, which is why the engine widens its
  interval and lowers confidence for unseen micro-markets instead of pretending otherwise.
- **Interval coverage:** 79.1% empirical p10–p90 coverage against a nominal 80%, median band width
  35.2%.

> The engine beats a locality × type rate card by **1.7 percentage points of MAPE** and **+7.1 points
> of ±10% hit rate** on this corpus. That is a real but modest margin, and it is the number this
> project measured — not a claim of "significantly higher accuracy than existing AVMs". Proving that
> requires the registry-transaction holdout described in [`DATA_STRATEGY.md`](DATA_STRATEGY.md).

---

## 4. Why this is a product, not a notebook

Three things valuation prototypes usually omit, and this one ships:

### a. A decision, not just a number

```
AUTO_APPROVE_DESKTOP      straight-through, no valuer
APPROVE_WITH_CONDITIONS   accept with attached reason codes
REFER_PHYSICAL_VALUATION  desktop file cannot support a collateral decision
REFER_CREDIT              the issue is not only the property
```

Six named checks, eight machine-readable reason codes, an A–E risk grade, and a maximum-loan
recommendation computed against the **p10** value — not the point estimate.

### b. Attribution that reconciles

Every valuation returns the drivers in rupees, computed by baseline substitution and batched into a
single prediction pass. `log(value) − log(baseline) = Σ effects + residual`, and the residual
(interaction term) is reported rather than hidden. It is exact and model-agnostic, so it does not
depend on a second, approximate explainer.

### c. A tamper-evident trail

`hash = SHA-256(prev_hash | seq | ts | kind | ref | payload_digest)`. Every valuation and decision
is appended; `GET /api/audit/verify` recomputes the chain and reports the first broken link. Editing
a past valuation is detectable, not merely discouraged.

---

## 5. Data provenance

**This build does not use licensed transaction data.** There is no public Indian property
transaction micro-dataset that can be redistributed, and inventing one would be the easiest way to
fail a diligence review.

The training corpus (`data_gen.py`) is a **documented parametric generator**: a multiplicative price
surface with hand-set coefficients for city level, locality index, property type, area elasticity,
age depreciation, floor premium, furnishing uplift, infrastructure distance decay, tenure and
occupancy, plus log-normal market noise. Latitude and longitude for the 64 covered micro-markets are
approximate locality centroids, used so the geo-enrichment layer can be exercised against real
geography.

What this proves: the feature contract, the model, conformal calibration, attribution, comparable
reconciliation, lending policy and audit trail all work end to end and are ready to be pointed at a
real feed.

What it does **not** prove: real-world AVM accuracy.

One component *is* live external data: **OpenStreetMap POI density** via the Overpass API, queried at
valuation time asynchronously, so it can never block a valuation.

The production data plan — registry deeds, circle/ready-reckoner rates, satellite built-up area,
market indices — is in [`DATA_STRATEGY.md`](DATA_STRATEGY.md), with each source tagged by whether it
is live in this build or planned.

---

## 6. Product walkthrough

A three-minute recording plan, for a product page or a lender demo. Record at 1440×900 or larger,
light UI, no browser chrome.

| Time | Screen | What to say |
|---|---|---|
| 0:00–0:20 | Landing / Valuation | "An Indian HFC prices collateral with a site visit and a valuer's judgement. That takes days, and the number is hard to audit. This engine answers three questions in 55 milliseconds." |
| 0:20–0:50 | Load the Koramangala sample | "Point value ₹2.08 crore, p10–p90 ₹1.78–2.41 crore, 87.9% confidence. The band is conformal — measured at 79.1% coverage on holdout, not a hand-set ±10%." |
| 0:50–1:25 | Drivers panel | "Every driver is in rupees and they add up. Location +₹X, size +₹Y, and the residual is reported. This is exact baseline substitution, not a sampled approximation." |
| 1:25–1:55 | Comparables table | "Eight sales within 12 km, each adjusted for age, floor, furnishing, size and market drift — from a grid that is deliberately independent of the model, so the cross-check is real." |
| 1:55–2:25 | Lending panel | "Auto-approve desktop, grade A. Push the loan to ₹1.5 crore and it becomes approve-with-conditions at grade B. Set a 95% LTV and it refers for physical valuation, with the reason code." |
| 2:25–2:45 | Governance | "Every call is hash-chained. Verify recomputes the chain. Tamper with one line and it names the exact sequence number that broke." |
| 2:45–3:00 | Model & data | "11.16% MAPE against 12.86% for the locality rate card, 23.5% on unseen micro-markets, and the corpus is synthetic — the data plan is in the repository, not in a promise." |

**Do not skip the synthetic-corpus sentence.** It is the single strongest credibility signal in the
product, and a technical buyer who finds it unaided will discount everything else.

---

## 7. Design FAQ

**"Your data is synthetic. Why should anyone believe the numbers?"**
They shouldn't be read as market accuracy, and nothing here asks them to be. The synthetic corpus is
a test fixture for the *system*: feature contract, calibration, attribution, comparable
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
A new micro-market needs a coordinate and a locality label; the model falls back to city behaviour
and flags `UNSEEN_MICROMARKET`. A new city needs a training slice. Inference is stateless and
O(trees × depth) per property — 55 ms — so scale is a data-coverage problem, not a compute problem.

**"What does it cost per valuation?"**
Model compute is negligible. The real cost is the registry lookup, which is contractual and
state-specific. That is why valuation and enrichment are separate calls: the lender pays for data
only when it needs deed-level evidence, not on every page view.

**"What happens when the model is wrong?"**
The interval widens, confidence falls, the comparable cross-check diverges, and the policy refers the
file. The failure mode is a slower decision, not a silently wrong number. That is the design
objective.

**"Is this fair-lending compliant?"**
No borrower attributes enter the model — not name, gender, religion, caste or income. The policy is
applied to collateral and confidence only. Geographic error parity still needs monitoring on real
data; that is in the validation protocol, not claimed as done.

---

## 8. Commercial packaging

| Surface | Access | Purpose |
|---|---|---|
| `/api/*` | open | product tour, model card, console |
| `/api/v1/valuate`, `/api/v1/batch`, `/api/v1/usage` | `X-API-Key`, monthly quota | paid integration and agent skills |
| `skill/housing-valuation-india/` | self-contained, runs locally | drop-in wrapper for Claude Code, Codex and Cursor |
| `mcp_server.py` | stdlib only, runs locally | MCP server: 6 tools, used by Claude Desktop, Cursor, Codex, Zed |
| `ingest.py` | stdlib + pandas | bring-your-own-data adapter with validation report |

Metering, key handling and quota semantics are documented in the [README](../README.md#commercial-access).

---

## 9. Current state

| Item | Status |
|---|---|
| Deployed, publicly reachable product | ✅ |
| Public repository, MIT licence | ✅ |
| README with architecture, metrics, API and run instructions | ✅ |
| Model card, data strategy, lending policy, architecture | ✅ `docs/` |
| Reproducible training | ✅ `python data_gen.py; python train.py` |
| Test suite | ✅ `python -m pytest -q` |
| Metered `/api/v1` with per-key quota | ✅ |
| Agent-skill wrapper | ✅ `skill/` |
| MCP server (6 tools) | ✅ `mcp_server.py` |
| Bring-your-own-data adapter | ✅ `ingest.py` |
| Ready-reckoner anchor | ✅ `engine/ready_reckoner.py` (model-derived fallback, swappable) |
| Registry-transaction corpus | ⬜ phase 1 of the data plan |
| Satellite built-up-area check | ⬜ phase 2 of the data plan |
| Durable audit store | ⬜ production hardening |

---

## 10. What is deliberately not claimed

- Not a certified valuation. Not a valuer's report.
- Not a credit decision. The engine never sees the borrower.
- Not validated on Indian market transactions. The corpus is synthetic and labelled as such.
- Not satellite-enabled. Built-up-area validation is specified and planned, not faked.
- Not a durable audit system. The hash chain is real; the storage is a reference implementation.
- Not a title or fraud check. Encumbrance, litigation and document verification are out of scope.

Every one of those gaps is written down in the repository, with the fix and the phase it belongs to.
