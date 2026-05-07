"""
DisasterReady — Firebase Client
Manajemen state real-time: data bencana aktif, relawan, warga, dan audit log.

Sumber: Firebase Realtime Database
Penyedia: Google LLC
Dokumentasi: https://firebase.google.com/docs/database/admin/start
Penggunaan: State management real-time untuk semua agen, audit log transparansi
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Any

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class FirebaseClient:
    """
    Wrapper Firebase Realtime Database.
    Mendukung mode simulasi (in-memory) untuk demo tanpa koneksi Firebase.
    """

    def __init__(self, simulation_mode: bool = None):
        self.simulation_mode = simulation_mode if simulation_mode is not None \
            else os.getenv("SIMULATION_MODE", "true").lower() == "true"

        # In-memory store untuk mode simulasi
        self._store: dict = {
            "disasters": {},
            "alerts": {},
            "residents": {},
            "volunteers": {},
            "audit_log": {},
            "risk_maps": {},
            "assignments": {},
            "reports": {},
            "field_reports": {},
            "system_state": {"status": "active", "started_at": datetime.now(timezone.utc).isoformat()},
        }

        if not self.simulation_mode:
            self._init_firebase()
        else:
            logger.info("🔧 FirebaseClient: mode simulasi (in-memory)")

    def _init_firebase(self):
        """Inisialisasi koneksi Firebase nyata."""
        try:
            import firebase_admin
            from firebase_admin import credentials, db

            sa_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "./firebase-service-account.json")
            db_url = os.getenv("FIREBASE_DATABASE_URL")

            if not os.path.exists(sa_path):
                raise FileNotFoundError(f"Service account not found: {sa_path}")

            cred = credentials.Certificate(sa_path)
            firebase_admin.initialize_app(cred, {"databaseURL": db_url})
            self._db = db
            logger.info("✅ Firebase Realtime Database terhubung")
        except Exception as e:
            logger.error(f"Firebase init error: {e}. Fallback ke simulasi.")
            self.simulation_mode = True

    # ── Audit Log ─────────────────────────────────────────────────────────────

    def log_action(self, agent_name: str, action: str, data: dict,
                   trigger_source: str = "", result: str = "") -> str:
        """
        Catat setiap aksi agen ke audit log.
        Setiap entri mencakup: siapa, apa, data apa, kapan, hasil.
        Ini adalah inti transparansi dan akuntabilitas DisasterReady.
        """
        log_id = f"LOG-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        entry = {
            "id": log_id,
            "agent": agent_name,
            "action": action,
            "trigger_source": trigger_source,
            "data": data,
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if self.simulation_mode:
            self._store["audit_log"][log_id] = entry
        else:
            self._db.reference(f"audit_log/{log_id}").set(entry)

        logger.debug(f"[AUDIT] {agent_name} | {action} | {result}")
        return log_id

    # ── Disaster Management ────────────────────────────────────────────────────

    def create_disaster_event(self, disaster_data: dict) -> str:
        """Buat event bencana baru."""
        event_id = f"DIS-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        event = {
            "id": event_id,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            **disaster_data,
        }
        self._write(f"disasters/{event_id}", event)
        self.log_action(
            agent_name="MonitorAgent",
            action="disaster_event_created",
            data={"disaster_id": event_id, "type": disaster_data.get("disaster_type")},
            result="success"
        )
        return event_id

    def get_active_disasters(self) -> list[dict]:
        """Ambil semua bencana aktif."""
        return [
            d for d in self._read_all("disasters").values()
            if d.get("status") == "active"
        ]

    def update_disaster(self, event_id: str, updates: dict):
        """Update data bencana aktif."""
        self._update(f"disasters/{event_id}", updates)

    # ── Alert Management ──────────────────────────────────────────────────────

    def save_alert(self, alert_data: dict) -> str:
        """Simpan alert yang dikirim."""
        alert_id = f"ALT-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        alert = {"id": alert_id, "sent_at": datetime.now(timezone.utc).isoformat(), **alert_data}
        self._write(f"alerts/{alert_id}", alert)
        return alert_id

    def get_recent_alerts(self, limit: int = 50) -> list[dict]:
        """Ambil alert terbaru."""
        all_alerts = list(self._read_all("alerts").values())
        return sorted(all_alerts, key=lambda a: a.get("sent_at", ""), reverse=True)[:limit]

    # ── Risk Map ──────────────────────────────────────────────────────────────

    def save_risk_map(self, disaster_id: str, geojson: dict):
        """Simpan peta risiko GeoJSON hasil Prediction Agent."""
        self._write(f"risk_maps/{disaster_id}", {
            "disaster_id": disaster_id,
            "geojson": geojson,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    def get_risk_map(self, disaster_id: str) -> Optional[dict]:
        """Ambil peta risiko untuk bencana tertentu."""
        return self._read(f"risk_maps/{disaster_id}")

    def get_latest_risk_map(self) -> Optional[dict]:
        """Ambil peta risiko paling terbaru."""
        all_maps = list(self._read_all("risk_maps").values())
        if not all_maps:
            return None
        return sorted(all_maps, key=lambda m: m.get("generated_at", ""), reverse=True)[0]

    # ── Volunteer Assignment ──────────────────────────────────────────────────

    def save_assignments(self, disaster_id: str, assignments: list[dict]):
        """Simpan penugasan relawan dari Allocation Agent."""
        self._write(f"assignments/{disaster_id}", {
            "disaster_id": disaster_id,
            "assignments": assignments,
            "dispatched_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending_confirmation",   # Human-in-the-loop
        })

    def confirm_assignment(self, disaster_id: str, coordinator_id: str):
        """Koordinator konfirmasi penugasan (Human-in-the-Loop)."""
        existing = self._read(f"assignments/{disaster_id}") or {}

        # Update status di setiap item individual agar popup peta juga terupdate
        updated_items = []
        for item in existing.get("assignments", []):
            updated_items.append({**item, "status": "confirmed"})

        self._update(f"assignments/{disaster_id}", {
            "status": "confirmed",
            "confirmed_by": coordinator_id,
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
            "assignments": updated_items,
        })
        self.log_action(
            agent_name="HumanCoordinator",
            action="assignment_confirmed",
            data={"disaster_id": disaster_id, "coordinator": coordinator_id},
            result="assignment_dispatched"
        )

    def get_assignments(self, disaster_id: str) -> Optional[dict]:
        return self._read(f"assignments/{disaster_id}")

    # ── Reports ───────────────────────────────────────────────────────────────

    def save_report(self, disaster_id: str, report: dict) -> str:
        """Simpan laporan situasi dari Communication Agent."""
        report_id = f"RPT-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        self._write(f"reports/{report_id}", {
            "id": report_id,
            "disaster_id": disaster_id,
            **report,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })
        return report_id

    def get_reports(self, disaster_id: str) -> list[dict]:
        """Ambil semua laporan untuk satu bencana."""
        return [
            r for r in self._read_all("reports").values()
            if r.get("disaster_id") == disaster_id
        ]

    # ── Audit Log Retrieval ───────────────────────────────────────────────────

    def get_audit_log(self, limit: int = 100) -> list[dict]:
        """Ambil audit log terbaru."""
        all_logs = list(self._read_all("audit_log").values())
        return sorted(all_logs, key=lambda l: l.get("timestamp", ""), reverse=True)[:limit]

    # ── System State ──────────────────────────────────────────────────────────

    def get_system_state(self) -> dict:
        """Ambil state keseluruhan sistem."""
        return self._read("system_state") or {}

    def update_system_state(self, updates: dict):
        """Update state sistem."""
        self._update("system_state", updates)
    def reset_simulation_state(self):
        """Reset seluruh data simulasi di penyimpanan in-memory."""
        self._store["disasters"] = {}
        self._store["alerts"] = {}
        self._store["risk_maps"] = {}
        self._store["assignments"] = {}
        self._store["reports"] = {}
        self._store["audit_log"] = {}
        # field_reports TIDAK direset — laporan lapangan tetap ada lintas simulasi
        self._store["system_state"] = {
            "status": "active",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── Field Reports (Laporan Relawan Lapangan) ──────────────────────────────

    def save_field_report(self, report_data: dict) -> str:
        """Simpan laporan dari relawan di lapangan."""
        report_id = f"FRPT-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        entry = {
            "id": report_id,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            **report_data,
        }
        self._write(f"field_reports/{report_id}", entry)
        self.log_action(
            agent_name="FieldVolunteer",
            action="field_report_submitted",
            data={"report_id": report_id, "volunteer": report_data.get("volunteer_name"),
                  "district": report_data.get("district")},
            result="saved"
        )
        return report_id

    def get_field_reports(self, limit: int = 50) -> list[dict]:
        """Ambil laporan lapangan terbaru."""
        all_reports = list(self._read_all("field_reports").values())
        return sorted(all_reports, key=lambda r: r.get("submitted_at", ""), reverse=True)[:limit]
    # ── Internal Helpers ──────────────────────────────────────────────────────

    def _write(self, path: str, data: Any):
        if self.simulation_mode:
            keys = path.split("/")
            store = self._store
            for key in keys[:-1]:
                if key not in store:
                    store[key] = {}
                store = store[key]
            store[keys[-1]] = data
        else:
            self._db.reference(path).set(data)

    def _update(self, path: str, updates: dict):
        if self.simulation_mode:
            existing = self._read(path) or {}
            existing.update(updates)
            self._write(path, existing)
        else:
            self._db.reference(path).update(updates)

    def _read(self, path: str) -> Optional[Any]:
        if self.simulation_mode:
            keys = path.split("/")
            store = self._store
            for key in keys:
                if not isinstance(store, dict) or key not in store:
                    return None
                store = store[key]
            return store
        else:
            return self._db.reference(path).get()

    def _read_all(self, collection: str) -> dict:
        if self.simulation_mode:
            return self._store.get(collection, {})
        else:
            result = self._db.reference(collection).get()
            return result if isinstance(result, dict) else {}

    def get_all_data(self) -> dict:
        """Ambil semua data (untuk SSE dashboard)."""
        if self.simulation_mode:
            return {
                "disasters": list(self._store.get("disasters", {}).values()),
                "alerts": list(self._store.get("alerts", {}).values())[-20:],
                "risk_maps": list(self._store.get("risk_maps", {}).values()),
                "assignments": list(self._store.get("assignments", {}).values()),
                "audit_log": list(self._store.get("audit_log", {}).values())[-30:],
                "reports": list(self._store.get("reports", {}).values()),
                "field_reports": list(self._store.get("field_reports", {}).values())[-20:],
                "system_state": self._store.get("system_state", {}),
            }
        return {}
