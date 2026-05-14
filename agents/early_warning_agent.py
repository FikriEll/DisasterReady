"""
Pantara — Early Warning Agent
Mengirim notifikasi proaktif ke warga sebelum bencana tiba.

Fitur Unggulan Pantara:
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

    # Sapaan personal
    if age >= 60:
        greeting = f"Halo {name}"
        special_note = "Relawan sudah dihubungi untuk membantu Anda sebagai warga prioritas."
    elif age <= 4:
        greeting = f"Halo orang tua/wali dari {name}"
        special_note = "Prioritaskan keselamatan anak terlebih dahulu."
    elif disability != "none":
        greeting = f"Halo {name}"
        special_note = "Bantuan khusus untuk Anda sudah disiapkan oleh tim relawan."
    else:
        greeting = f"Halo {name}"
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
        f"-PESAN NOTIFIKASI DARURAT-\n\n"
        f"{greeting},\n"
        f"Kami dari Sistem Peringatan Dini Bencana Indonesia memberitahu Anda bahwa situasi cuaca di Kecamatan {district_name} sedang mengalami kondisi darurat.\n\n"
        f"Kecamatan: {district_name}\n"
        f"Status BMKG: {alert_level}\n"
        f"Curah hujan: {rainfall_mm:.0f}mm/hari - Potensi {disaster_text}\n\n"
        f"INSTRUKSI EVAKUASI:\n\n"
        f"{steps_text}\n\n"
        f"INFO LAIN:\n\n"
        f" Nomor darurat: 119 (BNPB) dan 112\n"
        f" Sumber data: BMKG\n"
        f" Perlu diingat: situasi cuaca dapat berubah-ubah, pastikan Anda selalu memantau informasi terbaru.\n\n"
        f"Tunggu instruksi dari petugas keamanan setempat!"
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
            # Generate SATU template per tier, bukan per-warga (hindari bottleneck)
            use_llm = message_generator and tier in ["KRITIS", "TINGGI"]
            tier_template_msg = None

            if use_llm:
                # Generate 1 pesan template untuk seluruh tier ini
                sample_resident = resident_map.get(batch[0].resident_id, {})
                sample_route = evacuation_routes.get(sample_resident.get("id")) if evacuation_routes else None
                try:
                    tier_template_msg = await message_generator(
                        sample_resident, batch[0], alert_level,
                        primary_district["district_name"],
                        rainfall_mm, disaster_type, sample_route
                    )
                    logger.info(f"   ✅ Template LLM untuk tier {tier} berhasil di-generate")
                except Exception as e:
                    logger.warning(f"   ⚠️ Groq gagal untuk tier {tier}: {e}. Fallback ke template statis.")
                    tier_template_msg = None

            # Kumpulkan semua task notifikasi untuk tier ini (paralel)
            notif_tasks = []
            for vs in batch:
                resident = resident_map.get(vs.resident_id)
                if not resident:
                    continue

                route_info = evacuation_routes.get(resident["id"]) if evacuation_routes else None

                # Pakai template tier jika LLM berhasil, atau fallback ke template statis per-warga
                if tier_template_msg:
                    msg = tier_template_msg
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
                # Dapatkan nama asli dari Telegram untuk demo yang lebih personal
                telegram_name = await notifier.get_chat_name(demo_chat_id)
                demo_resident = affected_residents[0] if affected_residents else {"name": telegram_name, "age": 30, "disability": "none"}
                # Timpa nama resident dengan nama telegram agar lebih personal
                demo_resident["name"] = telegram_name
                
                demo_vs = ranked_scores[0] if ranked_scores else None
                if not demo_vs:
                    from core.vulnerability_scorer import VulnerabilityScore
                    demo_vs = VulnerabilityScore("demo_id", telegram_name, 0, "KRITIS")
                else:
                    # Update nama di vulnerability score juga
                    demo_vs.resident_name = telegram_name
                
                demo_route = evacuation_routes.get(demo_resident.get("id")) if evacuation_routes else None
                if message_generator:
                    demo_msg = await message_generator(demo_resident, demo_vs, alert_level, primary_district["district_name"], rainfall_mm, disaster_type, demo_route)
                else:
                    demo_msg = build_notification_message(demo_resident, demo_vs, alert_level, primary_district["district_name"], rainfall_mm, disaster_type, demo_route)
                
                # Kirim langsung tanpa header demo
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
