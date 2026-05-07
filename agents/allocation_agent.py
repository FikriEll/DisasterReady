"""
DisasterReady — Allocation Agent
Optimasi penugasan dan routing relawan ke lokasi terdampak.

Tools:
- Haversine distance (matching relawan terdekat)
- OpenRouteService API (rute optimal) | https://openrouteservice.org
- Human-in-the-loop: distribusi FISIK memerlukan konfirmasi koordinator

Prinsip fairness dalam alokasi:
- Warga paling rentan (KRITIS) mendapat relawan pertama
- Kapasitas relawan diperhitungkan (tidak overload satu relawan)
- Distribusi merata ke seluruh zona terdampak
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from core.firebase_client import FirebaseClient
from core.geo_utils import find_nearest_volunteers, get_route

logger = logging.getLogger(__name__)


class AllocationAgent:
    """
    Agent alokasi: dispatch relawan ke zona terdampak menggunakan GIS routing.

    Aturan human-in-the-loop:
    - Penugasan relawan (informasi): otonom, notifikasi ke koordinator
    - Distribusi bantuan FISIK (evakuasi paksa, logistik besar): wajib konfirmasi
    """

    AGENT_NAME = "AllocationAgent"

    def __init__(self, firebase: FirebaseClient, volunteers: list[dict]):
        self.firebase = firebase
        self.volunteers = volunteers
        self._dispatched_volunteer_ids: set = set()

    def reset(self):
        """Reset state relawan yang sudah di-dispatch. Dipanggil saat simulasi direset."""
        self._dispatched_volunteer_ids.clear()
        logger.info("[AllocationAgent] State relawan direset — siap untuk simulasi baru.")

    async def dispatch_volunteers(
        self,
        disaster_id: str,
        district_risks: list[dict],
        notification_stats: dict,
    ) -> dict:
        """
        Assign relawan ke zona terdampak berdasarkan proximity dan kebutuhan.

        Args:
            disaster_id: ID event bencana
            district_risks: List risiko per kecamatan dari Prediction Agent
            notification_stats: Statistik dari Early Warning Agent (jumlah rentan per kecamatan)

        Returns:
            dict berisi assignments dan total relawan yang didispatch
        """
        logger.info(f"🚁 [AllocationAgent] Memulai dispatch relawan untuk bencana {disaster_id}...")

        # Prioritaskan kecamatan berdasarkan risk level + vulnerable residents
        prioritized_districts = sorted(
            [d for d in district_risks if d["risk_level"] in ["critical", "high", "medium"]],
            key=lambda d: (
                {"critical": 3, "high": 2, "medium": 1}.get(d["risk_level"], 0),
                d.get("vulnerable_residents", 0)
            ),
            reverse=True
        )

        if not prioritized_districts:
            logger.warning("[AllocationAgent] Tidak ada distrik prioritas untuk di-dispatch.")
            return {"assignments": [], "total_dispatched": 0}

        assignments = []
        available_volunteers = [v for v in self.volunteers if v.get("is_available", True)]

        for district in prioritized_districts:
            target_lat = district["lat"]
            target_lon = district["lon"]
            district_name = district["district_name"]
            vulnerable_count = district.get("vulnerable_residents", 0)

            # Tentukan jumlah relawan yang dibutuhkan
            needed = self._calculate_volunteers_needed(district)

            # Temukan relawan terdekat yang belum ditugaskan
            eligible = [v for v in available_volunteers if v["id"] not in self._dispatched_volunteer_ids]
            nearest = find_nearest_volunteers(eligible, target_lat, target_lon, n=needed * 2)

            selected = nearest[:needed]

            if not selected:
                logger.warning(f"   ⚠️  Tidak cukup relawan untuk {district_name}")
                continue

            # Dapatkan rute untuk setiap relawan
            district_assignments = []
            route_tasks = [
                get_route(v["lat"], v["lon"], target_lat, target_lon)
                for v in selected
            ]
            routes = await asyncio.gather(*route_tasks)

            for vol, route in zip(selected, routes):
                assignment = {
                    "volunteer_id": vol["id"],
                    "volunteer_name": vol["name"],
                    "organization": vol["organization"],
                    "specialties": vol["specialties"],
                    "vehicle": vol.get("vehicle", "motor"),
                    "from_lat": vol["lat"],
                    "from_lon": vol["lon"],
                    "to_district": district_name,
                    "to_lat": target_lat,
                    "to_lon": target_lon,
                    "distance_km": route.get("distance_km", 0) if route else 0,
                    "eta_minutes": route.get("duration_minutes", 0) if route else 0,
                    "route_source": route.get("source", "unknown") if route else "unknown",
                    "vulnerable_to_assist": vulnerable_count,
                    "status": "pending_confirmation",  # Human-in-the-loop
                    "assigned_at": datetime.now(timezone.utc).isoformat(),
                }
                district_assignments.append(assignment)
                self._dispatched_volunteer_ids.add(vol["id"])

                logger.info(
                    f"   ✅ {vol['name']} ({vol['organization']}) → "
                    f"{district_name} | "
                    f"ETA: {route.get('duration_minutes', '?'):.0f} menit | "
                    f"{route.get('distance_km', '?'):.1f} km"
                )

            assignments.extend(district_assignments)

            logger.info(
                f"   📍 {district_name} [{district['risk_level'].upper()}]: "
                f"{len(district_assignments)} relawan ditugaskan "
                f"({vulnerable_count} warga rentan)"
            )

        # Simpan ke Firebase (masih pending confirmation)
        self.firebase.save_assignments(disaster_id, assignments)

        total_dispatched = len(assignments)

        self.firebase.log_action(
            agent_name=self.AGENT_NAME,
            action="volunteers_dispatched",
            data={
                "disaster_id": disaster_id,
                "total_volunteers": total_dispatched,
                "districts_covered": len(prioritized_districts),
                "status": "pending_confirmation",
                "human_approval_required": True,
            },
            trigger_source="OrchestratorAgent",
            result=(
                f"{total_dispatched} relawan ditugaskan ke {len(prioritized_districts)} kecamatan. "
                f"⚠️ STATUS: Menunggu konfirmasi koordinator (Human-in-the-Loop)"
            )
        )

        logger.info(
            f"\n🏁 [AllocationAgent] {total_dispatched} relawan ditugaskan. "
            f"⚠️  Menunggu konfirmasi koordinator untuk distribusi fisik."
        )

        return {
            "assignments": assignments,
            "total_dispatched": total_dispatched,
            "districts_covered": len(prioritized_districts),
            "status": "pending_confirmation",
        }

    def _calculate_volunteers_needed(self, district: dict) -> int:
        """
        Hitung jumlah relawan yang dibutuhkan per kecamatan.
        Berdasarkan: jumlah vulnerable residents + risk level.
        """
        vulnerable = district.get("vulnerable_residents", 0)
        risk_level = district["risk_level"]

        # Base: 1 relawan per 5 warga rentan
        base = max(2, math.ceil(vulnerable / 5)) if vulnerable > 0 else 3

        # Multiplier risk level
        multiplier = {"critical": 1.5, "high": 1.2, "medium": 1.0}.get(risk_level, 1.0)

        return min(int(base * multiplier), 20)  # Max 20 relawan per kecamatan


import math  # noqa (placed here to avoid circular before class definition)
