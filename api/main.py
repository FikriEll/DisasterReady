"""
Pantara — FastAPI Backend
REST API untuk orkestrasi sistem, SSE dashboard, dan endpoint simulasi.

Penyedia: FastAPI (Sebastián Ramírez) | https://fastapi.tiangolo.com
Versi: 0.115.0
"""

import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.firebase_client import FirebaseClient
from core.bmkg_client import BMKGClient
from agents.orchestrator import create_orchestrator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import os
from dotenv import load_dotenv
load_dotenv()

# ── Global State ──────────────────────────────────────────────────────────────
_sim_mode = os.getenv("SIMULATION_MODE", "true").lower() == "true"
firebase = FirebaseClient(simulation_mode=_sim_mode)
bmkg_client = BMKGClient(simulation_mode=_sim_mode)
residents = []
volunteers = []
orchestrator = None

SIMULATION_SCENARIO = {
    "scenario_name": "Banjir Jabodetabek — Status BMKG Siaga",
    "districts": [
        {"district_id": "bogor_tengah",  "rainfall_mm": 290.0, "description": "Status Siaga BMKG"},
        {"district_id": "bogor_selatan", "rainfall_mm": 265.0, "description": "Hujan deras"},
        {"district_id": "ciawi",         "rainfall_mm": 310.0, "description": "Potensi banjir bandang"},
        {"district_id": "cisarua",       "rainfall_mm": 285.0, "description": "Waspada longsor"},
        {"district_id": "cibinong",      "rainfall_mm": 180.0, "description": "Status Waspada"},
    ]
}


def load_data():
    global residents, volunteers
    data_dir = Path(__file__).parent.parent / "data" / "synthetic"
    res_path = data_dir / "residents.json"
    vol_path = data_dir / "volunteers.json"

    if res_path.exists() and vol_path.exists():
        with open(res_path) as f:
            residents = json.load(f)
        with open(vol_path) as f:
            volunteers = json.load(f)
        logger.info(f"✅ Data loaded: {len(residents)} residents, {len(volunteers)} volunteers")
    else:
        logger.warning("⚠️  Synthetic data tidak ditemukan. Jalankan: python data/generate_synthetic.py")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup & shutdown lifecycle."""
    global orchestrator
    load_data()
    orchestrator = create_orchestrator(
        firebase=firebase,
        residents=residents,
        volunteers=volunteers,
        simulation_mode=_sim_mode,
    )
    logger.info(f"🚀 Pantara API Server siap! [SIMULATION_MODE={_sim_mode}]")
    yield
    logger.info("🛑 Server shutting down...")


app = FastAPI(
    title="Pantara API",
    description="Sistem Koordinasi Respons Bencana Otonom — Multi-Agent AI",
    version="1.0.0",
    lifespan=lifespan,
)
app.state.current_simulation_task = None
app.state.simulation_cancel_requested = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount static dashboard ────────────────────────────────────────────────────
dashboard_path = Path(__file__).parent.parent / "dashboard"
if dashboard_path.exists():
    app.mount("/dashboard", StaticFiles(directory=str(dashboard_path), html=True), name="dashboard")


# ── Root Redirect ─────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root():
    return """
    <meta http-equiv="refresh" content="0; url=/dashboard">
    <a href="/dashboard">→ Dashboard DisasterReady</a>
    """


# ── System Status ─────────────────────────────────────────────────────────────
@app.get("/api/status")
async def get_status():
    """Status sistem secara keseluruhan."""
    active_disasters = firebase.get_active_disasters()
    recent_alerts = firebase.get_recent_alerts(limit=5)
    return {
        "status": "operational",
        "version": "1.0.0",
        "simulation_mode": True,
        "residents_registered": len(residents),
        "volunteers_registered": len(volunteers),
        "active_disasters": len(active_disasters),
        "recent_alerts_count": len(recent_alerts),
        "system_state": firebase.get_system_state(),
    }


# ── Simulation Endpoints ──────────────────────────────────────────────────────
@app.post("/api/simulate")
async def trigger_simulation():
    """
    Trigger skenario demo banjir Bogor.
    Pipeline berjalan di background task.
    """
    from core.bmkg_client import WeatherAlert, AlertLevel
    from datetime import datetime, timezone

    alerts = []
    for d in SIMULATION_SCENARIO["districts"]:
        mm = d["rainfall_mm"]
        level = AlertLevel.AWAS if mm >= 200 else AlertLevel.SIAGA if mm >= 100 else AlertLevel.WASPADA
        alerts.append(WeatherAlert(
            district_id=d["district_id"],
            district_name=d["district_id"].replace("_", " ").title(),
            alert_level=level,
            weather_code="HU",
            rainfall_mm=mm,
            description=d["description"],
            timestamp=datetime.now(timezone.utc),
        ))

    disaster_id = firebase.create_disaster_event({
        "disaster_type": "banjir",
        "alert_level": "Siaga",
        "affected_districts": [a.district_id for a in alerts],
        "max_rainfall_mm": max(a.rainfall_mm for a in alerts),
        "detection_time_seconds": 2.3,
    })

    firebase.update_system_state({"simulation_running": True, "current_disaster_id": disaster_id})

    async def run_pipeline():
        try:
            result = await orchestrator.handle_disaster_alert(disaster_id=disaster_id, alerts=alerts)
            return result
        except asyncio.CancelledError:
            logger.info(f"🚫 Simulasi {disaster_id} dibatalkan secara manual.")
            raise
        finally:
            firebase.update_system_state({"simulation_running": False})
            app.state.current_simulation_task = None
            app.state.simulation_cancel_requested = False

    if app.state.current_simulation_task and not app.state.current_simulation_task.done():
        raise HTTPException(status_code=409, detail="Simulasi sedang berjalan. Hentikan dulu sebelum memulai ulang.")

    task = asyncio.create_task(run_pipeline())
    app.state.current_simulation_task = task

    return {
        "status": "started",
        "disaster_id": disaster_id,
        "message": "Pipeline multi-agent dimulai. Pantau via SSE: GET /api/stream",
        "scenario": SIMULATION_SCENARIO["scenario_name"],
    }

@app.post("/api/trigger-real-poll")
async def trigger_real_poll(background_tasks: BackgroundTasks):
    """Trigger polling ke API live BMKG tanpa data dummy."""
    from agents.monitor_agent import MonitorAgent
    
    real_bmkg = BMKGClient(simulation_mode=False)
    
    firebase.update_system_state({"simulation_running": True, "current_disaster_id": "POLLING_LIVE_BMKG"})
    
    async def run_live_poll():
        monitor = MonitorAgent(
            bmkg_client=real_bmkg,
            firebase=firebase,
            on_alert=orchestrator.handle_disaster_alert,
        )
        try:
            await monitor._poll_cycle()
        except Exception as e:
            logger.error(f"Live poll error: {e}")
        finally:
            firebase.update_system_state({"simulation_running": False})
            await real_bmkg.close()
            
    background_tasks.add_task(run_live_poll)
    
    return {
        "status": "started",
        "message": "Live BMKG polling dimulai. Perhatikan dashboard/terminal untuk hasilnya.",
        "scenario": "Live Data BMKG (Performa Real-time)",
    }


@app.post("/api/reset-simulation")
async def reset_simulation():
    """Hentikan simulasi aktif dan reset state demo ke kondisi awal."""
    if app.state.current_simulation_task and not app.state.current_simulation_task.done():
        app.state.current_simulation_task.cancel()
        try:
            await app.state.current_simulation_task
        except asyncio.CancelledError:
            logger.info("✅ Simulasi aktif berhasil dibatalkan.")

    firebase.reset_simulation_state()
    firebase.update_system_state({
        "status": "active",
        "simulation_running": False,
        "current_disaster_id": None,
        "last_disaster_id": None,
    })

    # Reset state internal agen agar simulasi berikutnya deterministik
    orchestrator.allocation_agent.reset()

    app.state.current_simulation_task = None
    app.state.simulation_cancel_requested = False

    return {
        "status": "reset",
        "message": "Simulasi dihentikan dan state dashboard direset ke awal.",
    }


@app.get("/api/stream")
async def stream_events():
    """
    Server-Sent Events (SSE) untuk real-time dashboard updates.
    Frontend berlangganan ke endpoint ini untuk mendapat update tanpa polling.
    """
    async def event_generator():
        import time
        while True:
            data = firebase.get_all_data()
            yield f"data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
            await asyncio.sleep(1.5)  # Update setiap 1.5 detik

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Dashboard Data Endpoints ──────────────────────────────────────────────────
@app.get("/api/disasters/active")
async def get_active_disasters():
    return firebase.get_active_disasters()


@app.get("/api/alerts/recent")
async def get_recent_alerts(limit: int = 20):
    return firebase.get_recent_alerts(limit=limit)


@app.get("/api/risk-map/latest")
async def get_latest_risk_map():
    rm = firebase.get_latest_risk_map()
    if not rm:
        raise HTTPException(status_code=404, detail="Belum ada peta risiko. Jalankan simulasi terlebih dahulu.")
    return rm


@app.get("/api/audit-log")
async def get_audit_log(limit: int = 50):
    return firebase.get_audit_log(limit=limit)


@app.get("/api/reports")
async def get_reports():
    all_data = firebase.get_all_data()
    return all_data.get("reports", [])


# ── Human-in-the-Loop Endpoint ────────────────────────────────────────────────
@app.post("/api/coordinator/confirm-assignment/{disaster_id}")
async def confirm_assignment(disaster_id: str, coordinator_id: str = "KOORDINATOR_DEMO"):
    """
    Endpoint untuk koordinator mengkonfirmasi penugasan relawan.
    Ini adalah implementasi Human-in-the-Loop untuk distribusi fisik.
    """
    assignment = firebase.get_assignments(disaster_id)
    if not assignment:
        raise HTTPException(status_code=404, detail=f"Tidak ada penugasan untuk disaster_id: {disaster_id}")

    firebase.confirm_assignment(disaster_id, coordinator_id)
    return {
        "status": "confirmed",
        "disaster_id": disaster_id,
        "confirmed_by": coordinator_id,
        "message": "✅ Penugasan relawan dikonfirmasi. Relawan akan segera bergerak.",
    }


@app.get("/api/assignments/{disaster_id}")
async def get_assignments(disaster_id: str):
    """Ambil data penugasan relawan untuk satu bencana."""
    result = firebase.get_assignments(disaster_id)
    if not result:
        raise HTTPException(status_code=404, detail="Penugasan tidak ditemukan.")
    return result


# ── Field Report Endpoints (Laporan Relawan Lapangan) ─────────────────
@app.post("/api/field-report", status_code=201)
async def submit_field_report(report: dict = Body(...)):
    """
    Relawan di lapangan submit laporan situasi bencana.
    Data: volunteer_name, organization, district, casualties, road_condition,
          needs, situation_description, urgency_level.
    """
    required = ["volunteer_name", "district", "situation_description"]
    for field in required:
        if not report.get(field):
            raise HTTPException(status_code=422, detail=f"Field '{field}' wajib diisi.")

    report_id = firebase.save_field_report(report)
    return {
        "status": "saved",
        "report_id": report_id,
        "message": "✅ Laporan berhasil dikirim dan tercatat di sistem koordinasi.",
    }


@app.get("/api/field-reports")
async def get_field_reports(limit: int = 50):
    """Ambil laporan lapangan dari semua relawan."""
    return firebase.get_field_reports(limit=limit)


# ── Demo Notifikasi Telegram ───────────────────────────────────────
@app.post("/api/demo/send-real-notification")
async def send_demo_notification():
    """
    Kirim notifikasi Telegram nyata ke nomor demo (TELEGRAM_DEMO_CHAT_ID di .env).
    Digunakan untuk demonstrasi live bahwa sistem benar-benar mengirim notifikasi.
    """
    import os
    from core.telegram_notifier import get_telegram_notifier

    demo_chat_id = os.getenv("TELEGRAM_DEMO_CHAT_ID")
    if not demo_chat_id:
        raise HTTPException(
            status_code=400,
            detail="TELEGRAM_DEMO_CHAT_ID belum diset di .env. "
                   "Isi dengan chat_id Telegram penerima demo."
        )

    notifier = get_telegram_notifier()
    if not notifier.is_configured:
        raise HTTPException(
            status_code=400,
            detail="TELEGRAM_BOT_TOKEN belum dikonfigurasi. Lihat panduan di .env.example."
        )

    result = await notifier.send_disaster_alert(
        chat_id=demo_chat_id,
        district_name="Bogor Tengah, Ciawi, Cisarua",
        alert_level="Siaga",
        rainfall_mm=290.0,
        disaster_type="banjir",
        affected_count=1240,
        vulnerable_count=312,
    )

    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)

    firebase.log_action(
        agent_name="DemoSystem",
        action="demo_telegram_sent",
        data={"chat_id": demo_chat_id},
        result="success"
    )
    return {
        "status": "sent",
        "message": f"✅ Notifikasi demo berhasil dikirim ke Telegram (chat_id: {demo_chat_id})",
        "message_id": result.message_id,
    }


# ── Telegram Endpoints ────────────────────────────────────────────────────────
@app.get("/api/telegram/status")
async def get_telegram_status():
    """
    Cek status koneksi Telegram Bot.
    Gunakan endpoint ini untuk verifikasi token sebelum demo.
    """
    import os
    from core.telegram_notifier import get_telegram_notifier

    notifier = get_telegram_notifier()
    if not notifier.is_configured:
        return {
            "configured": False,
            "message": "TELEGRAM_BOT_TOKEN belum diset. Tambahkan ke file .env",
        }

    bot_info = await notifier.test_connection()
    demo_chat_id = os.getenv("TELEGRAM_DEMO_CHAT_ID", "")
    return {
        "configured": True,
        "bot_info": bot_info,
        "demo_chat_id_set": bool(demo_chat_id),
        "demo_chat_id_preview": demo_chat_id[:6] + "..." if demo_chat_id else None,
    }


@app.post("/api/telegram/test")
async def test_telegram_connection():
    """
    Test koneksi Telegram Bot dan kirim pesan test ke TELEGRAM_DEMO_CHAT_ID.
    Gunakan endpoint ini untuk verifikasi setup sebelum demo.
    """
    import os
    from core.telegram_notifier import get_telegram_notifier

    demo_chat_id = os.getenv("TELEGRAM_DEMO_CHAT_ID")
    if not demo_chat_id:
        raise HTTPException(
            status_code=400,
            detail="TELEGRAM_DEMO_CHAT_ID belum diset di .env"
        )

    notifier = get_telegram_notifier()
    if not notifier.is_configured:
        raise HTTPException(
            status_code=400,
            detail="TELEGRAM_BOT_TOKEN belum dikonfigurasi"
        )

    bot_info = await notifier.test_connection()
    if not bot_info.get("ok"):
        raise HTTPException(status_code=500, detail=f"Bot error: {bot_info.get('error')}")

    # Kirim pesan test
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M")
    test_msg = (
        f"✅ <b>DisasterReady — Test Koneksi</b>\n\n"
        f"Bot <b>{bot_info['bot_username']}</b> berhasil terhubung!\n"
        f"Sistem siap mengirim notifikasi early warning bencana.\n\n"
        f"<i>⏰ {now} WIB</i>"
    )
    result = await notifier.send_message(chat_id=demo_chat_id, message=test_msg)

    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)

    return {
        "status": "ok",
        "bot_username": bot_info["bot_username"],
        "message": f"✅ Pesan test berhasil dikirim ke chat_id {demo_chat_id}",
        "message_id": result.message_id,
    }


@app.post("/api/telegram/send-alert")
async def send_telegram_alert(payload: dict = Body(...)):
    """
    Kirim notifikasi peringatan dini bencana via Telegram.

    Body JSON:
    {
      "chat_id": "-100xxx",          // opsional, default ke TELEGRAM_DEMO_CHAT_ID
      "district_name": "Bogor Tengah",
      "alert_level": "Siaga",         // Awas / Siaga / Waspada
      "rainfall_mm": 290,
      "disaster_type": "banjir",      // banjir / longsor / cuaca_ekstrem / gempa
      "affected_count": 1240,         // opsional
      "vulnerable_count": 312         // opsional
    }
    """
    import os
    from core.telegram_notifier import get_telegram_notifier

    notifier = get_telegram_notifier()
    if not notifier.is_configured:
        raise HTTPException(
            status_code=400,
            detail="TELEGRAM_BOT_TOKEN belum dikonfigurasi. Set di .env"
        )

    chat_id = payload.get("chat_id") or os.getenv("TELEGRAM_DEMO_CHAT_ID")
    if not chat_id:
        raise HTTPException(
            status_code=400,
            detail="Sertakan 'chat_id' di body atau set TELEGRAM_DEMO_CHAT_ID di .env"
        )

    district_name = payload.get("district_name", "Tidak diketahui")
    alert_level = payload.get("alert_level", "Waspada")
    rainfall_mm = float(payload.get("rainfall_mm", 0))
    disaster_type = payload.get("disaster_type", "banjir")
    affected_count = int(payload.get("affected_count", 0))
    vulnerable_count = int(payload.get("vulnerable_count", 0))

    result = await notifier.send_disaster_alert(
        chat_id=chat_id,
        district_name=district_name,
        alert_level=alert_level,
        rainfall_mm=rainfall_mm,
        disaster_type=disaster_type,
        affected_count=affected_count,
        vulnerable_count=vulnerable_count,
    )

    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)

    firebase.log_action(
        agent_name="TelegramAPI",
        action="alert_sent",
        data={"chat_id": chat_id, "district": district_name, "level": alert_level},
        result="success"
    )
    return {
        "status": "sent",
        "chat_id": chat_id,
        "message_id": result.message_id,
        "district_name": district_name,
        "alert_level": alert_level,
    }



@app.get("/api/data/residents/stats")
async def get_residents_stats():
    """Statistik warga terdaftar (tanpa data pribadi)."""
    if not residents:
        return {"error": "Data belum dimuat"}
    lansia = sum(1 for r in residents if r["age"] >= 60)
    balita = sum(1 for r in residents if r["age"] <= 4)
    difabel = sum(1 for r in residents if r.get("disability", "none") != "none")
    districts = {}
    for r in residents:
        did = r.get("district_id", "unknown")
        districts[did] = districts.get(did, 0) + 1

    return {
        "total": len(residents),
        "lansia_60plus": lansia,
        "balita_0_4": balita,
        "difabel": difabel,
        "by_district": districts,
    }


@app.get("/api/data/volunteers/stats")
async def get_volunteers_stats():
    """Statistik relawan terdaftar."""
    if not volunteers:
        return {"error": "Data belum dimuat"}
    orgs = {}
    for v in volunteers:
        org = v.get("organization", "Unknown")
        orgs[org] = orgs.get(org, 0) + 1
    return {
        "total": len(volunteers),
        "by_organization": orgs,
    }


if __name__ == "__main__":
    import uvicorn
    import os
    uvicorn.run(
        "api.main:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", 8000)),
        reload=os.getenv("DEBUG", "true").lower() == "true",
    )
