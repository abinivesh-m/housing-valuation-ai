# HousingValuation AI

**An explainable automated valuation engine for Indian residential and commercial property, with a risk-based lending layer and a tamper-evident audit trail.**

Built for the **Hero Housing Fintech Challenge — Problem Statement 1: AI-Powered Digital Property Valuation Engine for India**.

- **Live engine:** https://housing-valuation-ai.vercel.app
- **API reference:** https://housing-valuation-ai.vercel.app/docs
- **License:** MIT

---

## Why this exists

Indian mortgage lending still leans on physical site visits and valuer judgement for most collateral
decisions. That caps throughput, adds days to turnaround, and produces valuations that are hard to
audit after the fact. An automated valuation model (AVM) is only usable by a lender if it can answer
three questions for every single number it produces:

1. **What is this worth?** — a point estimate *and* an honest interval.
2. **Why?** — the drivers, in rupees, traceable to input fields.
3. **Can I act on it?** — a policy position: desktop decision, desk review, or physical inspection.

This engine answers all three, and writes each answer to a hash-chained audit ledger.

---

## What it does

| Capability | Implementation |
|---|---|
| Valuation | Gradient-boosted trees on `log(price)`, 20 features over 6 categoricals and 14 numerics |
| Uncertainty | **Split-conformal** calibration on out-of-fold residuals — measured **79.1%** coverage against a nominal 80% |
| Explainability | **Baseline-substitution attribution** — exact, model-agnostic, reproducible, in ₹ per driver group |
| Cross-check | **Comparable-sales engine** with an explicit adjustment grid and recency weighting |
| Geo features | **Live OpenStreetMap Overpass** POI density within 1.5 km, degrades honestly when unavailable |
| Lending | Policy engine with RBI/NHB LTV bands, confidence haircuts, 6 named checks, reason codes, risk grade |
| Scale | Batch endpoint — 24-property book scored in a single request |
| Governance | Hash-chained audit ledger with a verification endpoint that detects tampering |
| Latency | **55 ms median** per valuation (warm), single vCPU |

---

## Accuracy — stated honestly

These are measured on the holdout split of this project's corpus. **The corpus is synthetic**
(see [Data provenance](#data-provenance)); replicate with `python train.py`.

| Model (identical test rows) | MAPE | R² | Within ±10% |
|---|---|---|---|
| Global median ₹/sqft × area | 42.08% | 0.346 | 15.8% |
| **Locality × type median ₹/sqft × area** (the rate card most lenders run today) | **12.86%** | 0.945 | 47.2% |
| Ridge hedonic regression (same features) | 25.99% | 0.679 | 26.3% |
| **This engine — gradient boosting** | **11.16%** | **0.944** | **54.3%** |

- **Unseen micro-market test:** grouped 5-fold CV by locality → **23.5% MAPE** (worst fold 29.7%).
  Error roughly doubles when a locality has no training history. That gap is the reason the engine
  widens its interval and lowers confidence for unseen micro-markets instead of pretending otherwise.
- **Interval coverage:** 79.1% empirical p10–p90 coverage, nominal 80%, median band width 35.2%.

> The engine beats a locality × type rate card by **1.7 percentage points of MAPE** and **+7.1 points
> of ±10% hit rate** on this corpus. That is a real but modest margin, and it is the number this
> project actually measured — not a claim of "significantly higher accuracy than existing AVMs".
> Proving that claim requires the registry-transaction holdout described in
> [`docs/DATA_STRATEGY.md`](docs/DATA_STRATEGY.md).

---

## Data provenance

**This prototype does not use licensed transaction data.** There is no public Indian property
transaction micro-dataset that can be redistributed, and inventing one would be the easiest way to
fail a diligence review.

The training corpus (`data_gen.py`) is a **documented parametric generator**: a multiplicative price
surface with hand-set coefficients for city level, locality index, property type, area elasticity,
age depreciation, floor premium, furnishing uplift, infrastructure distance decay, tenure and
occupancy, plus log-normal market noise. Latitude/longitude for the 64 covered micro-markets are
approximate locality centroids, used only so the geo-enrichment layer can be exercised for real.

What this proves: the feature contract, the model, the conformal calibration, the attribution, the
comparable-sales reconciliation, the lending policy and the audit trail all work end to end and are
ready to be pointed at a real feed.

What it does **not** prove: real-world AVM accuracy.

One component *is* live external data: **OpenStreetMap POI density** via the Overpass API, queried at
valuation time (asynchronously, so it can never block a valuation).

The production data plan — registry deeds, circle/ready-reckoner rates, satellite built-up area,
market indices — is in [`docs/DATA_STRATEGY.md`](docs/DATA_STRATEGY.md), with each source tagged by
whether it is live in this build or planned.

---

## The lending layer

The engine does not make credit decisions. It evaluates a **collateral-risk policy** and returns one
of four positions, each with named checks and machine-readable reason codes:

```
AUTO_APPROVE_DESKTOP      confidence >= 72%, LTV <= ceiling x 0.95, no warnings
APPROVE_WITH_CONDITIONS   LTV within ceiling, confidence >= 60%
REFER_PHYSICAL_VALUATION  any hard check failed
REFER_CREDIT              LTV above ceiling, or confidence < 60%
```

LTV caps follow the RBI/NHB ceiling (90% up to ₹30 lakh, 80% to ₹75 lakh, 75% above) and are **only
ever tightened** by a confidence haircut of 0–20%. The recommended loan is computed against the
**p10** value, not the point estimate. Full policy in
[`docs/LENDING_POLICY.md`](docs/LENDING_POLICY.md).

---

## Architecture

```
Browser (vanilla JS console, no build step)
   │
   ├── POST /api/valuate ─────────────┐
   │                                 │
   ├── GET  /api/geo ────────────────┼── engine/geo.py ──── OpenStreetMap Overpass
   │      (async, never blocks)      │
   │                                 ├── engine/model.py ── JSON trees, pure numpy inference
   │                                 ├── engine/valuation.py ── point + conformal band +
   │                                 │      attribution + comps + confidence
   │                                 ├── engine/lending.py ── policy engine, LTV caps, reason codes
   │                                 └── engine/audit.py ── SHA-256 hash chain (JSONL)
   │
   └── POST /api/batch ──────────────── 24-property book in one request
```

**No scikit-learn at runtime.** The model is exported to flat JSON tree arrays and evaluated by a
pure-numpy module. This was a real production fix: the first deployment of this project failed with
`ModuleNotFoundError: No module named '_loss'` because a joblib pickle was written by scikit-learn
1.8 and unpickled by the runtime's older build. JSON trees cannot drift, cold-start faster, and keep
the serverless bundle small. A round-trip test asserts the exported trees reproduce scikit-learn's
predictions exactly (max |Δ log price| = 0.0e+00 over 250 rows).

Full detail in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Run it locally

```bash
pip install -r requirements.txt          # runtime: fastapi, uvicorn, numpy, pydantic
python -m uvicorn app:app --reload --port 8000
# http://127.0.0.1:8000
```

Retrain the model (needs the dev dependencies):

```bash
pip install -r requirements-dev.txt
python data_gen.py        # regenerate the parametric corpus -> data/properties.csv
python train.py           # fit, calibrate, export artifacts/*.json, print all metrics
python -m pytest -q       # 25 tests
```

`train.py` refuses to write artifacts if the exported trees do not reproduce scikit-learn exactly.

---

## API

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/api/health` | Liveness + measured model metrics |
| `GET` | `/api/meta` | Metrics, benchmarks, coverage, policy, audit stats |
| `GET` | `/api/options` | Cities, localities, property types, sample records |
| `POST` | `/api/valuate` | Full valuation + attribution + comps + lending decision |
| `POST` | `/api/batch` | Up to 40 properties, decision mix, straight-through rate |
| `GET` | `/api/geo` | Live POI density for a coordinate |
| `GET` | `/api/audit` | Ledger tail |
| `GET` | `/api/audit/verify` | Recompute the hash chain, report the first broken link |

```bash
curl -X POST https://housing-valuation-ai.vercel.app/api/valuate \
  -H "Content-Type: application/json" \
  -d '{"city":"Bangalore","locality":"Koramangala","property_type":"Apartment",
       "furnishing":"Semi-Furnished","occupancy":"Self-Occupied","tenure":"Freehold",
       "area_sqft":1250,"bedrooms":3,"bathrooms":2,"floor":7,"total_floors":14,
       "age_years":5,"parking":1,"lift":1,"balcony":1,"metro_distance_km":1.2,
       "school_distance_km":0.6,"hospital_distance_km":1.1,"highway_distance_km":2.4,
       "crime_index":4.2}'
```

---

## Coverage

8 cities · 64 micro-markets · 8 property types (5 residential, 3 commercial): Mumbai, Delhi,
Bangalore, Hyderabad, Pune, Chennai, Ahmedabad, Kolkata.

Extension path: a new city needs one row in the locality table plus a training slice; a new
micro-market inside a covered city needs only a coordinate and a locality label. The model falls back
to city-level behaviour for an unseen locality and flags `UNSEEN_MICROMARKET` while lowering confidence.

---

## What is deliberately not here

- **No certified valuation claim.** Output is a model estimate, not a registered valuer's report.
- **No credit decision.** The lending layer evaluates a property-risk policy; a human decides.
- **No durable ledger.** The audit chain is an append-only JSONL file on instance disk. It
  demonstrates the mechanism and detects tampering, but production needs DynamoDB / S3 Object Lock /
  append-only Postgres. Stated in the UI, not hidden.
- **No satellite features.** Built-up area validation is specified in the data strategy and tagged
  *production plan*, not faked with a proxy.

---

## Repo map

```
app.py                     FastAPI routes
engine/
  model.py                 JSON tree loader + pure-numpy inference
  valuation.py             point, conformal band, attribution, comps, confidence
  lending.py               LTV policy, checks, reason codes, risk grade
  geo.py                   OpenStreetMap Overpass enrichment + cache
  audit.py                 hash-chained ledger
train.py                   fit, calibrate, benchmark, export artifacts
data_gen.py                parametric corpus generator
artifacts/
  model.json               trees + vocabs + conformal bounds + metrics
  comps.json               3,000-row comparable pool
  locality_stats.json      locality-level medians
  coverage.json            cities, localities, coordinates, sample records
static/                    console UI (vanilla JS, no build step)
tests/                     25 API + engine regression tests
docs/                      model card, data strategy, lending policy, architecture
```

---

## Licence

MIT. See `LICENSE`.
