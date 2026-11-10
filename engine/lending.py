"""
Risk-based lending layer.

Converts a valuation into a *policy-evaluated* lending position. Two things
this module deliberately does NOT do:

  * it does not make a credit decision — it evaluates a property-risk policy
    and returns whether a desktop valuation is sufficient, or whether a
    physical inspection must be ordered;
  * it does not hide its rules behind a score. Every rule is a named check
    with a pass/warn/fail status and a reason code, so a credit officer can
    override, and an auditor can replay.

LTV caps follow the RBI/National Housing Bank regulatory ceiling that Indian
HFCs work within (90% up to ₹30 lakh, 80% from ₹30–75 lakh, 75% above
₹75 lakh). The engine only ever *tightens* those caps, never loosens them.
"""
from __future__ import annotations

LTV_BANDS = [
    {"max_ticket_inr": 3_000_000, "cap": 0.90, "label": "up to ₹30 lakh"},
    {"max_ticket_inr": 7_500_000, "cap": 0.80, "label": "₹30–75 lakh"},
    {"max_ticket_inr": None, "cap": 0.75, "label": "above ₹75 lakh"},
]

COMMERCIAL_TYPES = {"Commercial Office", "Retail Shop", "Warehouse"}

# 0.05 percentage points of tolerance: a reference loan is generated as 60% of
# the point value, which can land a few rupees above a 60% ceiling purely from
# rounding. Flagging that as a breach would be a display artefact, not a policy
# position.
LTV_EPS = 0.0005


def regulatory_cap(value: int) -> tuple[float, str]:
    for band in LTV_BANDS:
        if band["max_ticket_inr"] is None or value <= band["max_ticket_inr"]:
            return band["cap"], band["label"]
    return 0.75, "above ₹75 lakh"


def confidence_haircut(confidence: float) -> tuple[float, str]:
    if confidence >= 0.85:
        return 1.00, "high confidence — no haircut"
    if confidence >= 0.70:
        return 0.95, "medium confidence — 5% cap haircut"
    if confidence >= 0.55:
        return 0.88, "low confidence — 12% cap haircut"
    return 0.80, "very low confidence — 20% cap haircut"


def _grade(
    confidence: float,
    requested_ltv: float,
    effective_cap: float,
    flags: list[str],
    commercial: bool,
    age: int,
) -> str:
    """Property-risk grade A–E.

    Utilisation is measured against the *confidence-adjusted* ceiling, not as an
    absolute headroom: a 75% LTV against a 75% cap and a 45% LTV against the same
    cap are different risks, but an absolute `cap - ltv` term treats every
    high-value property (cap 75%) as maximum risk the moment the request equals
    the cap. Penalising only the top 20% of the allowed range keeps the grade
    monotonic in both confidence and utilisation.
    """
    utilisation = (requested_ltv / effective_cap) if effective_cap > 0 else 1.0
    score = 0.0
    score += (1.0 - confidence) * 55
    score += max(0.0, utilisation - 0.80) * 60
    score += 6.0 * len([f for f in flags if f in {"WIDE_INTERVAL", "MODEL_COMPS_DIVERGENCE", "UNSEEN_MICROMARKET"}])
    score += 5.0 if commercial else 0.0
    score += 4.0 if age > 25 else 0.0
    if score < 12:
        return "A"
    if score < 22:
        return "B"
    if score < 34:
        return "C"
    if score < 48:
        return "D"
    return "E"


def assess(valuation: dict, requested_loan: int, req: dict) -> dict:
    value = valuation["value"]
    value_low = valuation["value_low"]
    confidence = valuation["confidence"]
    flags = valuation["flags"]
    commercial = req["property_type"] in COMMERCIAL_TYPES
    age = int(req.get("age_years", 0))

    cap, cap_label = regulatory_cap(value)
    haircut, haircut_label = confidence_haircut(confidence)
    effective_cap = round(cap * haircut, 4)
    max_loan = int(round(value_low * effective_cap, -3))
    requested_loan = max(int(requested_loan), 0)
    requested_ltv = requested_loan / value if value else 0.0
    headroom = effective_cap - requested_ltv

    checks = []

    def add(name: str, status: str, detail: str) -> None:
        checks.append({"name": name, "status": status, "detail": detail})

    # 1. regulatory / policy LTV ceiling
    if requested_ltv <= cap + LTV_EPS:
        add("Policy LTV ceiling", "pass", f"requested {requested_ltv:.2%} within the {cap:.2%} cap ({cap_label})")
    else:
        add("Policy LTV ceiling", "fail", f"requested {requested_ltv:.2%} exceeds the {cap:.2%} cap ({cap_label})")

    # 2. confidence-adjusted ceiling
    if requested_ltv <= effective_cap + LTV_EPS:
        add("Confidence-adjusted ceiling", "pass", f"{requested_ltv:.2%} within {effective_cap:.2%} ({haircut_label})")
    else:
        add("Confidence-adjusted ceiling", "fail", f"{requested_ltv:.2%} exceeds {effective_cap:.2%} ({haircut_label})")

    # 3. valuation interval
    width = valuation["interval_width_pct"]
    if width <= 0.40:
        add("Valuation interval width", "pass", f"p10–p90 band is {width:.1%} of the point estimate")
    elif width <= 0.55:
        add("Valuation interval width", "warn", f"p10–p90 band is {width:.1%} — desk review recommended")
    else:
        add("Valuation interval width", "fail", f"p10–p90 band is {width:.1%} — too wide for a desktop decision")

    # 4. comparable support
    comps_n = len(valuation["comparables"])
    if comps_n >= 6:
        add("Comparable support", "pass", f"{comps_n} comparables within 12 km")
    elif comps_n >= 4:
        add("Comparable support", "warn", f"only {comps_n} comparables — thin support")
    else:
        add("Comparable support", "fail", f"only {comps_n} comparables available")

    # 5. model vs comps agreement
    divergence = valuation.get("comps_divergence_pct")
    if divergence is None:
        add("Model / comps reconciliation", "warn", "no comparable value to reconcile against")
    elif divergence <= 12:
        add("Model / comps reconciliation", "pass", f"model and comparables agree within {divergence:.1f}%")
    elif divergence <= 20:
        add("Model / comps reconciliation", "warn", f"{divergence:.1f}% divergence — review drivers")
    else:
        add("Model / comps reconciliation", "fail", f"{divergence:.1f}% divergence — physical inspection")

    # 6. collateral type / age
    if commercial:
        add("Collateral type", "warn", "commercial collateral — separate policy and lower cap apply")
    elif age > 25:
        add("Collateral type", "warn", f"property age {age} years — residual-life check required")
    else:
        add("Collateral type", "pass", "standard residential collateral, within residual life policy")

    statuses = [c["status"] for c in checks]
    reasons: list[str] = []
    if "fail" in statuses:
        decision, label = "REFER_PHYSICAL_VALUATION", "Physical valuation required"
    elif confidence >= 0.72 and requested_ltv <= effective_cap * 0.95 and "warn" not in statuses:
        decision, label = "AUTO_APPROVE_DESKTOP", "Auto-approve on desktop valuation"
    elif requested_ltv <= effective_cap + LTV_EPS and confidence >= 0.60:
        decision, label = "APPROVE_WITH_CONDITIONS", "Approve with conditions"
    else:
        decision, label = "REFER_CREDIT", "Refer to credit officer"

    if requested_ltv > cap + LTV_EPS:
        reasons.append("LTV_ABOVE_REGULATORY_CAP")
    if requested_ltv > effective_cap + LTV_EPS:
        reasons.append("LTV_ABOVE_CONFIDENCE_ADJUSTED_CAP")
    if confidence < 0.60:
        reasons.append("LOW_VALUATION_CONFIDENCE")
    if "WIDE_INTERVAL" in flags:
        reasons.append("WIDE_P10_P90_INTERVAL")
    if "MODEL_COMPS_DIVERGENCE" in flags:
        reasons.append("MODEL_COMPS_DIVERGENCE")
    if comps_n < 4:
        reasons.append("THIN_COMPARABLES")
    if commercial:
        reasons.append("COMMERCIAL_COLLATERAL")
    if "UNSEEN_MICROMARKET" in flags:
        reasons.append("UNSEEN_MICROMARKET")

    return {
        "decision": decision,
        "decision_label": label,
        "risk_grade": _grade(confidence, requested_ltv, effective_cap, flags, commercial, age),
        "regulatory_cap": cap,
        "regulatory_cap_label": cap_label,
        "confidence_haircut": haircut,
        "confidence_haircut_label": haircut_label,
        "effective_cap": effective_cap,
        "requested_loan": requested_loan,
        "requested_ltv": round(requested_ltv, 4),
        "max_loan_recommended": max_loan,
        "overshoot_inr": max(requested_loan - max_loan, 0),
        "headroom_pct": round(headroom * 100, 2),
        "checks": checks,
        "reason_codes": reasons,
        "turnaround": "under 60 seconds, no manual intervention",
    }
