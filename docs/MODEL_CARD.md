# Model card — HousingValuation AI v2.0

## Purpose

Estimate the fair market value of Indian residential and commercial property from structured
attributes, and quantify the uncertainty of that estimate well enough for a lender to decide whether
a desktop decision is defensible or a physical inspection must be ordered.

**Intended use:** triage and price-discovery in a mortgage workflow.
**Not intended for:** certified valuations, litigation, taxation, or any decision made without a
human credit officer in the loop.

## Model

| Property | Value |
|---|---|
| Family | Gradient-boosted regression trees |
| Loss | Huber (α = 0.90) — limits influence of the noisy tail |
| Target | `log(price_inr)` |
| Trees | 320, depth 6, learning rate 0.055, subsample 0.85, min_samples_leaf 6 |
| Features | 20 (6 categorical, 14 numeric) |
| Training rows | 4,800 (80% split, seed 20261110) |
| Holdout rows | 1,200 |
| Runtime | Pure-numpy JSON tree evaluation, no scikit-learn |

Log-space fitting is deliberate: the loss then matches percentage error, which is what a lender
prices, and it stabilises variance across a ₹0.9M–₹50M range.

### Features

**Categorical (ordinal-encoded against a fixed vocabulary):** city, locality, property_type,
furnishing, occupancy, tenure.

**Numeric:** area_sqft, bedrooms, bathrooms, floor, floor_ratio (`floor / total_floors`, clipped
0–1), age_years, parking, lift, balcony, metro_distance_km, school_distance_km,
hospital_distance_km, highway_distance_km, crime_index.

`floor_ratio` rather than raw `floor` is intentional: a 7th floor in a 14-storey building is a
different product from a 7th floor in an 8-storey building, and the raw feature cannot express that.

### Excluded features

Borrower demographics, name, religion, caste, gender, and any applicant attribute. The valuation is a
property model; the lending policy is applied to collateral and confidence only. This is a design
constraint, not an afterthought — it removes the most obvious fair-lending exposure.

## Uncertainty — split conformal

Intervals are **not** a hand-set ±10% band and **not** independent quantile booster heads (an earlier
version used those; they produced a 59% wide, lopsided band on a normal property, which is how this
was caught).

Method:

1. Generate out-of-fold predictions with 5-fold CV over the training corpus.
2. Compute `residual = log(y) − log(ŷ)` for every row.
3. Take the 10th and 90th percentiles of that residual distribution, globally and per property type
   (Mondrian conformal).
4. Band = `ŷ · exp(q10)` to `ŷ · exp(q90)`.

**Measured coverage: 79.1% against a nominal 80%** on the holdout split, median band width 35.2%.

The per-property-type split matters because commercial assets have structurally wider dispersion
than apartments.

## Accuracy

| Model (identical 1,200 holdout rows) | MAPE | R² | Median APE | Within ±10% | Within ±20% |
|---|---|---|---|---|---|
| Global median ₹/sqft × area | 42.08% | 0.346 | 33.88% | 15.8% | 30.8% |
| Locality × type median ₹/sqft × area | 12.86% | 0.945 | 10.72% | 47.2% | 80.1% |
| Ridge hedonic (same features) | 25.99% | 0.679 | 18.82% | 26.3% | 53.3% |
| **Gradient boosting (this engine)** | **11.16%** | **0.944** | **9.16%** | **54.3%** | **84.6%** |

*(Exact figures are emitted by `train.py` and served at `/api/meta`; the table above is generated from
the same run and should be regenerated rather than copied if the corpus changes.)*

### Generalisation — the number that matters

Random-split metrics flatter any tree model on a corpus with repeated localities. The honest test is
**GroupKFold by locality**, which simulates scoring a micro-market with no training history:

| Metric | Value |
|---|---|
| Grouped MAPE (mean of 5 folds) | **23.54%** |
| Worst fold | 29.65% |
| Grouped R² (mean) | 0.817 |
| Fold MAPEs | 17.03%, 25.21%, 19.01%, 29.65%, 26.80% (`/api/meta`) |

Error roughly doubles. That is expected and is exactly why the engine:

- lowers confidence by 15% for an unseen micro-market,
- raises `UNSEEN_MICROMARKET`,
- and lets the interval do the talking instead of the point estimate.

## Explainability

Two independent mechanisms, both returned with every valuation.

### 1. Baseline-substitution attribution (occlusion)

For a subject property, build the **typical property in the same micro-market** (median numeric
values, modal categorical values, from the comparable pool). Then swap in each feature from the
subject one at a time and measure the change in `log(price)`.

- Exact — no sampling approximation.
- Model-agnostic — works on any regressor.
- Reproducible — deterministic, no seed.
- Reconciles: `log(value) − log(baseline) = Σ effects + residual`, where the residual is the
  interaction term. Reported transparently (typically 3–7% in log space).

Effects are grouped into seven human-readable drivers: Location, Size & layout, Property profile,
Age & condition, Building & amenities, Connectivity, Neighbourhood safety.

Implementation detail: all 21 substitution rows are evaluated in **one batched prediction**, not 21
separate calls — identical numbers, ~20× less dispatch overhead.

### 2. Comparable-sales cross-check

Nearest 8 comparables within 12 km, scored on distance, type match, area similarity and age
similarity, then adjusted through an explicit **adjustment grid**:

| Adjustment | Coefficient |
|---|---|
| Age | ±0.9% per year of age difference |
| Floor ratio | ±6% per unit of floor-ratio difference |
| Furnishing | 0 / +3.5% / +7.5% |
| Size (₹/sqft elasticity) | −0.18 × ln(area ratio) |
| Market drift | +0.4% per month since sale |

These coefficients are **hand-set and documented, deliberately not fitted on the valuation model**, so
that the comparable estimate stays an independent cross-check rather than a restatement of the model.

Weighted median by recency (18-month half-life) and distance gives `comps_value`. The divergence
between model and comps feeds confidence and is surfaced as a percentage. Divergence > 18% raises
`MODEL_COMPS_DIVERGENCE`; > 20% fails a lending check.

## Confidence

Deterministic composite in [0.05, 0.97]:

```
confidence = 0.45 · f_interval + 0.25 · f_comparables + 0.30 · f_agreement

f_interval    = clamp(1 − (band_width − 0.25) / 0.40, 0, 1)
f_comparables = clamp(n_comps / 8, 0.25, 1)
f_agreement   = clamp(1 − divergence / 0.30, 0, 1)
```

An unseen micro-market applies a further ×0.85. There is **no random component** in the serving path:
the same property always returns the same value, band, drivers and confidence. This is a hard
requirement for audit, and an earlier build violated it with a `np.random.uniform` confidence term
that was removed.

## Known limitations

1. **Synthetic corpus.** No licensed transaction data. All accuracy figures are within-corpus.
2. **No satellite or built-up-area validation.** Declared area is taken at face value; this is the
   largest single source of real-world AVM error and is specified as a production feature, not faked.
3. **No temporal split.** The corpus has synthetic sale dates but the holdout is random, not
   out-of-time. A production validation must hold out the most recent 12 months.
4. **Thin commercial support.** Commercial types are in the corpus with a wider noise term; per-type
   conformal bounds partly compensate, but commercial valuation needs its own model in production.
5. **Locality-level granularity.** No sub-locality (building, street, tower) effects, which are the
   dominant driver in dense Indian metros.
6. **Crime index is an input, not verified data.** In production it must come from a citable
   district-level source or be dropped.
7. **Attribution interactions.** Occlusion leaves 3–7% of the log deviation as residual. Shapley
   values would be exact in the interaction sense and are the natural upgrade.

## Monitoring a production deployment

| Signal | Threshold | Action |
|---|---|---|
| Rolling 3-month conformal coverage | < 72% | Recalibrate, then investigate drift |
| Rolling MAPE on inspected properties | > 15% | Model review |
| PSI on locality mix, area, price level | > 0.2 | Re-fit |
| Share of `UNSEEN_MICROMARKET` | > 20% | Expand corpus coverage |
| Share of `MODEL_COMPS_DIVERGENCE` | > 10% | Review comps pool freshness |
| Median latency | > 500 ms | Capacity / caching review |

## Version history

- **v2.0** — conformal intervals replacing quantile heads; batched attribution (3.3 s → 55 ms);
  JSON tree export replacing joblib; comparable-sales engine; lending policy layer; hash-chained
  audit ledger; multi-view console.
- **v1.0** — single-model prototype with a synthetic ±10% band and a random confidence term.
  Both were removed as unsound.
