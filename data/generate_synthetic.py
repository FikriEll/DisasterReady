"""
DisasterReady — Synthetic Data Generator
Menghasilkan dataset warga dan relawan sintetis untuk demo lomba.
Data terinspirasi dari demografi nyata Jabodetabek (BPS 2023), 
namun sepenuhnya fiktif — tidak ada data pribadi nyata.
"""

import json
import random
import math
from datetime import datetime

random.seed(42)  # Reproducible output

# ── Kecamatan Jabodetabek dengan koordinat pusat ──────────────────────────────
DISTRICTS = [
    {"id": "bogor_tengah",     "name": "Bogor Tengah",     "lat": -6.5954, "lon": 106.7977, "city": "Bogor"},
    {"id": "bogor_selatan",    "name": "Bogor Selatan",    "lat": -6.6450, "lon": 106.7920, "city": "Bogor"},
    {"id": "bogor_utara",      "name": "Bogor Utara",      "lat": -6.5623, "lon": 106.7891, "city": "Bogor"},
    {"id": "cibinong",         "name": "Cibinong",         "lat": -6.4800, "lon": 106.8537, "city": "Kabupaten Bogor"},
    {"id": "gunung_putri",     "name": "Gunung Putri",     "lat": -6.4560, "lon": 106.9301, "city": "Kabupaten Bogor"},
    {"id": "ciawi",            "name": "Ciawi",            "lat": -6.6854, "lon": 106.8712, "city": "Kabupaten Bogor"},
    {"id": "cisarua",          "name": "Cisarua",          "lat": -6.7060, "lon": 106.9464, "city": "Kabupaten Bogor"},
    {"id": "ciomas",           "name": "Ciomas",           "lat": -6.6199, "lon": 106.7638, "city": "Kabupaten Bogor"},
    {"id": "dramaga",          "name": "Dramaga",          "lat": -6.5545, "lon": 106.7243, "city": "Kabupaten Bogor"},
    {"id": "depok_tengah",     "name": "Depok",            "lat": -6.4025, "lon": 106.7942, "city": "Depok"},
]

FIRST_NAMES_FEMALE = [
    "Siti", "Dewi", "Sri", "Nurul", "Rina", "Ani", "Yuli", "Fitri",
    "Hana", "Indah", "Maya", "Dina", "Rini", "Lina", "Nadia", "Putri",
    "Sari", "Wati", "Evi", "Tuti", "Lia", "Ida", "Ayu", "Retno"
]

FIRST_NAMES_MALE = [
    "Budi", "Ahmad", "Hendra", "Deni", "Rudi", "Agus", "Eko", "Joko",
    "Wahyu", "Rizky", "Fajar", "Bayu", "Dian", "Andi", "Yoga", "Rama",
    "Irfan", "Hafiz", "Dimas", "Arif", "Reza", "Gilang", "Taufik", "Syahrul"
]

LAST_NAMES = [
    "Santoso", "Wijaya", "Kusuma", "Pratama", "Hidayat", "Setiawan",
    "Nugroho", "Purnomo", "Rahayu", "Susanto", "Hartono", "Wibowo",
    "Saputra", "Firmansyah", "Iskandar", "Hasibuan", "Siregar", "Lubis",
    "Nasution", "Harahap", "Panjaitan", "Saragih", "Manurung", "Sirait"
]

DISABILITIES = ["none", "none", "none", "none", "none", "none", "none",
                 "visual_impairment", "mobility_impairment", "hearing_impairment"]


def random_point_near(lat, lon, radius_km=2.5):
    """Generate random GPS point within radius_km of center."""
    r = radius_km / 111.0  # degrees
    u = random.uniform(0, 1)
    v = random.uniform(0, 1)
    w = r * math.sqrt(u)
    t = 2 * math.pi * v
    x = w * math.cos(t)
    y = w * math.sin(t)
    return round(lat + y, 6), round(lon + x, 6)


def generate_residents(total=2000):
    """Generate synthetic resident records (warga terdaftar)."""
    residents = []

    for i in range(total):
        gender = random.choice(["F", "M"])
        first_name = random.choice(FIRST_NAMES_FEMALE if gender == "F" else FIRST_NAMES_MALE)
        last_name = random.choice(LAST_NAMES)

        # Distribusi usia sesuai demografi Bogor (BPS 2023)
        age_group = random.choices(
            ["balita", "anak", "dewasa", "lansia"],
            weights=[8, 20, 58, 14],
            k=1
        )[0]

        if age_group == "balita":
            age = random.randint(0, 4)
        elif age_group == "anak":
            age = random.randint(5, 17)
        elif age_group == "dewasa":
            age = random.randint(18, 59)
        else:
            age = random.randint(60, 88)

        district = random.choice(DISTRICTS)
        lat, lon = random_point_near(district["lat"], district["lon"])
        disability = random.choice(DISABILITIES)

        # Nomor telepon (format Indonesia, fiktif)
        phone = f"+628{random.randint(10000000000, 99999999999)}"
        # Telegram user_id (fiktif)
        telegram_id = random.randint(100000000, 999999999) if random.random() > 0.3 else None

        residents.append({
            "id": f"RES-{i+1:04d}",
            "name": f"{first_name} {last_name}",
            "gender": gender,
            "age": age,
            "age_group": age_group,
            "disability": disability,
            "district_id": district["id"],
            "district_name": district["name"],
            "city": district["city"],
            "lat": lat,
            "lon": lon,
            "phone": phone,
            "telegram_id": telegram_id,
            "has_whatsapp": random.random() > 0.35,
            "registered_at": "2026-01-15T08:00:00Z",
        })

    return residents


VOLUNTEER_ORGS = [
    "Palang Merah Indonesia",
    "Basarnas Jabar",
    "BPBD Kabupaten Bogor",
    "Pramuka Siaga Bencana",
    "Tagana (Taruna Siaga Bencana)",
    "Relawan Desa Tangguh",
]

VOLUNTEER_SPECIALTIES = [
    "evakuasi", "medis", "logistik", "SAR", "komunikasi", "shelter"
]


def generate_volunteers(total=150):
    """Generate synthetic volunteer records (relawan terdaftar)."""
    volunteers = []

    for i in range(total):
        gender = random.choice(["F", "M"])
        first_name = random.choice(FIRST_NAMES_FEMALE if gender == "F" else FIRST_NAMES_MALE)
        last_name = random.choice(LAST_NAMES)
        district = random.choice(DISTRICTS)
        lat, lon = random_point_near(district["lat"], district["lon"], radius_km=4.0)
        org = random.choice(VOLUNTEER_ORGS)
        specialties = random.sample(VOLUNTEER_SPECIALTIES, k=random.randint(1, 3))

        volunteers.append({
            "id": f"VOL-{i+1:03d}",
            "name": f"{first_name} {last_name}",
            "gender": gender,
            "age": random.randint(20, 55),
            "organization": org,
            "specialties": specialties,
            "district_id": district["id"],
            "district_name": district["name"],
            "city": district["city"],
            "lat": lat,
            "lon": lon,
            "phone": f"+628{random.randint(10000000000, 99999999999)}",
            "telegram_id": random.randint(100000000, 999999999),
            "capacity": random.randint(5, 20),  # Max assisted per mission
            "vehicle": random.choice(["motor", "mobil", "truk", "motor"]),
            "is_available": True,
            "registered_at": "2025-10-01T08:00:00Z",
        })

    return volunteers


if __name__ == "__main__":
    print("🔧 Generating synthetic dataset...")

    residents = generate_residents(2000)
    volunteers = generate_volunteers(150)

    with open("data/synthetic/residents.json", "w", encoding="utf-8") as f:
        json.dump(residents, f, ensure_ascii=False, indent=2)
    print(f"✅ Generated {len(residents)} residents → data/synthetic/residents.json")

    with open("data/synthetic/volunteers.json", "w", encoding="utf-8") as f:
        json.dump(volunteers, f, ensure_ascii=False, indent=2)
    print(f"✅ Generated {len(volunteers)} volunteers → data/synthetic/volunteers.json")

    # Stats summary
    lansia = sum(1 for r in residents if r["age"] >= 60)
    balita = sum(1 for r in residents if r["age"] <= 4)
    difabel = sum(1 for r in residents if r["disability"] != "none")
    print(f"\n📊 Resident breakdown:")
    print(f"   Lansia (60+): {lansia} ({lansia/len(residents)*100:.1f}%)")
    print(f"   Balita (0-4): {balita} ({balita/len(residents)*100:.1f}%)")
    print(f"   Difabel:      {difabel} ({difabel/len(residents)*100:.1f}%)")
    print(f"\n📊 Volunteer breakdown: {len(volunteers)} relawan dari {len(VOLUNTEER_ORGS)} organisasi")
