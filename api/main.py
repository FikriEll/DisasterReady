"""
DisasterReady — FastAPI Backend
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

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.firebase_client import FirebaseClient
from core.bmkg_client import BMKGClient
from agents.orchestrator import create_orchestrator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Global State ──────────────────────────────────────────────────────────────
firebase = FirebaseClient(simulation_mode=True)
bmkg_client = BMKGClient(simulation_mode=True)
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
        simulation_mode=True,
    )
    logger.info("🚀 DisasterReady API Server siap!")
    yield
    logger.info("🛑 Server shutting down...")


app = FastAPI(
    title="DisasterReady API",
    description="Sistem Koordinasi Respons Bencana Otonom — Multi-Agent AI",
    version="1.0.0",
    lifespan=lifespan,
)

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
async def trigger_simulation(background_tasks: BackgroundTasks):
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
        result = await orchestrator.handle_disaster_alert(disaster_id=disaster_id, alerts=alerts)
        firebase.update_system_state({"simulation_running": False})
        return result

    background_tasks.add_task(run_pipeline)

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


# ── Synthetic Data Endpoints ──────────────────────────────────────────────────
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
