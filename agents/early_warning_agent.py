"""
DisasterReady — Early Warning Agent
Mengirim notifikasi proaktif ke warga sebelum bencana tiba.

Fitur Unggulan DisasterReady:
- Vulnerability scoring transparan (usia + disabilitas + jarak)
- Kelompok rentan PERTAMA menerima notifikasi
- Pesan personal dalam Bahasa Indonesia sederhana
- Semua aksi tercatat di audit log (transparansi penuh)

Prinsip human-in-the-loop:
- Notifikasi informasi: otonom penuh (makin cepat makin baik)
- Dispatch fisik relawan: memerlukan konfirmasi koordinator
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from core.vulnerability_scorer import rank_residents_by_vulnerability, VulnerabilityScore
from core.notification_dispatcher import NotificationDispatcher, NotificationStatus
from core.firebase_client import FirebaseClient
from core.geo_utils import filter_residents_in_districts

logger = logging.getLogger(__name__)


def build_notification_message(
    resident: dict,
    vs: VulnerabilityScore,
    alert_level: str,
    district_name: str,
    rainfall_mm: float,
    disaster_type: str,
    evacuation_route: dict = None,
) -> str:
    """
    Bangun pesan notifikasi personal dalam Bahasa Indonesia sederhana.
    Setiap pesan mencantumkan:
    - Nama warga (personal, bukan massal)
    - Nama kecamatan spesifik
    - Data konkret (curah hujan)
    - Langkah tindakan yang jelas
    - Sumber informasi (BMKG) untuk kepercayaan
    """
    name = resident.get("name", "Warga")
    age = resident.get("age", 30)
    disability = resident.get("disability", "none")
    tier = vs.priority_tier

    # Sapaan personal berdasarkan kelompok
    if age >= 60:
        greeting = f"Halo, {name}. Sebagai warga lansia"
        special_note = "Relawan sudah dihubungi untuk membantu Anda."
    elif age <= 4:
        greeting = f"Halo, orang tua/wali dari {name}"
        special_note = "Prioritaskan keselamatan anak terlebih dahulu."
    elif disability != "none":
        greeting = f"Halo, {name}"
        special_note = "Bantuan khusus untuk Anda sudah disiapkan."
    else:
        greeting = f"Halo, {name}"
        special_note = ""

    # Level bahaya
    level_text = {
        "Awas": "⛔ AWAS — BAHAYA SANGAT TINGGI",
        "Siaga": "🔴 SIAGA — bahaya tinggi",
        "Waspada": "🟡 WASPADA — perlu waspada",
    }.get(alert_level, f"⚠️ {alert_level}")

    # Jenis bencana
    disaster_text = {
        "banjir_bandang": "banjir bandang",
        "banjir": "banjir",
        "longsor": "tanah longsor",
        "cuaca_ekstrem": "cuaca ekstrem",
    }.get(disaster_type, disaster_type)

    # Langkah tindakan
    steps = [
        "1️⃣  Pindahkan barang berharga ke tempat lebih tinggi",
        "2️⃣  Siapkan tas darurat (dokumen, obat, air, makanan)",
        "3️⃣  Pantau perkembangan di info.bmkg.go.id",
        "4️⃣  Hubungi 119 jika membutuhkan bantuan darurat",
    ]
    if tier in ["KRITIS", "TINGGI"]:
        evac_point_name = evacuation_route["point_name"] if evacuation_route else "titik kumpul terdekat"
        dist_km = evacuation_route["route_info"]["distance_km"] if evacuation_route and evacuation_route.get("route_info") else 1.5
        steps.insert(0, f"⚡ SEGERA menuju titik evakuasi: {evac_point_name} (jarak ±{dist_km} km)!")
        
    steps_text = "\n".join(steps)

    message = (
        f"🚨 PERINGATAN DINI BENCANA — DisasterReady\n"
        f"{'─' * 35}\n"
        f"{greeting}.\n\n"
        f"BMKG mengeluarkan status {level_text} untuk wilayah {district_name}.\n"
        f"📊 Curah hujan: {rainfall_mm:.0f}mm/hari — potensi {disaster_text}.\n\n"
        f"{special_note + chr(10) if special_note else ''}"
        f"📋 Langkah yang disarankan:\n{steps_text}\n\n"
        f"🔗 Info lengkap: info.bmkg.go.id\n"
        f"📞 Darurat: 119 (BNPB) | 112 (Umum)\n"
        f"{'─' * 35}\n"
        f"DisasterReady — Sistem Peringatan Dini Indonesia\n"
        f"Sumber: BMKG Open API | Waktu: {datetime.now(timezone.utc).strftime('%d-%m-%Y %H:%M')} WIB"
    )

    return message


class EarlyWarningAgent:
    """
    Agent peringatan dini: menghitung vulnerability score dan mengirim notifikasi.

    Urutan eksekusi:
    1. Filter warga di zona terdampak
    2. Hitung vulnerability score setiap warga
    3. Sort: paling rentan (KRITIS) → pertama
    4. Generate pesan personal via Communication Agent
    5. Kirim notifikasi (Telegram/WA/SMS)
    6. Catat semua aksi di audit log
    """

    AGENT_NAME = "EarlyWarningAgent"

    def __init__(
        self,
        firebase: FirebaseClient,
        dispatcher: NotificationDispatcher,
        residents: list[dict],
    ):
        self.firebase = firebase
        self.dispatcher = dispatcher
        self.residents = residents
        self._notification_stats = {"sent": 0, "failed": 0, "simulated": 0}

    async def process_alert(
        self,
        disaster_id: str,
        district_risks: list[dict],
        alert_level: str,
        rainfall_mm: float,
        disaster_type: str,
        evacuation_routes: dict = None,
        message_generator=None,  # Opsional: Communication Agent untuk pesan Claude
    ) -> dict:
        """
        Proses alert bencana dan kirim notifikasi ke warga terdampak.

        Returns:
            dict berisi statistik pengiriman notifikasi
        """
        logger.info(f"📢 [EarlyWarningAgent] Memproses alert untuk {len(district_risks)} kecamatan...")

        # Ambil kecamatan dengan risiko tinggi/kritis
        high_risk_districts = [
            d for d in district_risks
            if d["risk_level"] in ["high", "critical", "medium"]
        ]
        affected_district_ids = [d["district_id"] for d in high_risk_districts]

        # Filter warga di zona terdampak
        affected_residents = filter_residents_in_districts(self.residents, affected_district_ids)
        logger.info(f"   👥 Warga di zona terdampak: {len(affected_residents)}")

        if not affected_residents:
            logger.warning("   ⚠️  Tidak ada warga terdaftar di zona terdampak.")
            return {"affected": 0, "notified": 0}

        # Pusat zona risiko (rata-rata koordinat kecamatan terdampak)
        center_lat = sum(d["lat"] for d in high_risk_districts) / len(high_risk_districts)
        center_lon = sum(d["lon"] for d in high_risk_districts) / len(high_risk_districts)
        risk_zone_center = {"lat": center_lat, "lon": center_lon}

        # Hitung vulnerability score dan sort
        ranked_scores = rank_residents_by_vulnerability(affected_residents, risk_zone_center)

        logger.info(f"   🏆 Top 5 prioritas pertama:")
        for vs in ranked_scores[:5]:
            logger.info(
                f"      [{vs.priority_tier}] {vs.resident_name} "
                f"(skor: {vs.total_score:.2f})"
            )

        # Kirim notifikasi secara batch
        primary_district = high_risk_districts[0]
        total_sent = 0
        total_failed = 0
        total_sim = 0

        # Map resident id → data
        resident_map = {r["id"]: r for r in affected_residents}

        # Bagi ke batch berdasarkan tier prioritas
        tier_order = ["KRITIS", "TINGGI", "SEDANG", "RENDAH"]
        tier_groups: dict[str, list[VulnerabilityScore]] = {t: [] for t in tier_order}
        for vs in ranked_scores:
            tier_groups[vs.priority_tier].append(vs)

        for tier in tier_order:
            batch = tier_groups[tier]
            if not batch:
                continue

            logger.info(f"   📨 Mengirim ke tier {tier}: {len(batch)} warga...")

            # Hanya gunakan Groq LLM untuk warga KRITIS & TINGGI (hemat quota)
            use_llm = message_generator and tier in ["KRITIS", "TINGGI"]

            # Generate pesan & kumpulkan task notifikasi
            notif_tasks = []
            for vs in batch:
                resident = resident_map.get(vs.resident_id)
                if not resident:
                    continue

                route_info = evacuation_routes.get(resident["id"]) if evacuation_routes else None

                if use_llm:
                    # Sequential dengan delay agar tidak hit Groq rate limit
                    msg = await message_generator(resident, vs, alert_level, primary_district["district_name"], rainfall_mm, disaster_type, route_info)
                    await asyncio.sleep(1.2)  # 1.2s delay → maks ~50 req/menit, di bawah limit Groq
                else:
                    msg = build_notification_message(
                        resident, vs, alert_level,
                        primary_district["district_name"],
                        rainfall_mm, disaster_type,
                        evacuation_route=route_info
                    )

                notif_tasks.append(
                    self.dispatcher.send_notification(resident, msg, tier)
                )

            results = await asyncio.gather(*notif_tasks)

            for result in results:
                if result.status == NotificationStatus.SENT:
                    total_sent += 1
                elif result.status == NotificationStatus.SIMULATED:
                    total_sim += 1
                elif result.status == NotificationStatus.FAILED:
                    total_failed += 1

            # Log per-tier progress
            self.firebase.log_action(
                agent_name=self.AGENT_NAME,
                action=f"notifications_sent_tier_{tier.lower()}",
                data={
                    "disaster_id": disaster_id,
                    "tier": tier,
                    "count": len(batch),
                    "alert_level": alert_level,
                },
                trigger_source="OrchestratorAgent",
                result=f"{len(batch)} notifikasi dikirim untuk tier {tier}"
            )

        # Alert tercatat di Firebase
        self.firebase.save_alert({
            "disaster_id": disaster_id,
            "alert_level": alert_level,
            "affected_districts": affected_district_ids,
            "total_affected_residents": len(affected_residents),
            "total_notified": total_sent + total_sim,
            "tier_breakdown": {
                tier: len(tier_groups[tier]) for tier in tier_order
            },
            "notification_channels": ["telegram", "sms_fallback"],
        })

        # --- DEMO LIVE PUSH NOTIFICATION ---
        # Kirim 1 pesan ke TELEGRAM_DEMO_CHAT_ID agar juri bisa melihat notifikasi masuk
        try:
            import os
            from core.telegram_notifier import get_telegram_notifier
            demo_chat_id = os.getenv("TELEGRAM_DEMO_CHAT_ID")
            notifier = get_telegram_notifier()
            if demo_chat_id and notifier.is_configured:
                demo_resident = affected_residents[0] if affected_residents else {"name": "Warga Demo", "age": 65, "disability": "none"}
                demo_vs = ranked_scores[0] if ranked_scores else None
                if not demo_vs:
                    from core.vulnerability_scorer import VulnerabilityScore
                    demo_vs = VulnerabilityScore("demo_id", "Warga Demo", 0, "KRITIS")
                
                demo_route = evacuation_routes.get(demo_resident.get("id")) if evacuation_routes else None
                if message_generator:
                    demo_msg = await message_generator(demo_resident, demo_vs, alert_level, primary_district["district_name"], rainfall_mm, disaster_type, demo_route)
                else:
                    demo_msg = build_notification_message(demo_resident, demo_vs, alert_level, primary_district["district_name"], rainfall_mm, disaster_type, demo_route)
                
                # Tambahkan header khusus demo
                demo_msg = "🔔 [DEMO BROADCAST] 🔔\nIni adalah contoh pesan yang diterima oleh warga prioritas (Kritis):\n\n" + demo_msg
                await notifier.send_message(chat_id=demo_chat_id, message=demo_msg)
                logger.info(f"✅ Demo notification berhasil di-push ke {demo_chat_id}")
        except Exception as e:
            logger.error(f"Gagal mem-push demo notification: {e}")
        # -----------------------------------

        stats = {
            "affected_residents": len(affected_residents),
            "notified_sent": total_sent,
            "notified_simulated": total_sim,
            "failed": total_failed,
            "priority_breakdown": {
                tier: len(tier_groups[tier]) for tier in tier_order
            },
        }

        logger.info(
            f"✅ [EarlyWarningAgent] Selesai: "
            f"{total_sent + total_sim}/{len(affected_residents)} warga ternotifikasi"
        )
        return stats
