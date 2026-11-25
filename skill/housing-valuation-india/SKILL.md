---
name: housing-valuation-india
description: Value Indian residential and commercial property and turn the result into a collateral-lending position. Runs locally with no API key. Returns a point value, a conformal p10-p90 interval, rupee attribution per driver, comparable sales, an RBI/NHB LTV policy decision with reason codes, and a risk grade. Use when a task needs an Indian property valuation, a loan-to-value check, a portfolio screen, or collateral risk for a mortgage workflow. Covers 8 cities and 64 micro-markets.
---

# HousingValuation AI — India

An automated valuation engine for Indian property that runs on this machine.
No API key, no network call, no quota. The model artifacts and the inference
code ship with the skill.

It answers three questions per property, not one:

1. **What is this worth?** — a point estimate *and* a calibrated interval.
2. **Why?** — every driver in rupees, exact and additive.
3. **Can I act on it?** — a policy position, not just a number.

## Requirements

- Python 3.10 or newer
- `numpy` (`pip install numpy`)
- Run commands from the skill directory, so `scripts/valuate.py` can find
  `engine/` and `artifacts/`

First run loads about 1.6 MB of JSON artifacts and takes a second. After that a
valuation is roughly 55 ms.

## Check what is covered

```bash
python scripts/valuate.py options
```

Returns the 8 cities, the localities inside each, the property types, and the
allowed values for furnishing, occupancy and tenure. Call this before
valuing anything — an uncovered locality is a hard error, not a fallback.

## Valuing one property

```bash
python scripts/valuate.py valuate --json '{
  "city": "Bangalore",
  "locality": "Koramangala",
  "property_type": "Apartment",
  "area_sqft": 1250,
  "bedrooms": 3,
  "bathrooms": 2,
  "floor": 7,
  "total_floors": 14,
  "age_years": 5,
  "requested_loan_inr": 15000000
}'
```

Or pass a file: `python scripts/valuate.py valuate --file property.json`.
Pipe it: `cat property.json | python scripts/valuate.py valuate`.
Add `--raw` for the full JSON result.

`city`, `locality` and `area_sqft` are the only required fields. Everything
else has a documented default:

| Field | Default | Range |
|---|---|---|
| `property_type` | `Apartment` | see `options` |
| `furnishing` | `Semi-Furnished` | `Unfurnished`, `Semi-Furnished`, `Fully Furnished` |
| `occupancy` | `Self-Occupied` | see `options` |
| `tenure` | `Freehold` | see `options` |
| `bedrooms`, `bathrooms` | `2` | 0–10 |
| `floor`, `total_floors` | `3`, `12` | 0–80, 1–80 |
| `age_years` | `4` | 0–60 |
| `parking` | `1` | 0–10 |
| `lift`, `balcony` | `1`, `1` | 0–1, 0–5 |
| `metro_distance_km` | `2.0` | 0–25 |
| `school_distance_km` | `1.0` | 0–15 |
| `hospital_distance_km` | `1.5` | 0–15 |
| `highway_distance_km` | `3.0` | 0–30 |
| `crime_index` | `5.0` | 1–10 |
| `requested_loan_inr` | `0` | any |

Sending `requested_loan_inr` makes the policy decision meaningful. Without it
the engine evaluates at a 60% reference LTV and says so in
`lending.loan_basis`.

## Screening a book

```bash
python scripts/valuate.py batch --file portfolio.json
```

`portfolio.json` is a JSON array of the same objects, up to 40 per run. Returns
per-row value, interval, confidence, decision, risk grade and flags, plus the
automated share.

## Reading the response

| Field | Meaning |
|---|---|
| `value`, `value_low`, `value_high` | point estimate and conformal p10–p90 band, in ₹ |
| `interval_width_pct` | band width as a percentage of the value |
| `rate_per_sqft` | implied rate, with `rate_low` and `rate_high` |
| `confidence` | 0–1; falls for unseen micro-markets and wide bands |
| `drivers` | per-group ₹ effects, sorted by magnitude |
| `attribution.residual_log` | interaction term the groups do not explain |
| `comparables` | independent sales cross-check with an adjustment grid |
| `comps_divergence_pct` | how far the comps view sits from the model |
| `lending.decision` | `AUTO_APPROVE_DESKTOP`, `APPROVE_WITH_CONDITIONS`, `REFER_PHYSICAL_VALUATION`, `REFER_CREDIT` |
| `lending.reason_codes` | machine-readable reasons behind the decision |
| `lending.max_loan_recommended` | sized against `value_low`, never the point estimate |
| `lending.effective_cap` | RBI/NHB ceiling after the confidence haircut |
| `flags` | e.g. `UNSEEN_MICROMARKET`, `WIDE_INTERVAL` |

## Rules for using the output

- **Never present a value as a certified valuation.** It is a model estimate.
- **Never auto-decline a borrower.** The engine scores collateral only; it does
  not see the applicant and must not be the decision-maker.
- **Treat `REFER_PHYSICAL_VALUATION` as a signal, not a rejection.** It means the
  desktop file cannot carry the decision.
- If `confidence` is below 0.60, say so in whatever you produce.
- Report the interval. A point estimate without `value_low`/`value_high` is a
  misleading output.
- Quote `lending.max_loan_recommended`, not a loan sized on `value`. The
  recommendation is deliberately computed on the p10.

## Limits the engine declares itself

- The model is trained on a documented synthetic corpus, not licensed
  transaction data. Within-corpus MAPE is 11.16% against 12.86% for a locality
  rate card; that is not a claim about real market accuracy.
- 8 cities, 64 micro-markets, 8 property types. Anything else exits with the
  covered list.
- No title, encumbrance or fraud check. Out of scope.
- No live geo enrichment in this package: it ships the model, comps and policy,
  not the OpenStreetMap lookup.

## Running as an MCP server

The skill also ships `mcp_server.py`, a stdlib-only MCP server with six tools:
`valuate_property`, `batch_valuate`, `check_loan`, `get_coverage`,
`get_ready_reckoner_rate`, `get_model_metrics`. Wire it into Claude Desktop,
Claude Code, Cursor or Codex:

```json
{
  "mcpServers": {
    "housing-valuation-india": {
      "command": "python",
      "args": ["/path/to/housing-valuation-india/mcp_server.py"]
    }
  }
}
```

## Bringing your own data

The shipped model is trained on a documented synthetic corpus. To retrain on
real transactions, run `python ingest.py your_deeds.csv --out data/properties.csv`
then `python train.py --data data/properties.csv --label "your source"`. The
engine code does not change; only the numbers do.

| Message | Cause |
|---|---|
| `City '...' is outside the covered market` | run `options` and pick a covered city |
| `Locality '...' is not covered in ...` | run `options`; the covered localities are listed |
| `area_sqft is required and must be between 150 and 40000` | fix the input |
| `ModuleNotFoundError: numpy` | `pip install numpy` |
