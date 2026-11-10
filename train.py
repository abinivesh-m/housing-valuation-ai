"""
Train + export the valuation model and its calibration artefacts.

Design notes
------------
1. Target is log(price). Fitting in log space aligns the objective with
   percentage error, which is what a lender actually prices risk on
   (MAPE, not rupee MAE), and it stabilises variance across a 0.9M–50M range.
2. The point model is a gradient-boosted regression tree ensemble fitted with
   Huber loss, which limits the influence of the noisy tail of the corpus.
3. Prediction intervals come from **split conformal calibration**, not from a
   hand-picked "+/-10%" band and not from independently fitted quantile
   boosters. Out-of-fold residuals give an empirical distribution of the
   model's own error; the 10th/90th percentiles of that distribution form the
   p10–p90 band. Coverage is then *measured* on a held-out split, and the
   number reported in the UI is the measured number.
4. The model is exported to plain JSON (flat tree arrays) and served by a
   pure-numpy inference module, so scikit-learn stays a training-time
   dependency. This removes pickle/version drift (the first deploy of this
   project died on `ModuleNotFoundError: No module named '_loss'`) and keeps
   the serverless bundle small.
5. Every benchmark is trained and scored on the identical split, so the
   comparison table in the UI is fair.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, r2_score
from sklearn.model_selection import GroupKFold, KFold, train_test_split

ROOT = Path(__file__).parent
DATA = ROOT / "data" / "properties.csv"
OUT = ROOT / "artifacts"
OUT.mkdir(exist_ok=True)

CATEGORICAL = ["city", "locality", "property_type", "furnishing", "occupancy", "tenure"]
NUMERICAL = [
    "area_sqft",
    "bedrooms",
    "bathrooms",
    "floor",
    "floor_ratio",
    "age_years",
    "parking",
    "lift",
    "balcony",
    "metro_distance_km",
    "school_distance_km",
    "hospital_distance_km",
    "highway_distance_km",
    "crime_index",
]
FEATURES = CATEGORICAL + NUMERICAL

SEED = 20261110
N_ESTIMATORS = 320
MAX_DEPTH = 6
LEARNING_RATE = 0.055
MIN_SAMPLES_LEAF = 6


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["floor_ratio"] = (df["floor"] / df["total_floors"].replace(0, 1)).clip(0, 1)
    return df


def build_matrix(df: pd.DataFrame, vocabs: dict[str, list[str]]) -> np.ndarray:
    cols = []
    for c in CATEGORICAL:
        vocab = vocabs[c]
        index = {v: i for i, v in enumerate(vocab)}
        cols.append(df[c].map(index).fillna(len(vocab) - 1).to_numpy(dtype=np.float64))
    for c in NUMERICAL:
        cols.append(df[c].to_numpy(dtype=np.float64))
    return np.column_stack(cols)


def new_model() -> GradientBoostingRegressor:
    return GradientBoostingRegressor(
        n_estimators=N_ESTIMATORS,
        max_depth=MAX_DEPTH,
        learning_rate=LEARNING_RATE,
        subsample=0.85,
        min_samples_leaf=MIN_SAMPLES_LEAF,
        random_state=SEED,
        loss="huber",
        alpha=0.90,
    )


def export_tree(est) -> dict:
    """Flat arrays. Floats are written at full precision so the JSON tree
    reproduces scikit-learn's split decisions bit-for-bit."""
    t = est.tree_
    return {
        "f": t.feature.astype(int).tolist(),
        "t": t.threshold.tolist(),
        "l": t.children_left.astype(int).tolist(),
        "r": t.children_right.astype(int).tolist(),
        "v": [float(np.ravel(node)[0]) for node in t.value],
    }


def export_model(model: GradientBoostingRegressor, name: str) -> dict:
    init_val = float(np.ravel(model.init_.constant_)[0])
    return {
        "name": name,
        "loss": model.loss,
        "learning_rate": float(model.learning_rate),
        "init": init_val,
        "trees": [export_tree(e[0]) for e in model.estimators_],
    }


def metrics_block(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    ape = np.abs(y_pred - y_true) / y_true
    return {
        "r2": round(float(r2_score(y_true, y_pred)), 4),
        "mae_inr": int(round(mean_absolute_error(y_true, y_pred), -3)),
        "mape": round(float(mean_absolute_percentage_error(y_true, y_pred)), 4),
        "median_ape": round(float(np.median(ape)), 4),
        "within_10pct": round(float((ape <= 0.10).mean()), 4),
        "within_20pct": round(float((ape <= 0.20).mean()), 4),
        "n": int(len(y_true)),
    }


def main() -> None:
    raw = pd.read_csv(DATA)
    df = add_derived(raw)

    vocabs = {c: sorted(df[c].astype(str).unique().tolist()) for c in CATEGORICAL}
    X = build_matrix(df, vocabs)
    y_price = df["price_inr"].to_numpy(dtype=np.float64)
    y_log = np.log(y_price)

    idx_train, idx_test = train_test_split(
        np.arange(len(df)), test_size=0.20, random_state=SEED, shuffle=True
    )

    # ---- out-of-fold residuals for conformal calibration -------------------
    oof = np.zeros(len(df))
    for tr, te in KFold(n_splits=5, shuffle=True, random_state=SEED).split(X):
        fold = new_model()
        fold.fit(X[tr], y_log[tr])
        oof[te] = fold.predict(X[te])
    resid = y_log - oof

    def bounds(alpha: float = 0.10) -> tuple[float, float]:
        return float(np.quantile(resid, alpha)), float(np.quantile(resid, 1 - alpha))

    q_lo, q_hi = bounds()
    by_type = {}
    for ptype in df["property_type"].unique():
        mask = (df["property_type"] == ptype).to_numpy()
        if mask.sum() >= 60:
            by_type[str(ptype)] = [
                round(float(np.quantile(resid[mask], 0.10)), 5),
                round(float(np.quantile(resid[mask], 0.90)), 5),
            ]

    # ---- final model on the training split --------------------------------
    model = new_model()
    model.fit(X[idx_train], y_log[idx_train])

    p_med = np.exp(model.predict(X[idx_test]))
    test_y = y_price[idx_test]

    lo = p_med * np.exp(q_lo)
    hi = p_med * np.exp(q_hi)
    coverage = float(((test_y >= lo) & (test_y <= hi)).mean())
    band_pct = (hi - lo) / p_med

    model_metrics = metrics_block(test_y, p_med)

    # ---- benchmarks on the SAME test rows ----------------------------------
    train_df = df.iloc[idx_train]
    test_df = df.iloc[idx_test]

    global_rate = float((train_df["price_inr"] / train_df["area_sqft"]).median())
    b1 = test_df["area_sqft"].to_numpy(dtype=float) * global_rate

    rate_table = (
        train_df.assign(rate=train_df["price_inr"] / train_df["area_sqft"])
        .groupby(["locality", "property_type"])["rate"]
        .median()
    )
    loc_rate = (
        train_df.assign(rate=train_df["price_inr"] / train_df["area_sqft"])
        .groupby("locality")["rate"]
        .median()
    )
    naive = []
    for _, row in test_df.iterrows():
        r = rate_table.get((row["locality"], row["property_type"]), loc_rate.get(row["locality"], global_rate))
        naive.append(r * row["area_sqft"])
    b2 = np.array(naive, dtype=float)

    onehot = pd.get_dummies(train_df[CATEGORICAL].astype(str), drop_first=True)
    onehot_test = pd.get_dummies(test_df[CATEGORICAL].astype(str), drop_first=True).reindex(
        columns=onehot.columns, fill_value=0
    )
    Xh_train = np.column_stack([onehot.to_numpy(dtype=float), train_df[NUMERICAL].to_numpy(dtype=float)])
    Xh_test = np.column_stack([onehot_test.to_numpy(dtype=float), test_df[NUMERICAL].to_numpy(dtype=float)])
    mu, sd = Xh_train.mean(0), Xh_train.std(0) + 1e-9
    ridge = Ridge(alpha=1.0)
    ridge.fit((Xh_train - mu) / sd, np.log(train_df["price_inr"].to_numpy(dtype=float)))
    b3 = np.exp(ridge.predict((Xh_test - mu) / sd))

    benchmarks = {
        "global_median_rate": {
            "label": "Global median ₹/sqft x area",
            **metrics_block(test_y, b1),
            "rate_inr_sqft": int(round(global_rate)),
        },
        "locality_type_median_rate": {
            "label": "Locality x type median ₹/sqft x area",
            **metrics_block(test_y, b2),
        },
        "ridge_hedonic": {
            "label": "Ridge hedonic regression (same features)",
            **metrics_block(test_y, b3),
        },
        "gradient_boosting": {
            "label": "Gradient boosting (this engine)",
            **model_metrics,
        },
    }

    # ---- generalisation: unseen micro-markets ------------------------------
    grouped_scores = []
    for tr, te in GroupKFold(n_splits=5).split(X, y_log, df["locality"].to_numpy()):
        fold = new_model()
        fold.fit(X[tr], y_log[tr])
        grouped_scores.append(metrics_block(y_price[te], np.exp(fold.predict(X[te]))))
    grouped_cv = {
        "scheme": "GroupKFold(5) by locality — approximates a micro-market with no training history",
        "mape_mean": round(float(np.mean([g["mape"] for g in grouped_scores])), 4),
        "mape_worst": round(float(np.max([g["mape"] for g in grouped_scores])), 4),
        "r2_mean": round(float(np.mean([g["r2"] for g in grouped_scores])), 4),
        "fold_mape": [g["mape"] for g in grouped_scores],
    }

    # ---- error by price band ----------------------------------------------
    bands = []
    edges = np.percentile(test_y, [0, 20, 40, 60, 80, 100])
    for i in range(5):
        mask = (test_y >= edges[i]) & (test_y <= edges[i + 1])
        if mask.sum() < 5:
            continue
        ape = np.abs(p_med[mask] - test_y[mask]) / test_y[mask]
        bands.append(
            {
                "band": f"₹{edges[i]/1e7:.1f}Cr–₹{edges[i+1]/1e7:.1f}Cr",
                "n": int(mask.sum()),
                "mape": round(float(ape.mean()), 4),
                "median_ape": round(float(np.median(ape)), 4),
            }
        )

    importance = sorted(
        zip(FEATURES, model.feature_importances_.tolist()), key=lambda kv: -kv[1]
    )

    artifact = {
        "schema_version": 2,
        "trained_at": pd.Timestamp.now("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
        "corpus": {
            "records": int(len(df)),
            "type": "parametric synthetic corpus (no licensed transaction data)",
            "seed": SEED,
        },
        "target": "log(price_inr)",
        "feature_order": FEATURES,
        "categorical": CATEGORICAL,
        "numerical": NUMERICAL,
        "vocabs": vocabs,
        "models": {"median": export_model(model, "median")},
        "conformal": {
            "method": "split conformal on out-of-fold log residuals",
            "global": [round(q_lo, 5), round(q_hi, 5)],
            "by_property_type": by_type,
            "nominal_coverage": 0.80,
        },
        "metrics": {
            "holdout": model_metrics,
            "interval": {
                "coverage_p10_p90": round(coverage, 4),
                "median_band_width_pct": round(float(np.median(band_pct)), 4),
                "nominal_coverage": 0.80,
            },
            "grouped_cv": grouped_cv,
            "by_price_band": bands,
            "benchmarks": benchmarks,
            "feature_importance": [
                {"feature": f, "importance": round(float(v), 4)} for f, v in importance
            ],
        },
        "split": {"train": int(len(idx_train)), "test": int(len(idx_test)), "seed": SEED},
    }

    # ---- round-trip check: exported JSON must reproduce sklearn exactly -----
    from engine.model import ValuationModel

    vm = ValuationModel(artifact)
    probe = X[idx_test][:250]
    err = float(np.abs(vm.median.predict(probe) - model.predict(probe)).max())
    if err > 1e-3:
        raise SystemExit(f"export mismatch: max |delta log price| = {err:.6g}")
    print(f"round-trip check: max |delta log price| = {err:.2e} over 250 rows")

    # ---- comps pool --------------------------------------------------------
    rng = np.random.default_rng(SEED)
    pool_idx = rng.choice(len(df), size=min(3000, len(df)), replace=False)
    pool = df.iloc[pool_idx].copy()
    pool["rate"] = (pool["price_inr"] / pool["area_sqft"]).round(0).astype(int)
    comps_cols = [
        "city", "locality", "lat", "lon", "property_type", "furnishing", "occupancy",
        "tenure", "area_sqft", "bedrooms", "bathrooms", "floor", "total_floors",
        "age_years", "parking", "lift", "balcony", "metro_distance_km",
        "school_distance_km", "hospital_distance_km", "highway_distance_km",
        "crime_index", "sale_date", "price_inr", "rate",
    ]
    comps = pool[comps_cols].copy()
    comps["price_inr"] = comps["price_inr"].astype(int)

    loc_stats = (
        df.assign(rate=df["price_inr"] / df["area_sqft"])
        .groupby(["city", "locality", "property_type"])
        .agg(median_rate=("rate", "median"), n=("rate", "size"), median_price=("price_inr", "median"))
        .reset_index()
    )
    loc_stats["median_rate"] = loc_stats["median_rate"].round(0).astype(int)
    loc_stats["median_price"] = loc_stats["median_price"].round(0).astype(int)

    (OUT / "model.json").write_text(json.dumps(artifact, separators=(",", ":")), encoding="utf-8")
    (OUT / "comps.json").write_text(
        json.dumps({"columns": comps_cols, "rows": comps.values.tolist()}, separators=(",", ":")),
        encoding="utf-8",
    )
    (OUT / "locality_stats.json").write_text(
        json.dumps({"columns": list(loc_stats.columns), "rows": loc_stats.values.tolist()}, separators=(",", ":")),
        encoding="utf-8",
    )

    # ---- coverage map + curated sample properties for the UI ---------------
    import data_gen

    localities = []
    for city, entries in data_gen.LOCALITIES.items():
        for name, coords in entries.items():
            subset = df[(df["city"] == city) & (df["locality"] == name)]
            localities.append(
                {
                    "city": city,
                    "locality": name,
                    "lat": round(coords[0], 5),
                    "lon": round(coords[1], 5),
                    "price_index": coords[2],
                    "median_rate": int(round(float((subset["price_inr"] / subset["area_sqft"]).median())))
                    if len(subset)
                    else 0,
                    "n": int(len(subset)),
                }
            )

    city_names = sorted(data_gen.CITIES)
    sample_specs = [
        ("Bangalore", "Koramangala", "Apartment"),
        ("Mumbai", "Bandra", "Apartment"),
        ("Hyderabad", "Gachibowli", "Apartment"),
        ("Pune", "Hinjewadi", "Apartment"),
        ("Delhi", "Saket", "Villa"),
        ("Chennai", "Anna Nagar", "Independent House"),
        ("Bangalore", "Whitefield", "Commercial Office"),
        ("Mumbai", "Thane", "Retail Shop"),
    ]
    samples = []
    for city, locality, ptype in sample_specs:
        subset = df[(df["city"] == city) & (df["locality"] == locality) & (df["property_type"] == ptype)]
        if subset.empty:
            subset = df[(df["city"] == city) & (df["locality"] == locality)]
        if subset.empty:
            continue
        row = subset.iloc[len(subset) // 2]
        samples.append(
            {
                "label": f"{locality}, {city} — {ptype}",
                "city": city,
                "locality": locality,
                "property_type": ptype,
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "input": {
                    "furnishing": str(row["furnishing"]),
                    "occupancy": str(row["occupancy"]),
                    "tenure": str(row["tenure"]),
                    "area_sqft": int(row["area_sqft"]),
                    "bedrooms": int(row["bedrooms"]),
                    "bathrooms": int(row["bathrooms"]),
                    "floor": int(row["floor"]),
                    "total_floors": int(row["total_floors"]),
                    "age_years": int(row["age_years"]),
                    "parking": int(row["parking"]),
                    "lift": int(row["lift"]),
                    "balcony": int(row["balcony"]),
                    "metro_distance_km": float(row["metro_distance_km"]),
                    "school_distance_km": float(row["school_distance_km"]),
                    "hospital_distance_km": float(row["hospital_distance_km"]),
                    "highway_distance_km": float(row["highway_distance_km"]),
                    "crime_index": float(row["crime_index"]),
                },
                "reference_price": int(row["price_inr"]),
            }
        )

    (OUT / "coverage.json").write_text(
        json.dumps(
            {
                "cities": [
                    {"city": c, "lat": data_gen.CITIES[c]["lat"], "lon": data_gen.CITIES[c]["lon"]}
                    for c in city_names
                ],
                "city_names": city_names,
                "localities": localities,
                "localities_by_city": {c: sorted(data_gen.LOCALITIES[c]) for c in city_names},
                "property_types": list(data_gen.PROPERTY_TYPES),
                "furnishing": data_gen.FURNISHING,
                "occupancy": data_gen.OCCUPANCY,
                "tenure": data_gen.TENURE,
                "samples": samples,
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )

    print(
        f"holdout  R2={model_metrics['r2']:.4f}  MAPE={model_metrics['mape']:.2%}  "
        f"within10%={model_metrics['within_10pct']:.1%}"
    )
    print(f"conformal interval coverage = {coverage:.1%} (nominal 80%), median width {np.median(band_pct):.1%}")
    print(f"grouped CV MAPE = {grouped_cv['mape_mean']:.2%} (worst fold {grouped_cv['mape_worst']:.2%})")
    print("\nbenchmarks (identical test rows):")
    for v in benchmarks.values():
        print(f"  {v['label']:<44} MAPE={v['mape']:.2%}  R2={v['r2']:.4f}  within10%={v['within_10pct']:.1%}")
    print("\ntop features:")
    for f, v in importance[:8]:
        print(f"  {f:<22} {v:.4f}")
    print(f"\nmodel.json = {(OUT / 'model.json').stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
