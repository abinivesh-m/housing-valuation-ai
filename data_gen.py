"""
Parametric corpus generator for the HousingValuation AI prototype.

IMPORTANT — DATA PROVENANCE
---------------------------
This generator produces a *synthetic* corpus. No licensed transaction,
registry, or satellite data is used. Records are drawn from a parametric
pricing function whose coefficients are set by hand so that the resulting
price surface behaves like Indian urban housing markets (city ordering,
locality premium, area elasticity, age depreciation, floor premium,
furnishing uplift, infrastructure distance decay).

Why ship a synthetic corpus?
  Real AVM training requires paid registry/transaction feeds (see
  docs/DATA_STRATEGY.md for the production data plan). The prototype is
  therefore honest about its corpus: every accuracy number reported by
  train.py is measured on this synthetic corpus and is NOT evidence of
  real-world AVM performance. What the prototype does prove is that the
  full pipeline — feature contract, model, interval estimation,
  attribution, comparable selection, lending policy, audit trail — works
  end to end and is ready to be pointed at a real feed.

Latitude/longitude values are approximate locality centroids so that the
geo-enrichment layer (OpenStreetMap Overpass) can be exercised for real.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SEED = 20261110
N_RECORDS = 6000

CITIES = {
    "Mumbai": {"lat": 19.0760, "lon": 72.8777, "rate": 15000, "city_mult": 1.00},
    "Delhi": {"lat": 28.6139, "lon": 77.2090, "rate": 10300, "city_mult": 0.92},
    "Bangalore": {"lat": 12.9716, "lon": 77.5946, "rate": 8600, "city_mult": 0.88},
    "Hyderabad": {"lat": 17.3850, "lon": 78.4867, "rate": 6600, "city_mult": 0.82},
    "Pune": {"lat": 18.5204, "lon": 73.8567, "rate": 6500, "city_mult": 0.81},
    "Chennai": {"lat": 13.0827, "lon": 80.2707, "rate": 6200, "city_mult": 0.80},
    "Ahmedabad": {"lat": 23.0225, "lon": 72.5714, "rate": 4650, "city_mult": 0.74},
    "Kolkata": {"lat": 22.5726, "lon": 88.3639, "rate": 4600, "city_mult": 0.73},
}

# locality -> (lat, lon, locality price index)
LOCALITIES = {
    "Mumbai": {
        "Worli": (19.0176, 72.8156, 1.72),
        "Bandra": (19.0596, 72.8295, 1.58),
        "Juhu": (19.1075, 72.8263, 1.46),
        "Powai": (19.1176, 72.9060, 1.22),
        "Andheri": (19.1136, 72.8697, 1.12),
        "Malad": (19.1868, 72.8482, 0.94),
        "Thane": (19.2183, 72.9781, 0.86),
        "Navi Mumbai": (19.0330, 73.0297, 0.83),
    },
    "Delhi": {
        "Vasant Kunj": (28.5200, 77.1590, 1.48),
        "Saket": (28.5245, 77.2066, 1.32),
        "Gurgaon": (28.4595, 77.0266, 1.26),
        "Lajpat Nagar": (28.5677, 77.2433, 1.14),
        "Dwarka": (28.5921, 77.0460, 1.00),
        "Karol Bagh": (28.6519, 77.1909, 0.98),
        "Rohini": (28.7495, 77.0565, 0.89),
        "Noida": (28.5355, 77.3910, 0.92),
    },
    "Bangalore": {
        "Koramangala": (12.9352, 77.6245, 1.54),
        "Indiranagar": (12.9719, 77.6412, 1.48),
        "HSR Layout": (12.9121, 77.6446, 1.34),
        "Jayanagar": (12.9250, 77.5938, 1.22),
        "Whitefield": (12.9698, 77.7500, 1.08),
        "Marathahalli": (12.9592, 77.6974, 1.04),
        "BTM Layout": (12.9166, 77.6101, 1.00),
        "Electronic City": (12.8452, 77.6602, 0.88),
    },
    "Hyderabad": {
        "Jubilee Hills": (17.4239, 78.4111, 1.66),
        "Banjara Hills": (17.4126, 78.4392, 1.58),
        "HITEC City": (17.4435, 78.3772, 1.22),
        "Gachibowli": (17.4401, 78.3489, 1.18),
        "Madhapur": (17.4483, 78.3915, 1.14),
        "Kondapur": (17.4615, 78.3646, 1.02),
        "Kukatpally": (17.4849, 78.4138, 0.92),
        "Secunderabad": (17.4399, 78.4983, 0.87),
    },
    "Pune": {
        "Kothrud": (18.5074, 73.8077, 1.32),
        "Baner": (18.5590, 73.7868, 1.28),
        "Aundh": (18.5590, 73.8078, 1.20),
        "Viman Nagar": (18.5679, 73.9143, 1.14),
        "Kharadi": (18.5516, 73.9400, 1.10),
        "Wakad": (18.5975, 73.7625, 1.00),
        "Hinjewadi": (18.5913, 73.7389, 0.96),
        "Hadapsar": (18.5089, 73.9260, 0.90),
    },
    "Chennai": {
        "Adyar": (13.0067, 80.2570, 1.42),
        "Anna Nagar": (13.0850, 80.2101, 1.34),
        "T Nagar": (13.0418, 80.2341, 1.22),
        "Velachery": (12.9750, 80.2210, 1.08),
        "Sholinganallur": (12.9010, 80.2279, 1.00),
        "Porur": (13.0359, 80.1560, 0.96),
        "OMR": (12.9300, 80.2300, 0.94),
        "Tambaram": (12.9249, 80.1000, 0.82),
    },
    "Ahmedabad": {
        "Prahlad Nagar": (23.0100, 72.5100, 1.36),
        "Satellite": (23.0300, 72.5100, 1.30),
        "Vastrapur": (23.0300, 72.5200, 1.24),
        "Thaltej": (23.0500, 72.5100, 1.20),
        "Navrangpura": (23.0300, 72.5600, 1.14),
        "SG Highway": (23.0300, 72.4900, 1.06),
        "Bopal": (23.0400, 72.4700, 0.94),
        "Maninagar": (22.9900, 72.6000, 0.86),
    },
    "Kolkata": {
        "Park Street": (22.5530, 88.3520, 1.44),
        "Salt Lake": (22.5867, 88.4171, 1.24),
        "New Town": (22.5800, 88.4600, 1.16),
        "Rajarhat": (22.6100, 88.4700, 1.08),
        "Howrah": (22.5958, 88.2636, 0.92),
        "Dum Dum": (22.6200, 88.4200, 0.88),
        "Behala": (22.4980, 88.3200, 0.86),
        "Garia": (22.4600, 88.3900, 0.80),
    },
}

# property_type -> (area band, base multiplier, typical bedrooms)
PROPERTY_TYPES = {
    "Apartment": {"area": (450, 2200), "mult": 1.00, "beds": [1, 2, 3, 4], "probs": [0.16, 0.38, 0.32, 0.14]},
    "Villa": {"area": (1800, 4800), "mult": 1.22, "beds": [3, 4, 5], "probs": [0.35, 0.45, 0.20]},
    "Independent House": {"area": (800, 3000), "mult": 1.06, "beds": [2, 3, 4], "probs": [0.30, 0.45, 0.25]},
    "Studio": {"area": (280, 620), "mult": 0.86, "beds": [1], "probs": [1.0]},
    "Penthouse": {"area": (1600, 4200), "mult": 1.42, "beds": [3, 4, 5], "probs": [0.35, 0.40, 0.25]},
    "Commercial Office": {"area": (600, 6000), "mult": 1.30, "beds": [0], "probs": [1.0]},
    "Retail Shop": {"area": (200, 1800), "mult": 1.48, "beds": [0], "probs": [1.0]},
    "Warehouse": {"area": (3000, 20000), "mult": 0.58, "beds": [0], "probs": [1.0]},
}

PROPERTY_TYPE_PROBS = [0.30, 0.09, 0.16, 0.08, 0.07, 0.16, 0.09, 0.05]
FURNISHING = ["Unfurnished", "Semi-Furnished", "Fully Furnished"]
FURNISHING_PROBS = [0.30, 0.42, 0.28]
FURNISHING_MULT = {"Unfurnished": 1.00, "Semi-Furnished": 1.07, "Fully Furnished": 1.15}

OCCUPANCY = ["Self-Occupied", "Rented", "Vacant"]
TENURE = ["Freehold", "Leasehold"]


def generate(n: int = N_RECORDS, seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []

    # Locality-weighted sampling: metro core gets more volume.
    city_names = list(CITIES)
    city_weights = np.array([CITIES[c]["city_mult"] for c in city_names])
    city_weights = city_weights / city_weights.sum()

    for _ in range(n):
        city = str(rng.choice(city_names, p=city_weights))
        locs = list(LOCALITIES[city])
        # transaction volume concentrates in mid-market localities, so weight
        # inversely to the price index rather than proportionally
        idx = np.array([LOCALITIES[city][l][2] for l in locs])
        loc_p = (1.0 / idx) ** 1.5
        loc_p = loc_p / loc_p.sum()
        locality = str(rng.choice(locs, p=loc_p))

        ptype = str(rng.choice(list(PROPERTY_TYPES), p=PROPERTY_TYPE_PROBS))
        spec = PROPERTY_TYPES[ptype]
        furnishing = str(rng.choice(FURNISHING, p=FURNISHING_PROBS))
        occupancy = str(rng.choice(OCCUPANCY, p=[0.55, 0.30, 0.15]))
        tenure = str(rng.choice(TENURE, p=[0.88, 0.12]))

        area = int(rng.integers(spec["area"][0], spec["area"][1]))
        bedrooms = int(rng.choice(spec["beds"], p=spec["probs"]))
        bathrooms = 0 if bedrooms == 0 else max(1, bedrooms - int(rng.integers(0, 2)))

        commercial = ptype in ("Commercial Office", "Retail Shop", "Warehouse")
        if commercial:
            floor = int(rng.integers(0, 12))
            total_floors = floor + int(rng.integers(1, 10))
        elif ptype in ("Villa", "Independent House"):
            floor, total_floors = int(rng.integers(0, 3)), int(rng.integers(1, 4))
        else:
            floor = int(rng.integers(0, 26))
            total_floors = floor + int(rng.integers(1, 26))

        age = int(np.clip(rng.gamma(2.0, 4.0), 0, 40))
        parking = int(rng.integers(0, 4)) if not commercial else int(rng.integers(0, 8))
        lift = 1 if (floor > 2 or ptype in ("Penthouse", "Apartment", "Commercial Office")) else int(rng.random() < 0.4)
        balcony = 0 if commercial else int(rng.integers(0, 3))

        metro_km = float(np.round(rng.exponential(2.2) + 0.15, 2))
        school_km = float(np.round(rng.exponential(1.5) + 0.1, 2))
        hospital_km = float(np.round(rng.exponential(1.8) + 0.1, 2))
        highway_km = float(np.round(rng.exponential(3.0) + 0.2, 2))
        crime_index = float(np.round(np.clip(rng.normal(5.2, 1.6), 1.0, 9.8), 1))

        lat0, lon0, loc_index = LOCALITIES[city][locality]
        lat = float(np.round(lat0 + rng.normal(0, 0.006), 6))
        lon = float(np.round(lon0 + rng.normal(0, 0.006), 6))

        # synthetic registration date inside a 24-month window, used by the
        # comparable-sales engine for recency weighting
        months_ago = int(rng.integers(0, 24))
        sale_date = (pd.Timestamp("2026-10-01") - pd.DateOffset(months=months_ago)).strftime("%Y-%m-01")

        # --- parametric price surface (synthetic, hand-set coefficients) ---
        rate = CITIES[city]["rate"] * loc_index * spec["mult"]
        base = area * rate

        # bedrooms add usable-value premium, not raw area
        bed_premium = 1.0 + 0.045 * max(bedrooms - 1, 0)
        # floor premium saturates and needs a lift in tall buildings
        floor_ratio = floor / max(total_floors, 1)
        floor_premium = 1.0 + (0.10 * floor_ratio if total_floors > 3 else 0.0)
        # depreciation: 1.1%/yr for first 15 yrs, 0.55%/yr after
        dep = 1.0 - (0.011 * min(age, 15) + 0.0055 * max(age - 15, 0))
        dep = max(dep, 0.55)
        furn = FURNISHING_MULT[furnishing]
        metro_d = 1.0 + 0.075 * np.exp(-metro_km / 1.8)
        school_d = 1.0 + 0.030 * np.exp(-school_km / 1.5)
        hosp_d = 1.0 + 0.025 * np.exp(-hospital_km / 2.0)
        hwy_d = 1.0 + 0.035 * np.exp(-highway_km / 3.0)
        lift_p = 1.045 if lift else 1.0
        park_p = 1.0 + 0.022 * min(parking, 3)
        balcony_p = 1.0 + 0.012 * min(balcony, 2)
        crime_p = 1.0 - (crime_index - 5.0) * 0.012
        tenure_p = 0.93 if tenure == "Leasehold" else 1.0
        occ_p = {"Self-Occupied": 1.0, "Rented": 1.035, "Vacant": 0.975}[occupancy]

        price = (
            base
            * bed_premium
            * floor_premium
            * dep
            * furn
            * metro_d
            * school_d
            * hosp_d
            * hwy_d
            * lift_p
            * park_p
            * balcony_p
            * crime_p
            * tenure_p
            * occ_p
        )
        # market noise: district-level dispersion, heavier for commercial
        noise_sd = 0.13 if commercial else 0.085
        price *= float(rng.lognormal(0.0, noise_sd))
        price = float(max(price, 850_000) if not commercial else max(price, 1_200_000))

        rows.append(
            {
                "city": city,
                "locality": locality,
                "lat": lat,
                "lon": lon,
                "property_type": ptype,
                "furnishing": furnishing,
                "occupancy": occupancy,
                "tenure": tenure,
                "area_sqft": area,
                "bedrooms": bedrooms,
                "bathrooms": bathrooms,
                "floor": floor,
                "total_floors": total_floors,
                "age_years": age,
                "parking": parking,
                "lift": lift,
                "balcony": balcony,
                "metro_distance_km": metro_km,
                "school_distance_km": school_km,
                "hospital_distance_km": hospital_km,
                "highway_distance_km": highway_km,
                "crime_index": crime_index,
                "sale_date": sale_date,
                "price_inr": int(round(price, -3)),
            }
        )

    return pd.DataFrame(rows)


if __name__ == "__main__":
    import pathlib

    out = pathlib.Path(__file__).parent / "data"
    out.mkdir(exist_ok=True)
    frame = generate()
    frame.to_csv(out / "properties.csv", index=False)
    print(f"wrote {len(frame)} rows -> data/properties.csv")
    print(frame["price_inr"].describe().apply(lambda v: f"{v:,.0f}"))
    print("\nmedian price by city (INR lakh):")
    print((frame.groupby("city")["price_inr"].median() / 1e5).round(1).sort_values(ascending=False))
    print("\nmedian rate by property type (INR/sqft):")
    rate_by_type = frame.groupby("property_type").apply(
        lambda d: (d["price_inr"] / d["area_sqft"]).median(), include_groups=False
    )
    print(rate_by_type.round(0).sort_values(ascending=False))
