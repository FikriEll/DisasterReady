"""
DisasterReady — BMKG API Client
Memantau data cuaca, curah hujan, dan gempa dari BMKG Open API.

Sumber: BMKG Open API (data.bmkg.go.id)
Penyedia: Badan Meteorologi, Klimatologi, dan Geofisika (BMKG)
Dokumentasi: https://data.bmkg.go.id
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from enum import Enum

import httpx
import feedparser
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class AlertLevel(str, Enum):
    """Level peringatan bencana (sesuai terminologi BMKG)."""
    NORMAL = "Normal"
    WASPADA = "Waspada"    # Watch – potensi terjadi
    SIAGA = "Siaga"        # Advisory – kemungkinan tinggi
    AWAS = "Awas"          # Warning – sangat berbahaya, segera evakuasi


class WeatherAlert:
    """Representasi alert cuaca dari BMKG."""

    def __init__(self, district_id: str, district_name: str,
                 alert_level: AlertLevel, weather_code: str,
                 rainfall_mm: float, description: str,
                 timestamp: datetime):
        self.district_id = district_id
        self.district_name = district_name
        self.alert_level = alert_level
        self.weather_code = weather_code
        self.rainfall_mm = rainfall_mm
        self.description = description
        self.timestamp = timestamp
        self.triggered_disaster_type = self._infer_disaster_type()

    def _infer_disaster_type(self) -> str:
        """Simpulkan jenis bencana potensial dari data cuaca."""
        if self.rainfall_mm >= 200:
            return "banjir_bandang"
        elif self.rainfall_mm >= 100:
            return "banjir"
        elif self.rainfall_mm >= 50:
            return "potensi_banjir"
        return "cuaca_ekstrem"

    def to_dict(self) -> dict:
        return {
            "district_id": self.district_id,
            "district_name": self.district_name,
            "alert_level": self.alert_level.value,
            "weather_code": self.weather_code,
            "rainfall_mm": self.rainfall_mm,
            "description": self.description,
            "disaster_type": self.triggered_disaster_type,
            "timestamp": self.timestamp.isoformat(),
        }


# ── Threshold kecamatan termasuk di Jabodetabek ──────────────────────────────
MONITORED_DISTRICTS = {
    "bogor_tengah": {"name": "Bogor Tengah", "lat": -6.5954, "lon": 106.7977},
    "bogor_selatan": {"name": "Bogor Selatan", "lat": -6.6450, "lon": 106.7920},
    "bogor_utara": {"name": "Bogor Utara", "lat": -6.5623, "lon": 106.7891},
    "cibinong": {"name": "Cibinong", "lat": -6.4800, "lon": 106.8537},
    "gunung_putri": {"name": "Gunung Putri", "lat": -6.4560, "lon": 106.9301},
    "ciawi": {"name": "Ciawi", "lat": -6.6854, "lon": 106.8712},
    "cisarua": {"name": "Cisarua", "lat": -6.7060, "lon": 106.9464},
    "ciomas": {"name": "Ciomas", "lat": -6.6199, "lon": 106.7638},
    "dramaga": {"name": "Dramaga", "lat": -6.5545, "lon": 106.7243},
    "depok_tengah": {"name": "Depok", "lat": -6.4025, "lon": 106.7942},
}

# Threshold curah hujan (mm/hari) → level peringatan
RAINFALL_THRESHOLDS = {
    AlertLevel.WASPADA: 50.0,   # 50mm/hari
    AlertLevel.SIAGA: 100.0,    # 100mm/hari
    AlertLevel.AWAS: 200.0,     # 200mm/hari (ekstrem)
}


class BMKGClient:
    """
    Client untuk BMKG Open Data API.
    Mendukung polling cuaca, curah hujan, dan RSS gempa bumi.
    """

    BASE_URL = os.getenv("BMKG_BASE_URL", "https://data.bmkg.go.id/DataMKG/MEWS/DigitalForecast")
    EARTHQUAKE_URL = os.getenv("BMKG_EARTHQUAKE_URL", "https://data.bmkg.go.id/DataMKG/TEWS")
    BNPB_RSS_URL = "https://bnpb.go.id/feed"

    def __init__(self, simulation_mode: bool = None):
        self.simulation_mode = simulation_mode if simulation_mode is not None \
            else os.getenv("SIMULATION_MODE", "true").lower() == "true"
        self._client = httpx.AsyncClient(timeout=30.0)
        logger.info(f"BMKGClient initialized (simulation_mode={self.simulation_mode})")

    async def get_weather_forecast(self, province: str = "JawaBarat") -> dict:
        """Ambil prakiraan cuaca dari BMKG Digital Forecast API."""
        if self.simulation_mode:
            return self._mock_weather_data(province)

        url = f"{self.BASE_URL}/DigitalForecast-{province}.xml"
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; DisasterReady/1.0)",
            "Accept": "application/xml"
        }
        try:
            response = await self._client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()
            return {"raw_xml": response.text, "status": "ok", "province": province}
        except httpx.HTTPError as e:
            logger.error(f"BMKG API error: {e}")
            return {"error": str(e), "status": "error"}

    async def get_earthquake_data(self) -> list[dict]:
        """Ambil data gempa terkini dari BMKG TEWS."""
        if self.simulation_mode:
            return []  # Gempa bukan fokus demo banjir

        url = f"{self.EARTHQUAKE_URL}/gempadirasakan.json"
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            data = response.json()
            return data.get("Infogempa", {}).get("gempa", [])
        except Exception as e:
            logger.error(f"BMKG earthquake API error: {e}")
            return []

    async def get_bnpb_rss(self) -> list[dict]:
        """Parse RSS feed BNPB untuk berita bencana terkini."""
        if self.simulation_mode:
            return []

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(self.BNPB_RSS_URL)
            feed = feedparser.parse(response.text)
            return [
                {
                    "title": entry.title,
                    "link": entry.link,
                    "published": entry.get("published", ""),
                    "summary": entry.get("summary", ""),
                }
                for entry in feed.entries[:20]
            ]
        except Exception as e:
            logger.error(f"BNPB RSS error: {e}")
            return []

    def parse_weather_alerts(self, raw_data: dict) -> list[WeatherAlert]:
        """
        Parse data cuaca BMKG menjadi daftar WeatherAlert.
        Dalam simulation mode, gunakan data sintetis yang diinjeksi.
        """
        if self.simulation_mode:
            return self._parse_simulated_alerts(raw_data)
        
        if raw_data.get("status") != "ok":
            return []
            
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(raw_data["raw_xml"])
            return self._parse_real_xml(root)
        except Exception as e:
            logger.error(f"Gagal parse XML BMKG. Peringkat: XML mungkin dilindungi Cloudflare. Error: {e}")
            return []

    def _parse_real_xml(self, root) -> list[WeatherAlert]:
        alerts = []
        # Estimasi BMKG Weather Codes ke Curah Hujan (mm/hari)
        code_to_rainfall = {
            "60": 15.0,   # Hujan Ringan
            "61": 55.0,   # Hujan Sedang (WASPADA)
            "63": 110.0,  # Hujan Lebat (SIAGA)
            "95": 210.0,  # Hujan Petir (AWAS)
            "97": 210.0,  # Hujan Petir Ekstrem (AWAS)
        }
        
        bmkg_name_to_id = {v["name"].lower(): k for k, v in MONITORED_DISTRICTS.items()}
        
        for area in root.findall(".//area"):
            area_name = area.attrib.get("description", "").lower()
            
            district_id = next((did for name, did in bmkg_name_to_id.items() if name in area_name), None)
            if not district_id:
                continue
                
            weather_param = area.find(".//parameter[@id='weather']")
            if weather_param is None:
                continue
                
            timerange = weather_param.find(".//timerange")
            if timerange is None:
                continue
                
            value_elem = timerange.find(".//value")
            if value_elem is None:
                continue
                
            weather_code = value_elem.text
            rainfall = code_to_rainfall.get(weather_code, 0.0)
            
            level = AlertLevel.NORMAL
            if rainfall >= RAINFALL_THRESHOLDS[AlertLevel.AWAS]:
                level = AlertLevel.AWAS
            elif rainfall >= RAINFALL_THRESHOLDS[AlertLevel.SIAGA]:
                level = AlertLevel.SIAGA
            elif rainfall >= RAINFALL_THRESHOLDS[AlertLevel.WASPADA]:
                level = AlertLevel.WASPADA
                
            desc = "Cuaca Berawan/Cerah"
            if level != AlertLevel.NORMAL:
                desc = "Potensi Hujan Signifikan"
            if weather_code in ["95", "97"]:
                desc = "Peringatan Dini: Badai Petir"
            elif weather_code == "63":
                desc = "Peringatan Dini: Hujan Lebat"
            elif weather_code == "61":
                desc = "Hujan Sedang Terdeteksi"
                
            if rainfall > 0: # Hanya laporkan yang memiliki hujan (60, 61, 63, 95, 97)
                alerts.append(WeatherAlert(
                    district_id=district_id,
                    district_name=MONITORED_DISTRICTS[district_id]["name"],
                    alert_level=level,
                    weather_code=weather_code,
                    rainfall_mm=rainfall,
                    description=desc,
                    timestamp=datetime.now(timezone.utc),
                ))
                
        return alerts

    def _parse_simulated_alerts(self, data: dict) -> list[WeatherAlert]:
        """Parse data simulasi yang diinjeksi dari run_demo.py."""
        alerts = []
        for district_data in data.get("districts", []):
            district_id = district_data["district_id"]
            if district_id not in MONITORED_DISTRICTS:
                continue

            rainfall = district_data["rainfall_mm"]
            level = AlertLevel.NORMAL

            if rainfall >= RAINFALL_THRESHOLDS[AlertLevel.AWAS]:
                level = AlertLevel.AWAS
            elif rainfall >= RAINFALL_THRESHOLDS[AlertLevel.SIAGA]:
                level = AlertLevel.SIAGA
            elif rainfall >= RAINFALL_THRESHOLDS[AlertLevel.WASPADA]:
                level = AlertLevel.WASPADA

            if level != AlertLevel.NORMAL:
                alerts.append(WeatherAlert(
                    district_id=district_id,
                    district_name=MONITORED_DISTRICTS[district_id]["name"],
                    alert_level=level,
                    weather_code="HU",  # Hujan Lebat
                    rainfall_mm=rainfall,
                    description=district_data.get("description", f"Curah hujan {rainfall}mm/hari"),
                    timestamp=datetime.now(timezone.utc),
                ))

        return alerts

    def _mock_weather_data(self, province: str) -> dict:
        """Data cuaca mock untuk mode simulasi (polling normal, tidak ada bencana)."""
        return {
            "status": "ok",
            "province": province,
            "districts": [
                {"district_id": did, "rainfall_mm": 15.0, "description": "Hujan ringan"}
                for did in MONITORED_DISTRICTS
            ]
        }

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
