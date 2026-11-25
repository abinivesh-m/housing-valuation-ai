# Data acquisition playbook

This is the 90-day plan to replace the synthetic corpus with real Indian
transaction data. It is written as a checklist, not an aspiration. Every source
below is one a lender's data team can actually contract; none of them requires
scraping or breaching terms.

## The short version

There is no single national transaction dataset. There are three realistic
paths, in order of cost and defensibility:

1. **A single state's registrar bulk feed** (Karnataka, Maharashtra, Telangana)
   — the only thing that produces a real AVM.
2. **A licensed aggregator** (Propstack, Zapkey, Square Yards) — fastest, most
   expensive, best coverage.
3. **A lender's own closed files** — cheapest, narrowest, enough to validate a
   model you already have.

Do (1) or (2) for production. Do (3) this week for the first real accuracy
number.

## Path 1 — State registrar bulk feed

| State | System | What you get | Access |
|---|---|---|---|
| Karnataka | Kaveri 2.0 (igr.karnataka.gov.in) | Sale deeds with consideration amount, property details, party names | Bulk data request to the IGR; historically granted to HFCs and research bodies under a data-use agreement. Allow 4–8 weeks. |
| Maharashtra | IGR Maharashtra (igrmaharashtra.gov.in) | Registration documents, ready-reckoner rates, transaction values | Bulk access via the department's data cell; ready-reckoner rates are published annually as PDF and are the easiest single artifact to start with. |
| Telangana | Registration & Stamps (registration.telangana.gov.in) | Sale deeds, market values | Bulk access via the department; market-value tables are published. |
| Tamil Nadu | TNREGINET | Sale deeds | Bulk access via the registration department. |

**What you actually need from a deed:** consideration amount, sale date,
property type, built-up area, locality, city, lat/lon (or at least a locality
centroid). Everything else in the engine's schema can be defaulted and flagged.

**Cost:** typically ₹2–10 lakh per state for a licensed bulk extract, plus
legal review of the data-use agreement. The agreement will prohibit
redistribution, which is fine — the model ships, the data does not.

**Obstacle:** the feed is messy. Circle-rate anchoring, delayed registration,
area-definition mismatches (carpet vs built-up vs super built-up) and
duplicate registrations all have to be cleaned before training. `ingest.py`
handles the mechanical part; the semantic part is a month of analyst time.

## Path 2 — Licensed aggregator

| Provider | Coverage | What you get | Rough cost |
|---|---|---|---|
| Propstack | 8+ cities, transaction + listing | Transaction values, property attributes, locality | ₹3–8 lakh/year |
| Zapkey | Mumbai, Pune, Bangalore, Hyderabad | Registered transaction data with consideration | ₹2–5 lakh/year |
| Square Yards / PropTiger data | Pan-India | Listing + transaction aggregates | Custom |
| Liases Foras | Pan-India | Transaction and inventory data | Custom |

**Advantage:** clean, structured, API-delivered, refreshable. **Disadvantage:**
you are now a licensee of someone else's data, and your product's accuracy
claim is only as good as their feed. That is acceptable for a shadow-mode
pilot and unacceptable for a certified valuation.

## Path 3 — A lender's own closed files (do this now)

Every HFC and NBFC has a folder of closed loans with: property address,
sanctioned loan, valuer's report, registered sale price (from the deed the
lender holds), and the date. That is 200–2,000 rows of real transaction truth,
sitting on a shared drive, legally owned by the lender, freely usable for
internal model validation.

**What to ask for:**
- 200+ closed files from the last 3 years
- City, locality, property type, built-up area, floor, age, sale price (from
  the deed), loan amount, valuer's assessed value
- Permission to use for internal validation only

**What to do with it:**
```
python ingest.py lender_closed_files.csv --report reports/lender_ingest.json
python validate_on_real.py lender_closed_files.csv --report reports/lender_validation.json
```
The second command produces the MAPE, interval coverage and ready-reckoner gap
on the lender's own data. That report — not this README — is what a credit-risk
committee signs off on.

## Public, free, citable anchors (ship these today)

These do not give you transaction truth, but they are real, free, and citable,
and they make the synthetic corpus defensible instead of arbitrary:

- **RBI House Price Index** — quarterly, 10 cities, base 2010-11=100.
  Published by RBI. Use it to anchor the city-level price level instead of a
  hand-set multiplier.
- **NHB Residex** — quarterly, 50 cities. Published by NHB. Use it for
  city-level trend validation.
- **Ready-reckoner / circle rates** — published annually by every state's
  registration department. These are the government's own floor rates and they
  are the single most defensible second number in the system. Import with
  `import_ready_reckoner.py`.
- **OpenStreetMap POI density** — already live in the engine via Overpass.

A corpus that is "parametric surface calibrated to RBI HPI and anchored to
the state ready-reckoner" is a defensible reference. A corpus that is "a
formula we wrote" is not. The engine code does not change between the two; only
the inputs do.

## 90-day plan

| Week | Action | Output |
|---|---|---|
| 1–2 | Run Path 3 on a friendly lender's closed files | First real MAPE number |
| 1–2 | Import ready-reckoner rates for 2 cities | `data/ready_reckoner.json` |
| 3–4 | Calibrate the parametric surface to RBI HPI | Updated `data_gen.py` coefficients |
| 3–4 | Write the shadow-mode validation report template | `docs/VALIDATION_REPORT.md` |
| 5–8 | Negotiate Path 1 or Path 2 for one city | Signed data-use agreement |
| 9–12 | Ingest, retrain, re-validate | Real AVM for one city |
| 12+ | Lender pilot on the real model | Revenue |

## What not to do

- Do not scrape 99acres, MagicBricks or Housing.com. It breaches their terms,
  the data is asking prices not sale prices, and a diligence review will find
  it.
- Do not fabricate transaction rows and label them real. The entire value of
  this product is that it is honest about what it measured. One fabricated row
  destroys that permanently.
- Do not claim production accuracy until `validate_on_real.py` has run on a
  file you did not generate.