"""
Pantara — Orchestrator Agent
Koordinator utama seluruh sistem multi-agent.

Peran:
- Menerima trigger dari Monitor Agent
- Mendistribusikan task ke agen spesialis secara berurutan  
- Mengelola state bencana aktif
- Enforce human-in-the-loop untuk aksi kritis
- Mencatat seluruh alur eksekusi di audit log

Alur Koordinasi (setelah trigger dari Monitor Agent):
  MonitorAgent → OrchestratorAgent
                    ├─→ PredictionAgent (peta risiko)
                    ├─→ EarlyWarningAgent (notifikasi warga)
                    ├─→ AllocationAgent (dispatch relawan) [perlu konfirmasi]
                    └─→ CommunicationAgent (laporan BPBD)

Framework: Menggunakan pola AutoGen GroupChat untuk multi-agent coordination.
           Dalam implementasi ini, orkestrasi dilakukan via Python async workflow
           yang setara dengan AutoGen GroupChat pattern.

Referensi AutoGen:
  Library: pyautogen 0.4.x
  Penyedia: Microsoft Research
  GitHub: https://github.com/microsoft/autogen
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Callable

from core.bmkg_client import WeatherAlert
from core.firebase_client import FirebaseClient
from core.notification_dispatcher import NotificationDispatcher
from agents.prediction_agent import PredictionAgent
from agents.early_warning_agent import EarlyWarningAgent
from agents.allocation_agent import AllocationAgent
from agents.communication_agent import CommunicationAgent

logger = logging.getLogger(__name__)


class OrchestratorAgent:
    """
    Orchestrator: koordinator multi-agent Pantara.

    Menjalankan pipeline respons bencana secara berurutan dan paralel
    sesuai dependency antar agen:

    Step 1: PredictionAgent (butuh alert data dari MonitorAgent)
    Step 2: EarlyWarningAgent (paralel dengan Allocation)
    Step 3: AllocationAgent (paralel dengan EarlyWarning)
    Step 4: CommunicationAgent (butuh output semua agen sebelumnya)
    """

    AGENT_NAME = "OrchestratorAgent"

    def __init__(
        self,
        firebase: FirebaseClient,
        residents: list[dict],
        volunteers: list[dict],
        simulation_mode: bool = True,
    ):
        self.firebase = firebase
        self.residents = residents
        self.volunteers = volunteers
        self.simulation_mode = simulation_mode

        # Inisialisasi semua agen spesialis
        self.dispatcher = NotificationDispatcher(simulation_mode=simulation_mode)

        self.prediction_agent = PredictionAgent(firebase=firebase)
        self.early_warning_agent = EarlyWarningAgent(
            firebase=firebase,
            dispatcher=self.dispatcher,
            residents=residents,
        )
        self.allocation_agent = AllocationAgent(
            firebase=firebase,
            volunteers=volunteers,
        )
        self.communication_agent = CommunicationAgent(
            firebase=firebase,
            simulation_mode=simulation_mode,
        )

        self._active_disasters: dict = {}

        logger.info("🎯 OrchestratorAgent siap — semua agen spesialis terinisialisasi")
        logger.info(f"   👥 {len(residents)} warga terdaftar")
        logger.info(f"   🦺 {len(volunteers)} relawan terdaftar")

    async def handle_disaster_alert(
        self,
        disaster_id: str,
        alerts: list[WeatherAlert],
    ):
        """
        Entry point utama: tangani alert bencana dari Monitor Agent.
        Mengeksekusi pipeline respons multi-agent secara terkoordinasi.
        """
        pipeline_start = datetime.now(timezone.utc)
        alert = alerts[0]  # Ambil alert utama (level tertinggi)

        logger.info(f"\n{'═'*60}")
        logger.info(f"🚨 ORCHESTRATOR: Memulai pipeline respons bencana")
        logger.info(f"   ID: {disaster_id}")
        logger.info(f"   Level: {alert.alert_level.value}")
        logger.info(f"   Wilayah: {', '.join(a.district_name for a in alerts)}")
        logger.info(f"{'═'*60}\n")

        self.firebase.log_action(
            agent_name=self.AGENT_NAME,
            action="pipeline_started",
            data={
                "disaster_id": disaster_id,
                "alert_level": alert.alert_level.value,
                "districts": [a.district_id for a in alerts],
            },
            trigger_source="MonitorAgent",
            result="Pipeline multi-agent dimulai"
        )

        # ── STEP 1: Prediction Agent ──────────────────────────────────────────
        logger.info("📍 STEP 1/4 — PredictionAgent: Membangun peta risiko...")
        district_weather = [
            {"district_id": a.district_id, "rainfall_mm": a.rainfall_mm,
             "description": a.description}
            for a in alerts
        ]
        prediction_result = self.prediction_agent.predict_risk(
            district_weather_data=district_weather,
            disaster_id=disaster_id,
            residents=self.residents,
        )
        district_risks = prediction_result["district_risks"]
        logger.info(f"   ✅ Peta risiko: {len(district_risks)} kecamatan dipetakan\n")

        # Filter warga terdampak dari district_risks
        affected_district_ids = [d["district_id"] for d in district_risks if d["risk_level"] in ["high", "critical", "medium"]]
        from core.geo_utils import filter_residents_in_districts
        affected_residents = filter_residents_in_districts(self.residents, affected_district_ids)

        # ── STEP 2: AllocationAgent (Calculate Evacuation Routes) ─────────────
        logger.info("🗺️ STEP 2/4 — AllocationAgent: Menghitung jalur evakuasi warga...")
        evacuation_routes = await self.allocation_agent.calculate_evacuation_routes(affected_residents)

        # ── STEP 3: Early Warning + Allocation (Dispatch) (paralel) ───────────
        logger.info("📢 STEP 3/4 — EarlyWarningAgent + AllocationAgent (paralel)...")
        notification_task = asyncio.create_task(
            self.early_warning_agent.process_alert(
                disaster_id=disaster_id,
                district_risks=district_risks,
                alert_level=alert.alert_level.value,
                rainfall_mm=alert.rainfall_mm,
                disaster_type=alert.triggered_disaster_type,
                evacuation_routes=evacuation_routes,
                message_generator=self.communication_agent.personalize_notification
                    if self.communication_agent._client else None,
            )
        )
        allocation_task = asyncio.create_task(
            self.allocation_agent.dispatch_volunteers(
                disaster_id=disaster_id,
                district_risks=district_risks,
                notification_stats={},
                evacuation_routes=evacuation_routes,
            )
        )

        notification_stats, allocation_result = await asyncio.gather(
            notification_task, allocation_task
        )

        logger.info(
            f"   ✅ Notifikasi: {notification_stats.get('notified_sent', 0) + notification_stats.get('notified_simulated', 0)} "
            f"warga ternotifikasi\n"
            f"   ✅ Alokasi: {allocation_result.get('total_dispatched', 0)} relawan ditugaskan\n"
        )

        # ── STEP 4: Communication Agent ───────────────────────────────────────
        logger.info("📝 STEP 4/4 — CommunicationAgent: Generating laporan situasi...")
        report = await self.communication_agent.generate_situation_report(
            disaster_id=disaster_id,
            district_risks=district_risks,
            notification_stats=notification_stats,
            allocation_result=allocation_result,
            alert_level=alert.alert_level.value,
        )

        # ── Ringkasan Pipeline ────────────────────────────────────────────────
        elapsed = (datetime.now(timezone.utc) - pipeline_start).total_seconds()

        summary = {
            "disaster_id": disaster_id,
            "elapsed_seconds": round(elapsed, 2),
            "districts_mapped": len(district_risks),
            "residents_notified": notification_stats.get("notified_sent", 0) + notification_stats.get("notified_simulated", 0),
            "affected_residents": notification_stats.get("affected_residents", 0),
            "volunteers_dispatched": allocation_result.get("total_dispatched", 0),
            "priority_breakdown": notification_stats.get("priority_breakdown", {}),
        }

        self.firebase.log_action(
            agent_name=self.AGENT_NAME,
            action="pipeline_completed",
            data=summary,
            result=f"Pipeline selesai dalam {elapsed:.1f}s"
        )

        self.firebase.update_system_state({
            "last_disaster_id": disaster_id,
            "last_pipeline_elapsed_seconds": elapsed,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        })

        self._print_summary(summary, report)

        return {
            "summary": summary,
            "district_risks": district_risks,
            "notification_stats": notification_stats,
            "allocation_result": allocation_result,
            "report": report,
        }

    def _print_summary(self, summary: dict, report: str):
        """Print ringkasan eksekusi pipeline ke terminal."""
        logger.info(f"\n{'═'*60}")
        logger.info("✅ PIPELINE SELESAI — DisasterReady Multi-Agent System")
        logger.info(f"{'═'*60}")
        logger.info(f"  ⏱️  Total waktu  : {summary['elapsed_seconds']:.1f} detik")
        logger.info(f"  🗺️  Kecamatan   : {summary['districts_mapped']} dipetakan")
        logger.info(f"  📢  Notifikasi  : {summary['residents_notified']}/{summary['affected_residents']} warga")
        logger.info(f"  🦺  Relawan     : {summary['volunteers_dispatched']} ditugaskan")

        breakdown = summary.get("priority_breakdown", {})
        if breakdown:
            logger.info(f"\n  📊 Breakdown Prioritas Notifikasi:")
            for tier in ["KRITIS", "TINGGI", "SEDANG", "RENDAH"]:
                count = breakdown.get(tier, 0)
                if count > 0:
                    logger.info(f"     {tier}: {count} warga")

        logger.info(f"\n{'─'*60}")
        logger.info("📋 LAPORAN SITUASI:")
        logger.info(f"{'─'*60}")
        print(report)
        logger.info(f"{'═'*60}\n")


def create_orchestrator(
    firebase: FirebaseClient,
    residents: list[dict],
    volunteers: list[dict],
    simulation_mode: bool = True,
) -> OrchestratorAgent:
    """Factory function untuk membuat OrchestratorAgent."""
    return OrchestratorAgent(
        firebase=firebase,
        residents=residents,
        volunteers=volunteers,
        simulation_mode=simulation_mode,
    )
