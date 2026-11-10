"""Generate synthetic but realistic Indian property data for valuation model."""
import numpy as np
import pandas as pd

CITIES = {
    "Mumbai": {"base": 15000, "growth": 0.08, "lat": 19.076, "lon": 72.877},
    "Delhi": {"base": 12000, "growth": 0.07, "lat": 28.613, "lon": 77.209},
    "Bangalore": {"base": 10000, "growth": 0.09, "lat": 12.971, "lon": 77.594},
    "Hyderabad": {"base": 8000, "growth": 0.10, "lat": 17.385, "lon": 78.486},
    "Chennai": {"base": 9000, "growth": 0.06, "lat": 13.082, "lon": 80.270},
    "Pune": {"base": 9500, "growth": 0.08, "lat": 18.520, "lon": 73.856},
    "Kolkata": {"base": 7000, "growth": 0.05, "lat": 22.572, "lon": 88.363},
    "Ahmedabad": {"base": 7500, "growth": 0.07, "lat": 23.022, "lon": 72.571},
}

PROPERTY_TYPES = ["Apartment", "Villa", "Independent House", "Studio", "Penthouse"]
FURNISHING = ["Unfurnished", "Semi-Furnished", "Fully Furnished"]
LOCALITIES = {
    "Mumbai": ["Bandra", "Andheri", "Powai", "Thane", "Navi Mumbai", "Worli", "Juhu", "Malad"],
    "Delhi": ["Dwarka", "Rohini", "Saket", "Vasant Kunj", "Noida", "Gurgaon", "Lajpat Nagar", "Karol Bagh"],
    "Bangalore": ["Koramangala", "Whitefield", "Indiranagar", "HSR Layout", "Electronic City", "Jayanagar", "Marathahalli", "BTM Layout"],
    "Hyderabad": ["Gachibowli", "HITEC City", "Banjara Hills", "Jubilee Hills", "Kondapur", "Madhapur", "Kukatpally", "Secunderabad"],
    "Chennai": ["Anna Nagar", "Adyar", "Velachery", "OMR", "T Nagar", "Porur", "Tambaram", "Sholinganallur"],
    "Pune": ["Hinjewadi", "Kothrud", "Baner", "Wakad", "Viman Nagar", "Hadapsar", "Aundh", "Kharadi"],
    "Kolkata": ["Salt Lake", "New Town", "Park Street", "Howrah", "Behala", "Dum Dum", "Garia", "Rajarhat"],
    "Ahmedabad": ["Satellite", "Bopal", "Prahlad Nagar", "Vastrapur", "Maninagar", "Navrangpura", "Thaltej", "SG Highway"],
}

PREMIUM_LOCALITIES = {
    "Mumbai": ["Bandra", "Worli", "Juhu"],
    "Delhi": ["Vasant Kunj", "Gurgaon"],
    "Bangalore": ["Koramangala", "Indiranagar"],
    "Hyderabad": ["Banjara Hills", "Jubilee Hills"],
    "Chennai": ["Adyar", "Anna Nagar"],
    "Pune": ["Kothrud", "Baner"],
    "Kolkata": ["Park Street", "Salt Lake"],
    "Ahmedabad": ["Satellite", "Prahlad Nagar"],
}


def generate_data(n: int = 5000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    records = []

    for _ in range(n):
        city = rng.choice(list(CITIES.keys()))
        city_info = CITIES[city]
        locality = rng.choice(LOCALITIES[city])
        is_premium = locality in PREMIUM_LOCALITIES.get(city, [])

        prop_type = rng.choice(PROPERTY_TYPES, p=[0.45, 0.1, 0.2, 0.15, 0.1])
        furnishing = rng.choice(FURNISHING, p=[0.3, 0.4, 0.3])
        age = int(rng.integers(0, 25))
        bedrooms = int(rng.choice([1, 2, 3, 4, 5], p=[0.15, 0.35, 0.3, 0.15, 0.05]))
        bathrooms = max(1, bedrooms - int(rng.integers(0, 2)))
        area_sqft = int(rng.integers(400, 4000))
        if prop_type == "Studio":
            area_sqft = int(rng.integers(300, 600))
            bedrooms = 1
        elif prop_type == "Villa":
            area_sqft = int(rng.integers(2000, 5000))
        elif prop_type == "Penthouse":
            area_sqft = int(rng.integers(1500, 4000))
            bedrooms = rng.choice([3, 4, 5])

        floor = int(rng.integers(0, 25)) if prop_type in ("Apartment", "Studio", "Penthouse") else 0
        total_floors = max(floor, int(rng.integers(floor, 30))) if prop_type in ("Apartment", "Studio", "Penthouse") else 1
        parking = int(rng.integers(0, 3))
        lift = 1 if (floor > 3 or prop_type in ("Penthouse",)) else int(rng.choice([0, 1], p=[0.3, 0.7]))
        balcony = int(rng.integers(0, 3))
        metro_distance = round(float(rng.exponential(3)), 1)
        school_distance = round(float(rng.exponential(2)), 1)
        hospital_distance = round(float(rng.exponential(2.5)), 1)
        crime_index = round(float(rng.uniform(1, 10)), 1)

        # Price calculation
        base_price = city_info["base"]
        if is_premium:
            base_price *= 1.4
        if prop_type == "Villa":
            base_price *= 1.3
        elif prop_type == "Penthouse":
            base_price *= 1.5
        elif prop_type == "Studio":
            base_price *= 0.85

        furnishing_mult = {"Unfurnished": 1.0, "Semi-Furnished": 1.08, "Fully Furnished": 1.18}[furnishing]
        age_discount = 1.0 - (age * 0.005)
        area_price = base_price * area_sqft
        bedroom_premium = bedrooms * 0.03 * base_price * area_sqft
        floor_premium = (floor / max(total_floors, 1)) * 0.05 * base_price * area_sqft if total_floors > 1 else 0
        metro_discount = max(0.85, 1.0 - metro_distance * 0.02)
        lift_premium = 1.05 if lift else 1.0
        crime_discount = 1.0 - (crime_index - 5) * 0.01

        price = (area_price + bedroom_premium + floor_premium) * furnishing_mult * age_discount * metro_discount * lift_premium * crime_discount
        price = price * rng.uniform(0.9, 1.1)  # noise
        price = max(price, 500000)

        records.append({
            "city": city,
            "locality": locality,
            "property_type": prop_type,
            "furnishing": furnishing,
            "area_sqft": area_sqft,
            "bedrooms": bedrooms,
            "bathrooms": bathrooms,
            "floor": floor,
            "total_floors": total_floors,
            "age_years": age,
            "parking": parking,
            "lift": lift,
            "balcony": balcony,
            "metro_distance_km": metro_distance,
            "school_distance_km": school_distance,
            "hospital_distance_km": hospital_distance,
            "crime_index": crime_index,
            "is_premium_locality": int(is_premium),
            "price_inr": round(price, -3),
        })

    return pd.DataFrame(records)


if __name__ == "__main__":
    df = generate_data(5000)
    df.to_csv("data/properties.csv", index=False)
    print(f"Generated {len(df)} records")
    print(df.head())
    print(f"\nPrice range: {df['price_inr'].min():,.0f} - {df['price_inr'].max():,.0f}")
    print(f"Mean price: {df['price_inr'].mean():,.0f}")
    print(f"\nCities: {df['city'].value_counts().to_dict()}")
    print(f"Property types: {df['property_type'].value_counts().to_dict()}")
