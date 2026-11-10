"""Train property valuation model."""
import json
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import mean_absolute_error, r2_score, mean_absolute_percentage_error
import joblib
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
MODEL_DIR = Path(__file__).parent / "models"
MODEL_DIR.mkdir(exist_ok=True)

CATEGORICAL = ["city", "locality", "property_type", "furnishing"]
NUMERICAL = ["area_sqft", "bedrooms", "bathrooms", "floor", "total_floors", "age_years",
             "parking", "lift", "balcony", "metro_distance_km", "school_distance_km",
             "hospital_distance_km", "crime_index", "is_premium_locality"]


def train():
    df = pd.read_csv(DATA_DIR / "properties.csv")

    # Encode categoricals
    encoders = {}
    for col in CATEGORICAL:
        le = LabelEncoder()
        df[col + "_enc"] = le.fit_transform(df[col])
        encoders[col] = le

    feature_cols = [c + "_enc" for c in CATEGORICAL] + NUMERICAL
    X = df[feature_cols].values
    y = df["price_inr"].values

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # Train Gradient Boosting
    model = GradientBoostingRegressor(
        n_estimators=200, max_depth=6, learning_rate=0.1,
        subsample=0.8, random_state=42
    )
    model.fit(X_train, y_train)

    # Evaluate
    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    mape = mean_absolute_percentage_error(y_test, y_pred)

    # Cross-validation
    cv_scores = cross_val_score(model, X, y, cv=5, scoring="r2")

    # Feature importance
    importances = sorted(zip(feature_cols, model.feature_importances_), key=lambda x: -x[1])

    metrics = {
        "model": "GradientBoostingRegressor",
        "n_samples": len(df),
        "n_features": len(feature_cols),
        "feature_names": feature_cols,
        "test_mae": round(mae, 0),
        "test_r2": round(r2, 4),
        "test_mape": round(mape, 4),
        "cv_r2_mean": round(float(cv_scores.mean()), 4),
        "cv_r2_std": round(float(cv_scores.std()), 4),
        "feature_importance": [{"feature": f, "importance": round(float(imp), 4)} for f, imp in importances],
        "price_range": {"min": int(df["price_inr"].min()), "max": int(df["price_inr"].max()), "mean": int(df["price_inr"].mean())},
        "cities": df["city"].nunique(),
        "property_types": df["property_type"].nunique(),
    }

    # Save model, encoders, metrics
    joblib.dump({"model": model, "encoders": encoders, "feature_cols": feature_cols}, MODEL_DIR / "valuation_model.joblib")
    with open(MODEL_DIR / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"R² (test): {r2:.4f}")
    print(f"MAE: {mae:,.0f} INR")
    print(f"MAPE: {mape:.2%}")
    print(f"CV R²: {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")
    print(f"\nTop features:")
    for f, imp in importances[:8]:
        print(f"  {f}: {imp:.4f}")

    return metrics


if __name__ == "__main__":
    train()
