"""
Pantara — Monitor Agent
Memantau data BMKG secara berkala dan mendeteksi anomali cuaca.

Peran: Polling data BMKG/BNPB setiap 5 menit, parsing status Waspada/Siaga/Awas,
       dan memicu Orchestrator Agent jika terdeteksi anomali.

Prinsip: Monitoring adalah otonom penuh (tidak perlu human approval).
         Latensi rendah kritis — setiap menit memiliki nilai.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Callable

from core.bmkg_client import BMKGClient, WeatherAlert, AlertLevel
from core.firebase_client import FirebaseClient

logger = logging.getLogger(__name__)

# Threshold peringatan (curah hujan mm/hari)
ALERT_THRESHOLDS = {
    AlertLevel.WASPADA: 50.0,
    AlertLevel.SIAGA: 100.0,
    AlertLevel.AWAS: 200.0,
}

POLLING_INTERVAL_SECONDS = 5 * 60  # 5 menit (dalam simulasi dikompres)


class MonitorAgent:
    """
    Agent pemantau: polling BMKG API dan mendeteksi anomali cuaca.

    Dalam skenario demo, polling loop dikompres (1 detik = 1 menit real-time)
    untuk memungkinkan demonstrasi live kepada juri.
    """

    AGENT_NAME = "MonitorAgent"

    def __init__(
        self,
        bmkg_client: BMKGClient,
        firebase: FirebaseClient,
        on_alert: Optional[Callable] = None,  # Callback → OrchestratorAgent
        simulation_speed: int = 1,            # Multiplikasi kecepatan simulasi
    ):
        self.bmkg = bmkg_client
        self.firebase = firebase
        self.on_alert = on_alert
        self.simulation_speed = simulation_speed
        self._is_running = False
        self._poll_count = 0
        self._injected_scenario: Optional[dict] = None  # Data simulasi demo

    def inject_scenario(self, scenario_data: dict):
        """
        Injeksi skenario bencana untuk demo (simulasi BMKG alert).
        Ini memungkinkan demo reproducible tanpa menunggu event BMKG nyata.
        """
        self._injected_scenario = scenario_data
        logger.warning(
            f"⚠️  [MonitorAgent] Skenario demo diinjeksi: "
            f"{scenario_data.get('scenario_name', 'Unknown')}"
        )

    async def start_polling(
        self,
        poll_interval_seconds: int = POLLING_INTERVAL_SECONDS,
        max_polls: Optional[int] = None,
    ):
        """
        Mulai polling loop. Berjalan terus sampai stop() dipanggil.
        Dalam mode simulasi, gunakan interval yang lebih pendek.
        """
        self._is_running = True
        actual_interval = poll_interval_seconds // self.simulation_speed

        logger.info(
            f"🔍 [MonitorAgent] Mulai polling BMKG "
            f"(interval: {actual_interval}s, speed: {self.simulation_speed}x)"
        )

        while self._is_running:
            if max_polls and self._poll_count >= max_polls:
                logger.info("[MonitorAgent] Batas polling tercapai, berhenti.")
                break

            await self._poll_cycle()
            self._poll_count += 1

            if self._is_running:
                await asyncio.sleep(actual_interval)

    async def _poll_cycle(self):
        """Satu siklus polling: ambil data → parse → detect → trigger."""
        start_time = datetime.now(timezone.utc)
        logger.info(f"🔄 [MonitorAgent] Poll #{self._poll_count + 1} — {start_time.strftime('%H:%M:%S')}")

        # Gunakan skenario yang diinjeksi (demo) atau polling BMKG nyata
        if self._injected_scenario:
            raw_data = self._injected_scenario
            self._injected_scenario = None  # Hanya triggered sekali
        else:
            raw_data = await self.bmkg.get_weather_forecast()

        alerts = self.bmkg.parse_weather_alerts(raw_data)

        if not alerts:
            logger.info(f"   ✅ Tidak ada anomali terdeteksi — semua wilayah normal")
            self.firebase.log_action(
                agent_name=self.AGENT_NAME,
                action="polling_completed",
                data={"poll_count": self._poll_count + 1, "alerts_found": 0},
                result="no_anomaly"
            )
            return

        # Anomali terdeteksi!
        detection_time = (datetime.now(timezone.utc) - start_time).total_seconds()

        logger.warning(f"🚨 [MonitorAgent] ANOMALI TERDETEKSI: {len(alerts)} wilayah!")
        for alert in alerts:
            logger.warning(
                f"   📍 {alert.district_name} — "
                f"Level: {alert.alert_level.value} | "
                f"Curah hujan: {alert.rainfall_mm}mm/hari | "
                f"Tipe: {alert.triggered_disaster_type}"
            )

        # Simpan ke Firebase
        disaster_id = self.firebase.create_disaster_event({
            "disaster_type": alerts[0].triggered_disaster_type,
            "alert_level": alerts[0].alert_level.value,
            "affected_districts": [a.district_id for a in alerts],
            "district_names": [a.district_name for a in alerts],
            "max_rainfall_mm": max(a.rainfall_mm for a in alerts),
            "detection_time_seconds": round(detection_time, 2),
        })

        self.firebase.log_action(
            agent_name=self.AGENT_NAME,
            action="anomaly_detected",
            data={
                "disaster_id": disaster_id,
                "districts": [a.district_id for a in alerts],
                "max_rainfall_mm": max(a.rainfall_mm for a in alerts),
                "detection_time_seconds": round(detection_time, 2),
            },
            trigger_source="BMKG_API",
            result=f"Trigger dikirim ke OrchestratorAgent untuk {len(alerts)} wilayah"
        )

        # Trigger Orchestrator
        if self.on_alert:
            return await self.on_alert(
                disaster_id=disaster_id,
                alerts=alerts,
            )
        return None

    def stop(self):
        """Hentikan polling loop."""
        self._is_running = False
        logger.info("[MonitorAgent] Polling dihentikan.")
