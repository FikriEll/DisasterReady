"""
DisasterReady — Notification Dispatcher
Mengirim notifikasi early warning ke warga via Telegram Bot / SMS fallback.

Channels:
1. Telegram Bot (primary, tidak ada limit untuk demo)
2. WhatsApp Business API (opsional, produksi)
3. Twilio SMS (fallback untuk warga tanpa smartphone)

Prinsip inklusivitas:
- Pesan dalam Bahasa Indonesia sederhana
- Tidak ada jargon teknis
- Selalu ada langkah konkret yang dapat dilakukan warga
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
    Otomatis fallback ke channel berikutnya jika gagal.
    """

    def __init__(self, simulation_mode: bool = None):
        self.simulation_mode = simulation_mode if simulation_mode is not None \
            else os.getenv("SIMULATION_MODE", "true").lower() == "true"

        self._telegram_bot = None
        self._twilio_client = None

        if not self.simulation_mode:
            self._init_channels()

    def _init_channels(self):
        """Inisialisasi klien notifikasi untuk produksi."""
        # Telegram
        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if telegram_token:
            try:
                from telegram import Bot
                self._telegram_bot = Bot(token=telegram_token)
                logger.info("✅ Telegram Bot terhubung")
            except Exception as e:
                logger.warning(f"Telegram init gagal: {e}")

        # Twilio
        sid = os.getenv("TWILIO_ACCOUNT_SID")
        token = os.getenv("TWILIO_AUTH_TOKEN")
        if sid and token:
            try:
                from twilio.rest import Client
                self._twilio_client = Client(sid, token)
                logger.info("✅ Twilio SMS terhubung")
            except Exception as e:
                logger.warning(f"Twilio init gagal: {e}")

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
            # Dalam mode simulasi: log pesan tanpa kirim
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

        # Produksi: coba channel sesuai preferensi
        channels = self._get_channel_priority(resident)
        for channel in channels:
            result = await self._send_via_channel(channel, resident, message, message_preview)
            if result.status == NotificationStatus.SENT:
                return result

        # Semua channel gagal
        return NotificationResult(
            resident_id=resident_id,
            channel=NotificationChannel.SMS,
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
        """Urutan channel yang dicoba (priority fallback chain)."""
        channels = []
        if resident.get("telegram_id"):
            channels.append(NotificationChannel.TELEGRAM)
        if resident.get("has_whatsapp"):
            channels.append(NotificationChannel.WHATSAPP)
        if resident.get("phone"):
            channels.append(NotificationChannel.SMS)
        return channels or [NotificationChannel.SMS]

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
                return await self._send_sms(resident, message, message_preview)
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
        if not self._telegram_bot or not resident.get("telegram_id"):
            return NotificationResult(resident["id"], NotificationChannel.TELEGRAM,
                                      NotificationStatus.SKIPPED, preview)
        await self._telegram_bot.send_message(
            chat_id=resident["telegram_id"],
            text=message,
            parse_mode="HTML",
        )
        return NotificationResult(resident["id"], NotificationChannel.TELEGRAM,
                                  NotificationStatus.SENT, preview)

    async def _send_whatsapp(self, resident: dict, message: str, preview: str) -> NotificationResult:
        """WhatsApp Business API via Meta Cloud API."""
        import httpx
        access_token = os.getenv("WHATSAPP_ACCESS_TOKEN")
        phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        api_version = os.getenv("WHATSAPP_API_VERSION", "v18.0")

        if not access_token or not phone_id:
            return NotificationResult(resident["id"], NotificationChannel.WHATSAPP,
                                      NotificationStatus.SKIPPED, preview)

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

        return NotificationResult(resident["id"], NotificationChannel.WHATSAPP,
                                  NotificationStatus.SENT, preview)

    async def _send_sms(self, resident: dict, message: str, preview: str) -> NotificationResult:
        """Twilio SMS — fallback untuk warga tanpa smartphone."""
        if not self._twilio_client:
            return NotificationResult(resident["id"], NotificationChannel.SMS,
                                      NotificationStatus.SKIPPED, preview)

        from_number = os.getenv("TWILIO_FROM_NUMBER")
        to_number = resident.get("phone")
        if not to_number:
            return NotificationResult(resident["id"], NotificationChannel.SMS,
                                      NotificationStatus.SKIPPED, preview)

        self._twilio_client.messages.create(
            body=message[:160],  # SMS limit
            from_=from_number,
            to=to_number,
        )
        return NotificationResult(resident["id"], NotificationChannel.SMS,
                                  NotificationStatus.SENT, preview)

    async def broadcast_to_volunteers(
        self, volunteers: list[dict], message: str
    ) -> list[NotificationResult]:
        """Broadcast penugasan ke relawan yang di-dispatch."""
        tasks = [
            self.send_notification(v, message, "RELAWAN")
            for v in volunteers
        ]
        return await asyncio.gather(*tasks)
