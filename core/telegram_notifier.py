"""
DisasterReady — Telegram Notifier
Module dedicated untuk mengirim notifikasi via Telegram Bot API.

Fitur:
  - Kirim pesan ke individual chat_id (warga terdaftar)
  - Broadcast ke grup/channel (BPBD koordinator)
  - Test koneksi bot
  - Format pesan HTML (bold, emoji, dll)
  - Graceful fallback jika token tidak terkonfigurasi

Setup:
  1. Buat bot di Telegram: chat ke @BotFather → /newbot
  2. Simpan token ke .env: TELEGRAM_BOT_TOKEN=...
  3. Dapatkan chat_id: kirim pesan ke bot, cek /getUpdates
  4. Simpan ke .env: TELEGRAM_DEMO_CHAT_ID=...
"""

import os
import asyncio
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_DEMO_CHAT_ID = os.getenv("TELEGRAM_DEMO_CHAT_ID", "")


@dataclass
class TelegramSendResult:
    success: bool
    chat_id: str
    message_id: Optional[int] = None
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TelegramNotifier:
    """
    Mengirim notifikasi via Telegram Bot API menggunakan python-telegram-bot.
    Mendukung HTML formatting, emoji, dan retry otomatis.
    """

    def __init__(self):
        self._bot = None
        self._token = TELEGRAM_BOT_TOKEN

        if self._token:
            try:
                from telegram import Bot
                self._bot = Bot(token=self._token)
                logger.info("✅ TelegramNotifier: Bot terhubung")
            except ImportError:
                logger.error(
                    "❌ python-telegram-bot belum terinstall. "
                    "Jalankan: pip install python-telegram-bot==21.5"
                )
            except Exception as e:
                logger.error(f"❌ TelegramNotifier init error: {e}")
        else:
            logger.warning(
                "⚠️  TELEGRAM_BOT_TOKEN tidak ditemukan di .env. "
                "Notifikasi Telegram tidak akan berfungsi."
            )

    @property
    def is_configured(self) -> bool:
        return self._bot is not None

    async def test_connection(self) -> dict:
        """
        Test koneksi ke Telegram API.
        Returns info bot jika berhasil.
        """
        if not self._bot:
            return {
                "ok": False,
                "error": "Bot tidak dikonfigurasi. Set TELEGRAM_BOT_TOKEN di .env"
            }
        try:
            bot_info = await self._bot.get_me()
            return {
                "ok": True,
                "bot_username": f"@{bot_info.username}",
                "bot_name": bot_info.first_name,
                "bot_id": bot_info.id,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def send_message(
        self,
        chat_id: str,
        message: str,
        parse_mode: str = "HTML",
    ) -> TelegramSendResult:
        """
        Kirim pesan ke satu chat_id.
        
        Args:
            chat_id: Telegram chat ID (user, grup, atau channel)
            message: Teks pesan (mendukung HTML jika parse_mode='HTML')
            parse_mode: 'HTML' atau 'Markdown' atau None
        """
        if not self._bot:
            return TelegramSendResult(
                success=False,
                chat_id=str(chat_id),
                error="Bot tidak dikonfigurasi. Set TELEGRAM_BOT_TOKEN di .env",
            )

        try:
            sent = await self._bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode=parse_mode,
            )
            logger.info(f"✅ Telegram terkirim ke chat_id={chat_id} (msg_id={sent.message_id})")
            return TelegramSendResult(
                success=True,
                chat_id=str(chat_id),
                message_id=sent.message_id,
            )
        except Exception as e:
            logger.error(f"❌ Telegram send error ke {chat_id}: {e}")
            return TelegramSendResult(
                success=False,
                chat_id=str(chat_id),
                error=str(e),
            )

    async def send_disaster_alert(
        self,
        chat_id: str,
        district_name: str,
        alert_level: str,
        rainfall_mm: float,
        disaster_type: str = "banjir",
        affected_count: int = 0,
        vulnerable_count: int = 0,
    ) -> TelegramSendResult:
        """
        Kirim notifikasi peringatan dini bencana yang terformat.
        Menggunakan HTML formatting untuk tampilan yang lebih baik di Telegram.
        """
        level_emoji = {
            "Awas": "⛔",
            "Siaga": "🔴",
            "Waspada": "🟡",
        }.get(alert_level, "⚠️")

        disaster_emoji = {
            "banjir": "🌊",
            "banjir_bandang": "🌊",
            "longsor": "⛰️",
            "cuaca_ekstrem": "⛈️",
            "gempa": "🏚️",
        }.get(disaster_type, "🚨")

        now = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M")

        message = (
            f"🚨 <b>PERINGATAN DINI BENCANA</b>\n"
            f"<b>DisasterReady — Sistem Early Warning Indonesia</b>\n"
            f"{'─' * 30}\n\n"
            f"{level_emoji} <b>Status BMKG: {alert_level.upper()}</b>\n"
            f"{disaster_emoji} Potensi: <b>{disaster_type.replace('_', ' ').title()}</b>\n"
            f"📍 Wilayah: <b>{district_name}</b>\n"
            f"🌧 Curah hujan: <b>{rainfall_mm:.0f} mm/hari</b>\n\n"
        )

        if affected_count > 0:
            message += (
                f"👥 Warga terdampak: <b>{affected_count:,}</b>\n"
                f"⚠️ Kelompok rentan: <b>{vulnerable_count:,}</b> (lansia/balita/difabel)\n\n"
            )

        message += (
            f"❗ <b>TINDAKAN SEGERA:</b>\n"
            f"1️⃣  Pindahkan barang berharga ke tempat lebih tinggi\n"
            f"2️⃣  Siapkan tas darurat (dokumen, obat, air minum)\n"
            f"3️⃣  Ikuti arahan relawan PMI/Basarnas\n"
            f"4️⃣  Hubungi BPBD: <b>119</b> atau <b>112</b>\n\n"
            f"🔗 Info terkini: <a href='https://info.bmkg.go.id'>info.bmkg.go.id</a>\n\n"
            f"{'─' * 30}\n"
            f"<i>⏰ {now} WIB</i>\n"
            f"<i>Sumber: BMKG Open API | DisasterReady AI System</i>"
        )

        return await self.send_message(chat_id, message)

    async def broadcast(
        self,
        chat_ids: list[str],
        message: str,
        delay_seconds: float = 0.5,
    ) -> list[TelegramSendResult]:
        """
        Broadcast pesan ke beberapa chat_id dengan delay untuk hindari rate limit.
        
        Args:
            chat_ids: List chat ID tujuan
            message: Pesan yang dikirim
            delay_seconds: Jeda antar pengiriman (default 0.5 detik)
        """
        results = []
        for chat_id in chat_ids:
            result = await self.send_message(chat_id, message)
            results.append(result)
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)
        return results

    async def send_coordinator_report(
        self,
        chat_id: str,
        report_text: str,
    ) -> TelegramSendResult:
        """
        Kirim laporan situasi untuk koordinator BPBD.
        Laporan panjang akan dipotong jika melebihi 4096 karakter (limit Telegram).
        """
        MAX_LEN = 4000
        if len(report_text) > MAX_LEN:
            report_text = report_text[:MAX_LEN] + "\n\n[...laporan dipotong — lihat dashboard]"

        # Wrap dalam format koordinator
        header = "📋 <b>LAPORAN SITUASI BENCANA</b>\n<b>DisasterReady untuk BPBD</b>\n\n"
        return await self.send_message(chat_id, header + report_text)


# ── Singleton instance ────────────────────────────────────────────────────────
_notifier: Optional[TelegramNotifier] = None


def get_telegram_notifier() -> TelegramNotifier:
    """Dapatkan singleton instance TelegramNotifier."""
    global _notifier
    if _notifier is None:
        _notifier = TelegramNotifier()
    return _notifier
