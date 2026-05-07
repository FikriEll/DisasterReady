"""
DisasterReady — Communication Agent
Generate laporan situasi otomatis dan personalisasi pesan menggunakan Google Gemini API.

Model: Google Gemini 2.0 Flash
Penyedia: Google | https://ai.google.dev
Penggunaan:
  1. Generate laporan narasi situasi bencana untuk BPBD (setiap 30 menit)
  2. Personalisasi pesan notifikasi warga yang kontekstual
  3. Summarize audit log untuk dashboard koordinator

Keamanan data:
  - Tidak ada data pribadi warga yang dikirim ke Gemini
  - Hanya konteks situasi bencana (kecamatan, curah hujan, statistik)
  - Nama warga dalam contoh pesan: data sintetis saja
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


class CommunicationAgent:
    """
    Agent komunikasi: Generate laporan dan pesan menggunakan Google Gemini API.
    Fallback ke template statis jika API key tidak tersedia.
    """

    AGENT_NAME = "CommunicationAgent"

    def __init__(self, firebase=None, simulation_mode: bool = None):
        self.firebase = firebase
        self.simulation_mode = simulation_mode if simulation_mode is not None \
            else os.getenv("SIMULATION_MODE", "true").lower() == "true"

        self._client = None
        if GEMINI_API_KEY:
            try:
                import google.generativeai as genai
                genai.configure(api_key=GEMINI_API_KEY)
                self._client = genai.GenerativeModel(GEMINI_MODEL)
                logger.info(f"✅ CommunicationAgent: Google Gemini ({GEMINI_MODEL}) terhubung")
            except ImportError:
                logger.warning("google-generativeai library tidak terinstall. Menggunakan template fallback.")
        else:
            logger.warning("⚠️  GEMINI_API_KEY tidak ditemukan. Menggunakan template fallback.")

    async def generate_situation_report(
        self,
        disaster_id: str,
        district_risks: list[dict],
        notification_stats: dict,
        allocation_result: dict,
        alert_level: str,
    ) -> str:
        """
        Generate laporan situasi lengkap untuk BPBD/koordinator.
        Laporan dalam Bahasa Indonesia, format naratif yang jelas.
        """
        logger.info(f"📝 [CommunicationAgent] Generating laporan situasi...")

        # Buat konteks situasi (tanpa data pribadi warga)
        context = self._build_situation_context(
            disaster_id, district_risks, notification_stats,
            allocation_result, alert_level
        )

        if self._client:
            report = await self._generate_with_claude(context, "situation_report")
        else:
            report = self._generate_template_report(context)

        # Simpan ke Firebase
        if self.firebase:
            report_id = self.firebase.save_report(disaster_id, {
                "report_type": "situation_report",
                "content": report,
                "alert_level": alert_level,
                "generated_by": "gemini" if self._client else "template",
            })
            self.firebase.log_action(
                agent_name=self.AGENT_NAME,
                action="situation_report_generated",
                data={"disaster_id": disaster_id, "report_id": report_id},
                trigger_source="OrchestratorAgent",
                result=f"Laporan situasi {len(report)} karakter berhasil di-generate"
            )

        return report

    async def personalize_notification(
        self,
        resident: dict,
        vulnerability_score,
        alert_level: str,
        district_name: str,
        rainfall_mm: float,
        disaster_type: str,
    ) -> str:
        """
        Generate pesan notifikasi personal via Claude.
        CATATAN: Hanya nama depan dan kecamatan yang dikirim ke Claude — bukan data sensitif.
        """
        if not self._client:
            # Fallback ke template standar dari early_warning_agent
            from agents.early_warning_agent import build_notification_message
            return build_notification_message(
                resident, vulnerability_score, alert_level,
                district_name, rainfall_mm, disaster_type
            )

        age = resident.get("age", 30)
        disability = resident.get("disability", "none")
        tier = vulnerability_score.priority_tier

        # Konteks minimal yang dikirim ke Claude (tidak ada NIK/alamat/telepon)
        prompt = f"""Kamu adalah sistem peringatan dini bencana Indonesia.
Tulis pesan notifikasi darurat dalam Bahasa Indonesia sederhana untuk:
- Kecamatan: {district_name}
- Status BMKG: {alert_level}
- Curah hujan: {rainfall_mm:.0f}mm/hari — potensi {disaster_type.replace('_', ' ')}
- Profil penerima: {"lansia" if age >= 60 else "balita (kepada orang tua)" if age <= 4 else "penyandang disabilitas" if disability != "none" else "warga umum"}
- Prioritas: {tier}

Pesan harus:
- Maks 300 kata
- Bahasa sederhana, tidak menimbulkan kepanikan berlebihan
- Menyebutkan 3-4 langkah konkret yang bisa dilakukan
- Menyebutkan nomor darurat 119 (BNPB) dan 112
- Menyebutkan sumber data: BMKG
- Langsung ke poin, tidak bertele-tele

Tulis langsung pesannya (tidak perlu pengantar)."""

        try:
            response = self._client.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Gemini API error: {e}. Fallback ke template.")
            from agents.early_warning_agent import build_notification_message
            return build_notification_message(
                resident, vulnerability_score, alert_level,
                district_name, rainfall_mm, disaster_type
            )

    def _build_situation_context(
        self, disaster_id: str, district_risks: list[dict],
        notification_stats: dict, allocation_result: dict, alert_level: str
    ) -> dict:
        """Buat konteks situasi tanpa data pribadi warga."""
        high_risk = [d for d in district_risks if d["risk_level"] in ["critical", "high"]]
        critical = [d for d in district_risks if d["risk_level"] == "critical"]

        return {
            "disaster_id": disaster_id,
            "timestamp": datetime.now(timezone.utc).strftime("%d %B %Y, pukul %H:%M WIB"),
            "alert_level": alert_level,
            "districts_analyzed": len(district_risks),
            "critical_districts": [d["district_name"] for d in critical],
            "high_risk_districts": [d["district_name"] for d in high_risk],
            "max_rainfall_mm": max(d["rainfall_mm"] for d in district_risks) if district_risks else 0,
            "total_affected_residents": notification_stats.get("affected_residents", 0),
            "total_notified": notification_stats.get("notified_sent", 0) + notification_stats.get("notified_simulated", 0),
            "vulnerable_breakdown": notification_stats.get("priority_breakdown", {}),
            "volunteers_dispatched": allocation_result.get("total_dispatched", 0),
            "districts_covered": allocation_result.get("districts_covered", 0),
            "approval_required": True,
        }

    async def _generate_with_claude(self, context: dict, report_type: str) -> str:
        """Generate report menggunakan Google Gemini API."""
        import asyncio

        prompt = f"""Kamu adalah sistem AI DisasterReady — koordinator respons bencana Indonesia.
Buat laporan situasi bencana untuk BPBD berdasarkan data berikut:

=== DATA SITUASI ===
{json.dumps(context, indent=2, ensure_ascii=False)}

=== FORMAT LAPORAN ===
Buat laporan dalam Bahasa Indonesia dengan format:

**LAPORAN SITUASI BENCANA — {context['timestamp']}**
**Status: {context['alert_level'].upper()}**

**1. Ringkasan Situasi**
[Narasi singkat 2-3 kalimat tentang kondisi terkini]

**2. Wilayah Terdampak**
[List kecamatan dengan level risiko dan jumlah terdampak]

**3. Tindakan yang Sudah Dilakukan**
[Notifikasi warga, dispatch relawan, dll]

**4. Kelompok Rentan**
[Statistik warga prioritas KRITIS/TINGGI]

**5. Rekomendasi Tindak Lanjut**
[3-4 rekomendasi konkret untuk koordinator BPBD]

**6. Sumber Data & Transparansi**
"Laporan ini dibuat otomatis oleh DisasterReady berdasarkan data BMKG Open API. 
[Kecamatan X diprioritaskan karena curah hujan [X]mm/hari + historis banjir BNPB. 
Vulnerability score dihitung dari data demografis BPS 2023.]"

Buat laporan yang faktual, jelas, dan dapat langsung digunakan BPBD."""

        loop = __import__("asyncio").get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._client.generate_content(prompt)
        )
        return response.text

    def _generate_template_report(self, ctx: dict) -> str:
        """Template laporan fallback (tanpa Claude API)."""
        critical_str = ", ".join(ctx["critical_districts"]) or "—"
        high_risk_str = ", ".join(ctx["high_risk_districts"]) or "—"
        vuln = ctx.get("vulnerable_breakdown", {})

        return f"""
╔══════════════════════════════════════════════════════════════╗
║         LAPORAN SITUASI BENCANA — DisasterReady              ║
╚══════════════════════════════════════════════════════════════╝
⏰ Waktu       : {ctx['timestamp']}
🔴 Status      : {ctx['alert_level'].upper()}
🔑 ID Bencana  : {ctx['disaster_id']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. RINGKASAN SITUASI
   BMKG mengeluarkan status {ctx['alert_level']} dengan curah hujan mencapai 
   {ctx['max_rainfall_mm']:.0f}mm/hari. Sistem DisasterReady mendeteksi {ctx['districts_analyzed']} 
   kecamatan dalam zona pemantauan, dengan {len(ctx['critical_districts'])} kecamatan 
   berstatus KRITIS.

2. WILAYAH TERDAMPAK
   • Kritis    : {critical_str}
   • Tinggi    : {high_risk_str}
   • Kecamatan dipantau: {ctx['districts_analyzed']}

3. TINDAKAN YANG SUDAH DILAKUKAN
   ✅ Notifikasi early warning dikirim ke {ctx['total_notified']} dari 
      {ctx['total_affected_residents']} warga terdaftar
   ✅ {ctx['volunteers_dispatched']} relawan diassign ke {ctx['districts_covered']} kecamatan
   ⚠️  Penugasan fisik menunggu konfirmasi koordinator (Human-in-the-Loop)

4. KELOMPOK RENTAN (PRIORITAS NOTIFIKASI)
   🔴 KRITIS  : {vuln.get('KRITIS', 0)} warga (notifikasi pertama)
   🟠 TINGGI  : {vuln.get('TINGGI', 0)} warga
   🟡 SEDANG  : {vuln.get('SEDANG', 0)} warga
   🟢 RENDAH  : {vuln.get('RENDAH', 0)} warga

5. REKOMENDASI TINDAK LANJUT
   1. Konfirmasi penugasan relawan di sistem DisasterReady (diperlukan)
   2. Koordinasi dengan Palang Merah untuk warga lansia di zona KRITIS
   3. Aktifkan posko pengungsian di {critical_str or 'kecamatan terdampak'}
   4. Monitor update BMKG setiap 30 menit

6. SUMBER DATA & TRANSPARANSI
   Laporan ini dibuat otomatis oleh DisasterReady AI System.
   Sumber: BMKG Open API (data.bmkg.go.id) | Historis banjir: BNPB GIS (gis.bnpb.go.id)
   Vulnerability score: Data BPS 2023 (demografi per kecamatan)
   Semua aksi tercatat di audit log Firebase yang dapat diverifikasi.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DisasterReady — Sistem Koordinasi Respons Bencana Otonom
Dikembangkan sebagai sistem AI untuk Environmental & Social Impact
""".strip()
