"""
DisasterReady — GIS Utilities
Operasi geospasial: spatial join, distance, routing, dan peta risiko.

Library:
- GeoPandas (spatial join koordinat dengan polygon zona risiko)
- Shapely (geometri vektor)
- OpenRouteService API (routing relawan)

Sumber peta: OpenStreetMap contributors (openstreetmap.org)
"""

import os
import math
import json
import logging
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

ORS_API_KEY = os.getenv("OPENROUTESERVICE_API_KEY", "")
ORS_BASE_URL = os.getenv("ORS_BASE_URL", "https://api.openrouteservice.org")


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Hitung jarak haversine (km) antara dua titik GPS."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def filter_residents_in_zone(residents: list[dict], zone_bounds: dict) -> list[dict]:
    """
    Filter warga yang berada di dalam zona risiko.
    zone_bounds: {"north": float, "south": float, "east": float, "west": float}
    Fallback dari GeoPandas spatial join (tidak butuh install GDAL untuk demo).
    """
    n, s, e, w = zone_bounds["north"], zone_bounds["south"], zone_bounds["east"], zone_bounds["west"]
    return [
        r for r in residents
        if s <= r["lat"] <= n and w <= r["lon"] <= e
    ]


def filter_residents_in_districts(residents: list[dict], district_ids: list[str]) -> list[dict]:
    """Filter warga berdasarkan district_id."""
    return [r for r in residents if r.get("district_id") in district_ids]


def find_nearest_volunteers(
    volunteers: list[dict],
    target_lat: float,
    target_lon: float,
    max_distance_km: float = 30.0,
    n: int = 50,
) -> list[dict]:
    """
    Temukan n relawan terdekat dari titik target.
    Returns list volunteer yang diurutkan berdasarkan jarak (ascending).
    """
    available = [v for v in volunteers if v.get("is_available", True)]

    with_distance = []
    for v in available:
        dist = haversine_distance(v["lat"], v["lon"], target_lat, target_lon)
        if dist <= max_distance_km:
            with_distance.append({**v, "_distance_km": round(dist, 3)})

    with_distance.sort(key=lambda v: v["_distance_km"])
    return with_distance[:n]


async def get_route(
    from_lat: float, from_lon: float,
    to_lat: float, to_lon: float,
    profile: str = "driving-car"
) -> Optional[dict]:
    """
    Ambil rute optimal dari OpenRouteService API.

    API: OpenRouteService v2
    Penyedia: HeiGIT / Heidelberg Institute for Geoinformation Technology
    Dokumentasi: https://openrouteservice.org/dev/#/api-docs
    Penggunaan: Optimasi rute relawan ke lokasi terdampak

    Returns:
        dict dengan distance_km, duration_minutes, geometry (polyline)
        None jika API tidak tersedia (fallback ke estimasi haversine)
    """
    if not ORS_API_KEY:
        # Fallback: estimasi berbasis haversine (tidak ada route geometry)
        dist = haversine_distance(from_lat, from_lon, to_lat, to_lon)
        return {
            "distance_km": round(dist, 2),
            "duration_minutes": round(dist * 60 / 40, 1),  # Asumsi 40km/jam
            "geometry": None,
            "source": "haversine_estimate",
        }

    url = f"{ORS_BASE_URL}/v2/directions/{profile}"
    headers = {"Authorization": ORS_API_KEY, "Content-Type": "application/json"}
    body = {
        "coordinates": [[from_lon, from_lat], [to_lon, to_lat]],
        "format": "json",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=body, headers=headers)
            response.raise_for_status()
            data = response.json()

        route = data["routes"][0]["summary"]
        return {
            "distance_km": round(route["distance"] / 1000, 2),
            "duration_minutes": round(route["duration"] / 60, 1),
            "geometry": data["routes"][0].get("geometry"),
            "source": "openrouteservice",
        }
    except Exception as e:
        logger.warning(f"ORS API error: {e}. Fallback ke haversine.")
        dist = haversine_distance(from_lat, from_lon, to_lat, to_lon)
        return {
            "distance_km": round(dist, 2),
            "duration_minutes": round(dist * 60 / 40, 1),
            "geometry": None,
            "source": "haversine_estimate",
        }


def create_risk_geojson(
    district_risks: list[dict],
    districts_meta: dict
) -> dict:
    """
    Buat GeoJSON peta risiko per kecamatan.

    Args:
        district_risks: [{"district_id": str, "risk_level": str, "risk_score": float, ...}]
        districts_meta: Dict metadata kecamatan dengan koordinat

    Returns:
        GeoJSON FeatureCollection yang bisa ditampilkan di Leaflet.js
    """
    RISK_COLORS = {
        "critical": "#FF0000",
        "high":     "#FF6600",
        "medium":   "#FFAA00",
        "low":      "#FFFF00",
        "safe":     "#00AA00",
    }

    features = []
    for risk in district_risks:
        did = risk["district_id"]
        meta = districts_meta.get(did, {})
        if not meta:
            continue

        lat = meta.get("lat", 0)
        lon = meta.get("lon", 0)
        d = 0.03  # ~3km radius untuk polygon kotak

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [lon - d, lat - d],
                    [lon + d, lat - d],
                    [lon + d, lat + d],
                    [lon - d, lat + d],
                    [lon - d, lat - d],
                ]],
            },
            "properties": {
                "district_id": did,
                "district_name": meta.get("name", did),
                "risk_level": risk["risk_level"],
                "risk_score": risk.get("risk_score", 0),
                "rainfall_mm": risk.get("rainfall_mm", 0),
                "affected_residents": risk.get("affected_residents", 0),
                "vulnerable_residents": risk.get("vulnerable_residents", 0),
                "fill_color": RISK_COLORS.get(risk["risk_level"], "#GRAY"),
                "confidence": risk.get("confidence", 0.0),
                "reasoning": risk.get("reasoning", ""),
            },
        }
        features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": features,
        "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    }
