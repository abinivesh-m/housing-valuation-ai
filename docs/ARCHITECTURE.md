# Architecture

A four-module Python engine behind a FastAPI surface, a no-build vanilla JS console, and a
hash-chained audit ledger. The design goal is not "ML demo" — it is **every number is explainable,
every request is replayable, and no dependency can break the deploy**.

---

## 1. System map

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Browser — static/index.html + app.js + style.css (no build step, no framework)│
│   Valuation · Portfolio · Model & data · Governance                          │
└───────────────┬───────────────────────────────────────────────┬─────────────┘
                │ POST /api/valuate                             │ GET /api/geo
                │ POST /api/batch                               │ (parallel, non-blocking)
                ▼                                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ app.py — FastAPI, pydantic validation, coordinate resolution, response shaping│
└───┬──────────────┬──────────────┬──────────────┬───────────────┬─────────────┘
    │              │              │              │               │
    ▼              ▼              ▼              ▼               ▼
engine/         engine/        engine/        engine/         engine/
model.py        valuation.py   lending.py     audit.py        geo.py
JSON trees      point + band   LTV policy     SHA-256 chain   Overpass POI
pure numpy      attribution    checks         JSONL           cache + timeout
                comps          grades
```

The browser never computes a valuation. It posts a property, receives a complete decision object,
and renders it. There is no client-side model, no hidden rounding, and no second source of truth.

---

## 2. Module responsibilities

| Module | Responsibility | Deliberately not responsible for |
|---|---|---|
| `app.py` | HTTP surface, input validation, coordinate resolution, audit append, response assembly | Model logic, policy thresholds, geo calls on the hot path |
| `engine/model.py` | Load JSON artifacts, encode features, run the additive tree ensemble | Training, calibration, file I/O per request |
| `engine/valuation.py` | Point estimate, conformal band, baseline-substitution attribution, comparables, confidence, flags | Lending policy, audit |
| `engine/lending.py` | LTV bands, confidence haircuts, six checks, reason codes, risk grade | Deciding creditworthiness |
| `engine/audit.py` | Append-only hash chain, verification, stats | Durable storage |
| `engine/geo.py` | Overpass query, radius filter, cache, honest degradation | Blocking a valuation |

---

## 3. Request lifecycle — `POST /api/valuate`

1. **Validate.** pydantic enforces types and physical bounds (`area_sqft` 150–40,000; crime index
   1–10; floors 0–80). Out-of-range input is a 422 before any model code runs.
2. **Resolve coordinates.** Explicit `lat`/`lon` if supplied, else the locality centroid, else the
   city centroid. Coordinates are needed only for comparables and the geo panel.
3. **Check coverage.** Unknown city or a locality outside the city's list is a 422 with the specific
   name. The engine refuses to silently extrapolate to an uncovered market.
4. **Encode.** Six categoricals are ordinal-encoded against frozen vocabularies; fourteen numerics
   are cast to the model's float32 input contract; `floor_ratio` is derived and clipped.
5. **Predict.** One batched pass returns the point value and the conformal p10/p90 bounds. The
   property-type-specific residual quantiles are used where available.
6. **Attribute.** Build the typical property in the same micro-market, swap in each of the subject's
   features one at a time, and evaluate **all 21 rows in a single prediction call**. Effects are
   grouped into seven driver categories in rupees.
7. **Comparables.** Nearest 8 sales within 12 km, scored on distance, type, area and age, adjusted
   through a fixed grid, then weighted-median by recency and proximity. Divergence against the model
   feeds confidence.
8. **Confidence and flags.** Deterministic composite from interval width, comparable count and
   model/comps agreement, with an unseen-micro-market penalty. No random term.
9. **Lending.** Apply the policy, produce the decision, six check results, reason codes and grade.
10. **Audit.** Append `VALUATION` with the value, band, confidence and decision, then return.

**Failure is explicit.** A model that cannot value a property returns a 4xx with a reason; it never
returns a plausible-looking number for an input it does not cover.

---

## 4. Why geo is off the critical path

Overpass is a volunteer-run public endpoint. From this machine it frequently takes longer than the
8-second client timeout, and it has no SLA. If geo enrichment sat on the valuation path, a lender's
turnaround would inherit a volunteer service's availability.

So `/api/valuate` never calls Overpass. The client fires `/api/geo` in parallel and fills the
neighbourhood panel when — and if — it lands. The valuation is complete without it, and the UI says
"unavailable" rather than showing an empty panel that looks broken.

This is a design invariant, not an optimisation: **no external network call is on the valuation
path.**

---

## 5. Model serving

### JSON trees, not pickle

The first deployment of this project failed with:

```
ModuleNotFoundError: No module named '_loss'
```

A joblib pickle written by scikit-learn 1.8 was being unpickled by an older runtime build; the
private `_loss` module had moved. Pinning scikit-learn would have fixed that one deploy and left the
same class of failure in place for the next runtime update — while adding a heavy dependency to every
cold start.

Instead, `train.py` exports each tree as flat arrays:

```json
{ "f": [feature indices], "t": [thresholds], "l": [left children],
  "r": [right children], "v": [leaf values] }
```

`engine/model.py` walks them with vectorised numpy: one array of node indices per batch, one gather
per level, `depth + 1` iterations per tree. Inputs are cast to **float32** before threshold
comparison because scikit-learn's `Tree` does exactly that internally — replicating the cast is what
makes the export bit-exact rather than approximately equal.

`train.py` refuses to write artifacts unless the exported model reproduces scikit-learn's predictions
on 250 rows: **max |Δ log price| = 0.00e+00** on the current build.

### Artifacts

| File | Size | Contents |
|---|---|---|
| `model.json` | 1.11 MB | 320 trees, vocabularies, conformal quantiles, all metrics |
| `comps.json` | 512 KB | 3,000-row comparable pool with rates and dates |
| `coverage.json` | 13 KB | Cities, localities, coordinates, sample records |
| `locality_stats.json` | 27 KB | Per-locality × type medians, used for the unseen check |

Total serving payload ≈ **1.66 MB**, loaded once per process. No database, no cache service, no
warm-up job.

### Caching

| Cache | Scope | Why |
|---|---|---|
| Model and artifacts | Module-level singleton | Loaded at import; immutable thereafter |
| Comparable pool by city | Module-level dict | Avoids a 3,000-row scan per request |
| Attribution baselines | Keyed by `(city, locality, type)` | The baseline for a micro-market never changes |
| Audit head (seq, hash, file size) | Per-ledger, invalidated by file size | Turns an O(n) re-read per append into O(1) |

All caches are read-mostly. The only mutable shared state is the audit ledger, which is serialised by
a `threading.Lock`.

---

## 6. Performance

Measured on the development machine (Windows, Python 3.14, numpy), in-process, after warm-up:

| Operation | Time |
|---|---|
| Single valuation, warm (median of 10) | **55 ms** |
| Single valuation, p95 | 94 ms |
| First call in a fresh process | 71 ms |
| Batch of 24 properties | **1.3 s** (≈ 54 ms each) |

Where the time goes, and what changed:

- **Before:** 3.3 s per valuation. The attribution sweep called the model 21 times, once per feature,
  each with full encode/decode overhead.
- **Now:** the subject, the baseline and all 21 substitutions are stacked into one 23-row matrix and
  predicted in a single pass. Same numbers, ~20× less dispatch overhead. Baselines and the city
  comparable pool are cached across requests.
- The audit append previously re-read the whole ledger to find the head hash. It now caches
  `(seq, head_hash, file_size)` and re-reads only if the file size changed underneath it.

Latency is a property of the *model* path only. In production, registry lookups will dominate, which
is why the API separates valuation from enrichment.

---

## 7. Deployment

```
Vercel (Python runtime)
  api/index.py          entrypoint; adds repo root to sys.path and re-exports app
  vercel.json           routes every path to api/index.py; includeFiles carries
                        app.py, engine/**, artifacts/**, static/**
  static/**             served by FastAPI's StaticFiles mount
```

- **No build step.** The frontend is plain HTML/CSS/JS; the backend is pure Python.
- **No runtime ML dependency.** `requirements.txt` is fastapi, uvicorn, numpy, pydantic.
- **Bundle size.** About 1.7 MB of artifacts plus source — comfortably inside the 50 MB lambda limit.
- **Cold start.** One JSON parse of 1.11 MB plus numpy array construction per tree. The model is
  loaded at import, so the first request pays it once per instance.
- **Ephemeral disk.** The audit ledger lives in the temp directory. It survives warm invocations and
  disappears on cold start or instance recycling. This is stated in the UI and in §8.

Vercel configuration is intentionally explicit about `includeFiles`: the Python runtime traces
imports, but it does not know that `artifacts/*.json` are read at runtime. Omitting them produces a
deploy that boots and then fails on the first request.

---

## 8. Failure modes

| Failure | Behaviour | Mitigation |
|---|---|---|
| Overpass timeout / rate limit | `/api/geo` returns `available: false` with a reason | Never on the valuation path; 7 s timeout; per-coordinate cache |
| Unknown city or locality | 422 with the specific value | Coverage check before model code |
| Malformed or out-of-range input | 422 from pydantic | Bounds on every numeric field |
| Artifact missing or corrupt | Process fails at import — loud, not silent | `train.py` round-trip assert; artifacts committed |
| Audit file unwritable | 500 on the valuation request | Small blast radius: the decision did not reach the ledger, so it is not returned as audited either |
| Cold start | First request slower | One-time artifact load; no network at boot |
| Concurrent instances | Separate audit chains per instance | Documented limitation; production needs a shared append-only store |

---

## 9. Security and data handling

- **No secrets in the repo.** No API keys, no database URLs. `.env*` is git-ignored.
- **No personal data.** The engine consumes property attributes. Borrower attributes are absent by
  design, not by omission.
- **Input surface.** Every endpoint validates types and ranges; batch size is capped at 40; audit
  tail is capped at 100 entries.
- **No authentication.** This is a public demo. A production deployment puts the API behind the
  lender's gateway with mTLS or OAuth, per-tenant rate limits and request signing.
- **Audit integrity.** The chain detects modification, reordering and payload substitution. It does
  not prevent deletion of the whole file — that requires the durable store described below.
- **Prompt-injection surface.** None: no LLM in the serving path. The only natural-language component
  is documentation.

---

## 10. Tests

```bash
python -m pytest -q      # 29 tests, ~10 s
```

Coverage is behavioural rather than line-based:

- determinism (same input → identical value, band, drivers, confidence)
- interval brackets the point estimate; rate per sqft reconciles
- monotonicity (bigger area, newer building, better locality, better furnishing)
- attribution reconciles with the prediction within the interaction residual
- comparables inside the radius, adjustments bounded
- lending: high LTV referred, conservative LTV approved, LTV bands correct, effective cap never above
  regulatory cap, reference LTV labelled, boundary tolerance, grade monotonic in utilisation
- unknown city/locality/area rejected
- batch decision mix and size limit
- audit chain valid, tamper detection at the exact sequence number
- model artifacts expose benchmarks and coverage
- geo endpoint validates coordinates and never raises for valid input
- index page serves

The audit tests use a temporary ledger via `HV_AUDIT_PATH`, so the suite never touches a real chain.

---

## 11. Known gaps

| Gap | Consequence | Fix |
|---|---|---|
| Synthetic training corpus | Accuracy is within-corpus only | Phase-1 registry feed, `DATA_STRATEGY.md` §3 |
| No durable ledger | Audit resets on cold start | DynamoDB / S3 Object Lock / append-only Postgres |
| No satellite features | Declared area taken at face value | Sentinel-2 + Open Buildings footprint check |
| No authentication | Public demo only | Gateway auth, per-tenant keys |
| No temporal split | Random holdout flatters the model | Out-of-time holdout on real data |
| Single-process audit cache | Multi-instance chains diverge | Shared store with conditional writes |
| Crime index unverified | Feature is an input, not evidence | Citable district-level source or drop the feature |

Full model limitations are in [`MODEL_CARD.md`](MODEL_CARD.md); data limitations in
[`DATA_STRATEGY.md`](DATA_STRATEGY.md); policy limitations in [`LENDING_POLICY.md`](LENDING_POLICY.md).
