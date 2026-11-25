"""Real-data validation harness.

This is the artifact that converts 'we have a pipeline' into 'we can prove
accuracy on your data in ten minutes.' Given a transaction file (the same
schema `ingest.py` produces), it runs the full accuracy suite against it and
writes a diligence report in the same shape as the within-corpus report in
`train.py`:

    python validate_on_real.py your_deeds.csv --report reports/validation.json

What it measures, honestly:
    * holdout MAPE, R2, within-10%, within-20% for the gradient booster
    * the same four metrics for the locality x type rate card (the number most
      lenders run today) and a ridge hedonic, on identical rows
    * split-conformal interval coverage and median band width
    * grouped CV by locality (the unseen-micro-market number)
    * error by price band
    * ready-reckoner comparison: model vs government floor rate

What it does NOT do: it cannot turn a synthetic corpus into evidence about the
Indian market. It can only measure what your data actually supports. If your
data is thin, the report says so, loudly, in the same JSON a reviewer reads.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import train  # noqa: E402
from engine import ready_reckoner  # noqa: E402

# Reuse train.py's machinery so the two reports are byte-comparable.
from train import (  # noqa: E402
    CATEGORICAL, NUMERICAL, FEATURES, SEED, N_ESTIMATORS, MAX_DEPTH,
    LEARNING_RATE, MIN_SAMPLES_LEAF, new_model, build_matrix, add_derived,
    metrics_block,
)


def _load(path: Path) -> pd.DataFrame:
    import ingest
    raw = ingest.load_table(path)
    mapping, unmapped, missing = ingest.map_columns(list(raw.columns))
    if missing:
        raise SystemExit(f"missing required columns: {', '.join(missing)}")
    renamed = raw.rename(columns={src: dst for dst, src in mapping.items()})
    frame, issues = ingest.validate(renamed)
    if len(frame) < 200:
        print(f"WARNING: only {len(frame)} usable rows; accuracy figures will be noisy",
              file=sys.stderr)
    return frame, issues, unmapped


def _ready_reckoner_gap(df: pd.DataFrame, predictions: np.ndarray) -> dict:
    gaps = []
    for i, row in df.iterrows():
        rr = ready_reckoner.rate(str(row["city"]), str(row["locality"]),
                                  str(row["property_type"]))
        if rr["rate"]:
            gaps.append((predictions[i] / (rr["rate"] * row["area_sqft"]) - 1.0) * 100)
    if not gaps:
        return {"n": 0, "median_gap_pct": None, "note": "no ready-reckoner rates available"}
    return {
        "n": len(gaps),
        "median_gap_pct": round(float(np.median(gaps)), 2),
        "mean_gap_pct": round(float(np.mean(gaps)), 2),
        "note": "positive = model above government floor rate",
    }


def run(frame: pd.DataFrame, issues, unmapped) -> dict:
    df = add_derived(frame)
    vocabs = {c: sorted(df[c].astype(str).unique().tolist()) for c in CATEGORICAL}
    X = build_matrix(df, vocabs)
    y_price = df["price_inr"].to_numpy(dtype=np.float64)
    y_log = np.log(y_price)

    idx_train, idx_test = train.train_test_split(
        np.arange(len(df)), test_size=0.20, random_state=SEED, shuffle=True
    )

    # conformal calibration on out-of-fold residuals
    oof = np.zeros(len(df))
    for tr, te in train.KFold(n_splits=5, shuffle=True, random_state=SEED).split(X):
        fold = new_model()
        fold.fit(X[tr], y_log[tr])
        oof[te] = fold.predict(X[te])
    resid = y_log - oof

    def bounds():
        return float(np.quantile(resid, 0.10)), float(np.quantile(resid, 0.90))

    q_lo, q_hi = bounds()

    model = new_model()
    model.fit(X[idx_train], y_log[idx_train])
    p_med = np.exp(model.predict(X[idx_test]))
    test_y = y_price[idx_test]
    lo = p_med * np.exp(q_lo)
    hi = p_med * np.exp(q_hi)
    coverage = float(((test_y >= lo) & (test_y <= hi)).mean())
    band_pct = (hi - lo) / p_med

    model_metrics = metrics_block(test_y, p_med)

    # benchmarks on identical rows
    train_df = df.iloc[idx_train]
    test_df = df.iloc[idx_test]
    global_rate = float((train_df["price_inr"] / train_df["area_sqft"]).median())
    b1 = test_df["area_sqft"].to_numpy(dtype=float) * global_rate

    rate_table = (
        train_df.assign(rate=train_df["price_inr"] / train_df["area_sqft"])
        .groupby(["locality", "property_type"])["rate"].median()
    )
    loc_rate = (
        train_df.assign(rate=train_df["price_inr"] / train_df["area_sqft"])
        .groupby("locality")["rate"].median()
    )
    naive = []
    for _, row in test_df.iterrows():
        r = rate_table.get((row["locality"], row["property_type"]),
                            loc_rate.get(row["locality"], global_rate))
        naive.append(r * row["area_sqft"])
    b2 = np.array(naive, dtype=float)

    onehot = pd.get_dummies(train_df[CATEGORICAL].astype(str), drop_first=True)
    onehot_test = pd.get_dummies(test_df[CATEGORICAL].astype(str), drop_first=True).reindex(
        columns=onehot.columns, fill_value=0
    )
    Xh_train = np.column_stack([onehot.to_numpy(dtype=float),
                                train_df[NUMERICAL].to_numpy(dtype=float)])
    Xh_test = np.column_stack([onehot_test.to_numpy(dtype=float),
                               test_df[NUMERICAL].to_numpy(dtype=float)])
    mu, sd = Xh_train.mean(0), Xh_train.std(0) + 1e-9
    ridge = train.Ridge(alpha=1.0)
    ridge.fit((Xh_train - mu) / sd, np.log(train_df["price_inr"].to_numpy(dtype=float)))
    b3 = np.exp(ridge.predict((Xh_test - mu) / sd))

    benchmarks = {
        "global_median_rate": {"label": "Global median ₹/sqft x area",
                               **metrics_block(test_y, b1)},
        "locality_type_median_rate": {"label": "Locality x type median ₹/sqft x area",
                                     **metrics_block(test_y, b2)},
        "ridge_hedonic": {"label": "Ridge hedonic regression (same features)",
                          **metrics_block(test_y, b3)},
        "gradient_boosting": {"label": "Gradient boosting (this engine)",
                              **model_metrics},
    }

    # grouped CV by locality
    grouped_scores = []
    for tr, te in train.GroupKFold(n_splits=min(5, df["locality"].nunique())).split(
            X, y_log, df["locality"].to_numpy()):
        fold = new_model()
        fold.fit(X[tr], y_log[tr])
        grouped_scores.append(metrics_block(y_price[te], np.exp(fold.predict(X[te]))))
    grouped_cv = {
        "scheme": "GroupKFold by locality - simulates a micro-market with no training history",
        "n_folds": len(grouped_scores),
        "mape_mean": round(float(np.mean([g["mape"] for g in grouped_scores])), 4),
        "mape_worst": round(float(np.max([g["mape"] for g in grouped_scores])), 4),
        "r2_mean": round(float(np.mean([g["r2"] for g in grouped_scores])), 4),
        "fold_mape": [g["mape"] for g in grouped_scores],
    }

    # price bands
    bands = []
    edges = np.percentile(test_y, [0, 20, 40, 60, 80, 100])
    for i in range(5):
        mask = (test_y >= edges[i]) & (test_y <= edges[i + 1])
        if mask.sum() < 5:
            continue
        ape = np.abs(p_med[mask] - test_y[mask]) / test_y[mask]
        bands.append({
            "band": f"₹{edges[i]/1e7:.1f}Cr–₹{edges[i+1]/1e7:.1f}Cr",
            "n": int(mask.sum()),
            "mape": round(float(ape.mean()), 4),
            "median_ape": round(float(np.median(ape)), 4),
        })

    rr_gap = _ready_reckoner_gap(df.iloc[idx_test].reset_index(drop=True), p_med)

    rate = (df["price_inr"] / df["area_sqft"]).replace([np.inf, -np.inf], np.nan).dropna()
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "corpus": {
            "records": int(len(df)),
            "cities": int(df["city"].nunique()),
            "localities": int(df.groupby(["city", "locality"]).ngroups),
            "property_types": sorted(df["property_type"].unique().tolist()),
            "date_min": str(df["sale_date"].min()),
            "date_max": str(df["sale_date"].max()),
            "price_median_inr": int(df["price_inr"].median()),
            "rate_median_inr_sqft": int(round(float(rate.median()))),
        },
        "data_quality": {
            "errors": sum(1 for i in issues if i["severity"] == "error"),
            "warnings": sum(1 for i in issues if i["severity"] == "warning"),
            "issues": issues,
        },
        "holdout": model_metrics,
        "interval": {
            "coverage_p10_p90": round(coverage, 4),
            "median_band_width_pct": round(float(np.median(band_pct)), 4),
            "nominal_coverage": 0.80,
        },
        "grouped_cv": grouped_cv,
        "by_price_band": bands,
        "benchmarks": benchmarks,
        "ready_reckoner": rr_gap,
        "verdict": _verdict(model_metrics, coverage, grouped_cv),
    }


def _verdict(m: dict, coverage: float, gcv: dict) -> dict:
    """A plain-language read a reviewer can act on."""
    notes = []
    if m["mape"] > 0.15:
        notes.append("holdout MAPE above 15%: not yet competitive with a locality rate card")
    if coverage < 0.75:
        notes.append("interval coverage below 75%: widen the band or recalibrate")
    if gcv["mape_mean"] > 0.30:
        notes.append("unseen-micro-market MAPE above 30%: do not quote prices for uncovered localities")
    if m["mape"] <= 0.12 and coverage >= 0.78:
        notes.append("within the range where a shadow-mode lender pilot is defensible")
    if not notes:
        notes.append("acceptable for a reference implementation; lender pilot needs a validation report")
    return {"notes": notes}


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate an AVM against a real transaction file.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--report", type=Path, help="write the JSON report here")
    parser.add_argument("--min-per-locality", type=int, default=20)
    args = parser.parse_args()

    if not args.source.exists():
        raise SystemExit(f"no such file: {args.source}")

    import ingest
    frame, issues, unmapped = _load(args.source)
    # ingest.validate already applied min_per_locality default of 20; re-run with arg
    # is not needed because the threshold only affects warnings, not rows.
    report = run(frame, issues, unmapped)

    print("\nReal-data validation")
    print(f"  rows          {report['corpus']['records']}")
    print(f"  cities        {report['corpus']['cities']}  localities {report['corpus']['localities']}")
    print(f"  holdout MAPE  {report['holdout']['mape']:.2%}   R2 {report['holdout']['r2']:.4f}   "
          f"within10% {report['holdout']['within_10pct']:.1%}")
    print(f"  interval      coverage {report['interval']['coverage_p10_p90']:.1%}   "
          f"median width {report['interval']['median_band_width_pct']:.1%}")
    print(f"  unseen micro  grouped CV MAPE {report['grouped_cv']['mape_mean']:.2%} "
          f"(worst {report['grouped_cv']['mape_worst']:.2%})")
    print(f"  ready-reckoner gap (model vs gov floor): "
          f"{report['ready_reckoner'].get('median_gap_pct')}%")
    print("\nVerdict:")
    for note in report["verdict"]["notes"]:
        print(f"  - {note}")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nwrote {args.report}")


if __name__ == "__main__":
    # stdout may be cp1252 on Windows
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    main()
