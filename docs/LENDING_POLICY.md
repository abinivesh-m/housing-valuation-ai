# Lending policy

How a valuation becomes a **collateral-risk position**, and why each rule exists. This is a policy
engine, not a credit engine: it never sees the borrower, the income, the credit bureau record or the
title. A human credit officer remains the decision-maker.

---

## 1. Scope

**In scope**

- Is the valuation precise enough to support a desktop decision?
- Does the requested loan fit inside the regulatory and confidence-adjusted LTV ceiling?
- Is there enough comparable evidence, and do the model and the comparables agree?
- Does the collateral type or age require a valuation method this engine cannot provide?

**Out of scope**

- Borrower creditworthiness, income stability, FOIR, bureau score.
- Title, encumbrance, litigation, construction approvals, occupancy certificate.
- Fraud detection, document verification, KYC.
- Insurance, property tax arrears, society dues.

Those remain separate workflow steps. The engine's job is to stop a weak *valuation* from entering a
credit decision, and to say exactly why in machine-readable form.

---

## 2. Decision states

Precedence is top-down; the first matching state wins.

| State | Condition | Meaning |
|---|---|---|
| `REFER_PHYSICAL_VALUATION` | any check has status `fail` | The desktop file cannot support a collateral decision. Order an inspection. |
| `AUTO_APPROVE_DESKTOP` | `confidence ≥ 0.72` **and** `requested_ltv ≤ 0.95 × effective_cap` **and** no `warn` | Straight-through. No human valuer, no inspection. |
| `APPROVE_WITH_CONDITIONS` | `requested_ltv ≤ effective_cap` **and** `confidence ≥ 0.60` | Accept the valuation; attach the conditions and reason codes. |
| `REFER_CREDIT` | anything else | The issue is not (only) the property — send it to a credit officer. |

The 95% factor on the auto-approve path is deliberate: a file sitting exactly at the ceiling is
approved, but not straight-through. Headroom is where errors are absorbed.

---

## 3. Reference LTV when no loan is entered

The UI sends `requested_loan_inr = 0` when the user has not entered an amount. The engine then
evaluates the policy at a **60% reference LTV** and marks the response:

```json
"loan_assumed": true,
"loan_basis": "reference LTV — no loan amount entered"
```

Why not test at the ceiling: every property above ₹75 lakh has a 75% cap, so a ceiling test would
grade every premium property as maximum risk and make the A–E grade meaningless. Why not skip the
lending layer: the point of the panel is to show what the policy would say. The flag makes the
assumption impossible to miss, and any submitted amount always overrides it.

---

## 4. LTV ceilings

The engine works inside the RBI / National Housing Bank ceiling that Indian housing finance companies
operate under, and **only ever tightens it**.

| Property value | Regulatory cap |
|---|---|
| up to ₹30 lakh | 90% |
| ₹30–75 lakh | 80% |
| above ₹75 lakh | 75% |

Source: RBI/NHB LTV norms as commonly applied by HFCs. A lender deploying this engine must confirm
the current circular and its own board policy; the table is a default, not legal advice.

| Confidence | Cap multiplier | Effect on a 75% cap |
|---|---|---|
| ≥ 0.85 | × 1.00 | 75.0% |
| 0.70–0.85 | × 0.95 | 71.3% |
| 0.55–0.70 | × 0.88 | 66.0% |
| < 0.55 | × 0.80 | 60.0% |

`effective_cap = regulatory_cap × multiplier`, rounded to 4 decimals. It is never above the
regulatory cap.

---

## 5. Exposure basis

```
max_loan_recommended = p10_value × effective_cap     (rounded to the nearest ₹1,000)
```

Two conservative choices, both intentional:

1. **p10, not the point estimate.** The lender is exposed to the downside, not the median. Using the
   lower conformal bound means the recommendation survives the model being wrong in the direction it
   is most likely to be wrong.
2. **The confidence haircut compounds with the cap**, so a low-confidence file gets a smaller loan
   against an already conservative value.

`overshoot_inr = max(requested_loan − max_loan_recommended, 0)` is returned so the UI can show the
gap rather than just a verdict.

**Boundary tolerance.** LTV comparisons use a 0.05 percentage-point tolerance (`LTV_EPS`). A
reference loan generated as 60% of the point value can land a few rupees above a 60.00% ceiling
through rounding; reporting that as a breach would be a display artefact, not a policy position.

---

## 6. The six checks

| # | Check | Pass | Warn | Fail |
|---|---|---|---|---|
| 1 | Policy LTV ceiling | `requested_ltv ≤ cap` | — | above |
| 2 | Confidence-adjusted ceiling | `requested_ltv ≤ effective_cap` | — | above |
| 3 | Valuation interval width | ≤ 40% | 40–55% | > 55% |
| 4 | Comparable support | ≥ 6 comps | 4–5 comps | < 4 comps |
| 5 | Model / comps reconciliation | divergence ≤ 12% | 12–20% | > 20% |
| 6 | Collateral type | standard residential, age ≤ 25 yrs | commercial, or age > 25 yrs | — |

The interval and comps thresholds are not arbitrary: on the holdout corpus the median p10–p90 band
is 35.2%, so a 40% pass line is "typical or better". Comparable support is calibrated to the engine's
8-comparable search radius. Divergence is measured against a comparable estimate that uses an
**independent** adjustment grid, so it is a genuine cross-check and not a restatement of the model.

---

## 7. Reason codes

Machine-readable, stable strings — safe to branch on in a downstream workflow.

| Code | Emitted when |
|---|---|
| `LTV_ABOVE_REGULATORY_CAP` | requested LTV above the RBI/NHB band |
| `LTV_ABOVE_CONFIDENCE_ADJUSTED_CAP` | above the haircut-adjusted ceiling |
| `LOW_VALUATION_CONFIDENCE` | confidence < 0.60 |
| `WIDE_P10_P90_INTERVAL` | interval flag raised by the valuation layer |
| `MODEL_COMPS_DIVERGENCE` | model and comparables differ by more than the flag threshold |
| `THIN_COMPARABLES` | fewer than 4 comparables |
| `COMMERCIAL_COLLATERAL` | office, retail or warehouse |
| `UNSEEN_MICROMARKET` | locality absent from training; confidence already reduced by 15% |

---

## 8. Risk grade A–E

A property-level grade, separate from the decision, so a portfolio view can rank collateral even when
every file is approvable.

```
utilisation = requested_ltv / effective_cap
score = 55 × (1 − confidence)
      + 60 × max(0, utilisation − 0.80)
      +  6 × |{WIDE_INTERVAL, MODEL_COMPS_DIVERGENCE, UNSEEN_MICROMARKET} ∩ flags|
      +  5 if commercial
      +  4 if age > 25 years
```

| Grade | Score |
|---|---|
| A | < 12 |
| B | 12–22 |
| C | 22–34 |
| D | 34–48 |
| E | ≥ 48 |

**Why utilisation and not absolute headroom.** An earlier version scored `cap − ltv`. Because every
property above ₹75 lakh has a 75% cap, a request at 75% produced zero headroom and therefore grade D
even at 91% confidence with six passing checks. Utilisation asks the right question: how much of the
*allowed* range is being used? A 60% request against a 75% ceiling is 80% utilisation and attracts no
penalty; 74% against 75% is 98.7% utilisation and attracts 11 points. The grade is now monotonic in
both confidence and exposure, which is what a portfolio ranking needs.

---

## 9. Worked examples

All three are captured from the running engine, not hand-written.

### A — clean apartment, desktop decision

| | |
|---|---|
| Property | 3 BHK, 1,250 sqft, Koramangala, Bangalore, 5 years old, 7/14 floor |
| Value | **₹2,08,15,000** (p10 ₹1,78,44,000 – p90 ₹2,41,12,000) |
| Confidence | 0.879 · band width 30.1% · 8 comparables · divergence 6.3% |
| Reference loan | ₹1,24,89,000 (60% of point value, `loan_assumed = true`) |
| Cap | 75% regulatory × 1.00 haircut = 75% |
| Max loan recommended | ₹1,33,83,000 (p10 × 75%) |
| **Decision** | **`AUTO_APPROVE_DESKTOP` · grade A · no reason codes** |

Six passes. This is the case the product exists for: a file that would take a valuer three to five
days is cleared in 55 ms.

### B — same property, loan pushed to the ceiling

| | |
|---|---|
| Requested loan | ₹1,50,00,000 → LTV **72.1%** against a 75% ceiling |
| **Decision** | **`APPROVE_WITH_CONDITIONS` · grade B · no reason codes** |

Still within policy, but utilisation is 96% of the allowed range, so it does not get straight-through
treatment. The difference between A and B is the entire point of the grade.

### C — stale commercial asset

| | |
|---|---|
| Property | Warehouse, 6,000 sqft, Behala, Kolkata, 31 years old |
| Value | ₹1,49,86,000 (band ₹1,14,64,000 – ₹1,88,67,000) |
| Confidence | 0.426 · band width 49.4% · divergence **64.3%** |
| Cap | 75% × 0.80 haircut = **60%** |
| Reference loan | ₹89,92,000 |
| Max loan recommended | ₹68,78,000 |
| **Decision** | **`REFER_PHYSICAL_VALUATION` · grade E** |
| Reason codes | `LOW_VALUATION_CONFIDENCE`, `MODEL_COMPS_DIVERGENCE`, `COMMERCIAL_COLLATERAL` |

The model and the comparable grid disagree by 64%, the interval is wide, and confidence is below the
0.55 haircut band. The engine does not pretend a desktop answer exists.

---

## 10. Human override and audit

Every valuation and every decision is appended to a hash-chained ledger:

```
hash = SHA-256(prev_hash | seq | ts | kind | ref | payload_digest)
```

- A credit officer can override any state; the override must be written as a new ledger entry, never
  by editing history.
- `GET /api/audit/verify` recomputes the chain and reports the first broken link, so a silent edit
  to a past valuation is detectable.
- The ledger stores the property inputs that matter for replay and no personal data.

**Known limitation, stated in the UI:** the ledger is an append-only JSONL file on the instance disk.
It demonstrates the mechanism and survives a warm serverless instance, but it is not durable.
Production requires DynamoDB, S3 Object Lock or an append-only Postgres table, with the hash chain
preserved. This build does not claim to be a system of record.

---

## 11. Monitoring the policy, not just the model

| Signal | Target | Action |
|---|---|---|
| Straight-through rate | Track, do not target | A rising STP rate with flat override quality means loosening; falling means drift |
| Override rate per reason code | < 15% | Review the threshold that generated the code |
| Physical-inspection yield | > 30% of referrals | Below this, the referral rules are too aggressive |
| Accuracy on inspected files | MAPE ≤ 15% | Model review |
| Grade migration | Stable quarter on quarter | Investigate drift in confidence or LTV mix |
| Time to decision | < 60 s desktop | Capacity review |

The policy is only as good as its calibration. A rule that refers 40% of files and catches nothing on
inspection is worse than no rule, because it destroys turnaround without reducing risk.

---

## 12. Deliberate non-claims

- Not a credit approval. The engine never sees the borrower.
- Not a title opinion. Encumbrance and litigation are outside its input space.
- Not a certified valuation. Output is a model estimate with a stated interval.
- Not calibrated on real transactions. The policy thresholds are defensible for this corpus and must
  be re-derived against a lender's own loss and override data before production use.
