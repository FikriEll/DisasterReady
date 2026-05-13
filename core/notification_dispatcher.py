"""
DisasterReady — Notification Dispatcher
Multi-channel notification: Telegram (primary) → WhatsApp (fallback) → SMS log.

Channel priority:
  1. Telegram Bot API (gratis, unlimited, primary)
  2. WhatsApp Business Meta Cloud API (fallback, opsional)
  3. SMS log fallback (untuk monitoring jika semua channel gagal)

Prinsip inklusivitas:
  - Pesan dalam Bahasa Indonesia sederhana
  - Kelompok rentan (KRITIS) diproses pertama
  - Semua aksi tercatat di audit log
"""

import os
import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class NotificationChannel(str, Enum):
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    SMS = "sms"
    SIMULATION = "simulation"  # Log ke terminal, tidak kirim ke mana-mana


class NotificationStatus(str, Enum):
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"
    SIMULATED = "simulated"


@dataclass
class NotificationResult:
    resident_id: str
    channel: NotificationChannel
    status: NotificationStatus
    message_preview: str
    error: Optional[str] = None


class NotificationDispatcher:
    """
    Multi-channel notification dispatcher.
    Telegram adalah channel utama. Otomatis fallback ke channel berikutnya jika gagal.
    """

    def __init__(self, simulation_mode: bool = None):
        self.simulation_mode = simulation_mode if simulation_mode is not None \
            else os.getenv("SIMULATION_MODE", "true").lower() == "true"

        self._telegram_notifier = None

        # Selalu init Telegram (bahkan di mode simulasi, bisa kirim notif nyata)
        self._init_telegram()

    def _init_telegram(self):
        """Inisialisasi Telegram notifier."""
        try:
            from core.telegram_notifier import get_telegram_notifier
            notifier = get_telegram_notifier()
            if notifier.is_configured:
                self._telegram_notifier = notifier
                logger.info("✅ NotificationDispatcher: Telegram aktif")
            else:
                logger.warning("⚠️  Telegram tidak terkonfigurasi (TELEGRAM_BOT_TOKEN kosong)")
        except Exception as e:
            logger.warning(f"Telegram init gagal: {e}")

    async def send_notification(
        self,
        resident: dict,
        message: str,
        priority_tier: str,
    ) -> NotificationResult:
        """
        Kirim notifikasi ke satu warga.
        Otomatis pilih channel terbaik yang tersedia.
        """
        resident_id = resident["id"]
        message_preview = message[:80] + "..." if len(message) > 80 else message

        if self.simulation_mode:
            # Mode simulasi: log saja, tidak kirim
            channel_used = self._choose_channel(resident)
            logger.info(
                f"[SIM] 📱 {channel_used.value.upper()} → {resident['name']} "
                f"[{priority_tier}] | {message_preview}"
            )
            return NotificationResult(
                resident_id=resident_id,
                channel=NotificationChannel.SIMULATION,
                status=NotificationStatus.SIMULATED,
                message_preview=message_preview,
            )

        # Produksi: coba channel sesuai preferensi warga
        channels = self._get_channel_priority(resident)
        for channel in channels:
            result = await self._send_via_channel(channel, resident, message, message_preview)
            if result.status == NotificationStatus.SENT:
                return result

        # Semua channel gagal
        return NotificationResult(
            resident_id=resident_id,
            channel=NotificationChannel.TELEGRAM,
            status=NotificationStatus.FAILED,
            message_preview=message_preview,
            error="Semua channel gagal",
        )

    def _choose_channel(self, resident: dict) -> NotificationChannel:
        """Pilih channel terbaik untuk warga ini."""
        if resident.get("telegram_id"):
            return NotificationChannel.TELEGRAM
        elif resident.get("has_whatsapp"):
            return NotificationChannel.WHATSAPP
        return NotificationChannel.SMS

    def _get_channel_priority(self, resident: dict) -> list[NotificationChannel]:
        """Urutan channel yang dicoba (Telegram → WhatsApp → SMS)."""
        channels = []
        if resident.get("telegram_id"):
            channels.append(NotificationChannel.TELEGRAM)
        if resident.get("has_whatsapp"):
            channels.append(NotificationChannel.WHATSAPP)
        if resident.get("phone"):
            channels.append(NotificationChannel.SMS)
        return channels or [NotificationChannel.TELEGRAM]

    async def _send_via_channel(
        self, channel: NotificationChannel, resident: dict,
        message: str, message_preview: str
    ) -> NotificationResult:
        """Kirim via channel spesifik."""
        try:
            if channel == NotificationChannel.TELEGRAM:
                return await self._send_telegram(resident, message, message_preview)
            elif channel == NotificationChannel.WHATSAPP:
                return await self._send_whatsapp(resident, message, message_preview)
            elif channel == NotificationChannel.SMS:
                return await self._send_sms_fallback(resident, message, message_preview)
        except Exception as e:
            logger.error(f"Error sending via {channel}: {e}")
            return NotificationResult(
                resident_id=resident["id"],
                channel=channel,
                status=NotificationStatus.FAILED,
                message_preview=message_preview,
                error=str(e),
            )

    async def _send_telegram(self, resident: dict, message: str, preview: str) -> NotificationResult:
        """Kirim notifikasi via Telegram Bot API (primary channel)."""
        chat_id = resident.get("telegram_id")
        if not self._telegram_notifier or not chat_id:
            return NotificationResult(
                resident["id"], NotificationChannel.TELEGRAM,
                NotificationStatus.SKIPPED, preview,
            )

        result = await self._telegram_notifier.send_message(chat_id=chat_id, message=message)
        if result.success:
            logger.info(f"✅ Telegram terkirim ke {resident.get('name')} (chat_id: {chat_id})")
            return NotificationResult(
                resident["id"], NotificationChannel.TELEGRAM,
                NotificationStatus.SENT, preview,
            )
        else:
            logger.error(f"Telegram send error: {result.error}")
            return NotificationResult(
                resident["id"], NotificationChannel.TELEGRAM,
                NotificationStatus.FAILED, preview, error=result.error,
            )

    async def _send_whatsapp(self, resident: dict, message: str, preview: str) -> NotificationResult:
        """WhatsApp Business API via Meta Cloud API (fallback)."""
        import httpx
        access_token = os.getenv("WHATSAPP_ACCESS_TOKEN")
        phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        api_version = os.getenv("WHATSAPP_API_VERSION", "v18.0")

        if not access_token or not phone_id:
            return NotificationResult(
                resident["id"], NotificationChannel.WHATSAPP,
                NotificationStatus.SKIPPED, preview,
            )

        url = f"https://graph.facebook.com/{api_version}/{phone_id}/messages"
        phone = resident.get("phone", "").replace("+", "").replace("-", "")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                json={
                    "messaging_product": "whatsapp",
                    "to": phone,
                    "type": "text",
                    "text": {"body": message},
                }
            )
            response.raise_for_status()

        return NotificationResult(
            resident["id"], NotificationChannel.WHATSAPP,
            NotificationStatus.SENT, preview,
        )

    async def _send_sms_fallback(self, resident: dict, message: str, preview: str) -> NotificationResult:
        """
        SMS fallback — log ke audit trail jika semua channel digital gagal.
        Untuk implementasi SMS nyata, integrasikan dengan provider lokal (ZenzVA/Watzap).
        """
        phone = resident.get("phone")
        if not phone:
            return NotificationResult(
                resident["id"], NotificationChannel.SMS,
                NotificationStatus.SKIPPED, preview,
            )

        logger.warning(
            f"📵 SMS fallback: {resident.get('name')} ({phone}) — "
            f"semua channel digital gagal. Koordinator perlu follow-up manual."
        )
        return NotificationResult(
            resident["id"], NotificationChannel.SMS,
            NotificationStatus.FAILED, preview,
            error="SMS provider tidak dikonfigurasi. Koordinator perlu follow-up manual.",
        )

    async def send_demo_telegram(self, chat_id: str, message: str) -> dict:
        """
        Kirim pesan Telegram langsung ke chat_id tertentu (untuk tombol demo dashboard).
        Tidak memerlukan data resident.
        """
        if not self._telegram_notifier:
            return {
                "status": "error",
                "detail": "Telegram Bot belum dikonfigurasi. Set TELEGRAM_BOT_TOKEN di .env",
            }
        result = await self._telegram_notifier.send_message(chat_id=chat_id, message=message)
        if result.success:
            return {"status": "sent", "chat_id": chat_id, "message_id": result.message_id}
        return {"status": "error", "detail": result.error}

    async def broadcast_to_volunteers(
        self, volunteers: list[dict], message: str
    ) -> list[NotificationResult]:
        """Broadcast penugasan ke relawan yang di-dispatch."""
        tasks = [
            self.send_notification(v, message, "RELAWAN")
            for v in volunteers
        ]
        return await asyncio.gather(*tasks)
