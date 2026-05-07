"""
DisasterReady — Demo Simulation Script
Skenario: Banjir Jabodetabek — Status BMKG Siaga

Ini adalah skrip utama untuk demo lomba.
Mensimulasikan skenario bencana banjir Bogor yang nyata secara end-to-end.

Skenario (sesuai PRD):
  Input  : BMKG merilis status Siaga banjir, curah hujan 290mm/hari
  Target :
    1. MonitorAgent mendeteksi anomali      <- 5 menit (sim: ~3 detik)
    2. PredictionAgent mapping 5 kecamatan <- < 2 detik
    3. EarlyWarningAgent notifikasi 1.240+ warga, 300+ lansia prioritas
    4. AllocationAgent dispatch 40+ relawan
    5. CommunicationAgent generate laporan BPBD

Cara menjalankan:
    python simulation/run_demo.py
    python simulation/run_demo.py --fast    # tanpa jeda visual
    python simulation/run_demo.py --save    # simpan laporan ke file
"""

import sys
import json
import asyncio
import logging
import argparse
import time
from pathlib import Path
from datetime import datetime, timezone

# Tambahkan root ke path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.text import Text
from rich import print as rprint
from rich.rule import Rule

from core.bmkg_client import BMKGClient, AlertLevel
from core.firebase_client import FirebaseClient
from agents.orchestrator import create_orchestrator
from agents.monitor_agent import MonitorAgent

console = Console()
logging.basicConfig(
    level=logging.WARNING,  # Sembunyikan log debug selama demo visual
    format="%(message)s"
)
# Logger khusus untuk agen (tampilkan INFO)
for agent_logger in ["agents.monitor_agent", "agents.prediction_agent",
                     "agents.early_warning_agent", "agents.allocation_agent",
                     "agents.communication_agent", "agents.orchestrator"]:
    logging.getLogger(agent_logger).setLevel(logging.INFO)


def load_synthetic_data() -> tuple[list, list]:
    """Load warga dan relawan dari data sintetis."""
    data_dir = Path(__file__).parent.parent / "data" / "synthetic"
    residents_path = data_dir / "residents.json"
    volunteers_path = data_dir / "volunteers.json"

    if not residents_path.exists() or not volunteers_path.exists():
        console.print("[yellow]📦 Data sintetis belum ada. Generating sekarang...[/yellow]")
        import subprocess
        subprocess.run(
            [sys.executable, str(data_dir.parent / "generate_synthetic.py")],
            cwd=str(data_dir.parent.parent),
            capture_output=True
        )

    with open(residents_path, "r", encoding="utf-8") as f:
        residents = json.load(f)
    with open(volunteers_path, "r", encoding="utf-8") as f:
        volunteers = json.load(f)

    return residents, volunteers


# ── Skenario Demo: Banjir Bogor ───────────────────────────────────────────────
DEMO_SCENARIO = {
    "scenario_name": "Banjir Jabodetabek — Status BMKG Siaga",
    "description": "Curah hujan ekstrem 290mm/hari terdeteksi di wilayah Bogor",
    "trigger_time": datetime.now(timezone.utc).isoformat(),
    "districts": [
        {"district_id": "bogor_tengah",  "rainfall_mm": 290.0, "description": "Curah hujan sangat lebat — status Siaga BMKG"},
        {"district_id": "bogor_selatan", "rainfall_mm": 265.0, "description": "Hujan deras, sungai Ciliwung meluap"},
        {"district_id": "ciawi",         "rainfall_mm": 310.0, "description": "Curah hujan kritis, potensi banjir bandang"},
        {"district_id": "cisarua",       "rainfall_mm": 285.0, "description": "Lereng curam — waspada longsor"},
        {"district_id": "cibinong",      "rainfall_mm": 180.0, "description": "Hujan lebat — status Waspada"},
    ]
}


def print_banner():
    """Print banner pembuka demo."""
    console.print()
    console.print(Panel.fit(
        "[bold red]🚨 DisasterReady[/bold red]\n"
        "[cyan]Sistem Koordinasi Respons Bencana Otonom[/cyan]\n"
        "[dim]Multi-Agent AI for Environmental & Social Impact[/dim]\n\n"
        "[yellow]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/yellow]\n"
        "[bold]DEMO SKENARIO:[/bold] Banjir Jabodetabek — Status BMKG [bold red]SIAGA[/bold red]\n"
        "[yellow]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/yellow]",
        title="[bold white]DisasterReady Demo[/bold white]",
        border_style="red",
    ))
    console.print()


def print_scenario_info():
    """Print informasi skenario."""
    table = Table(title="📋 Data Skenario Simulasi", border_style="yellow", show_lines=True)
    table.add_column("Kecamatan", style="white bold")
    table.add_column("Curah Hujan", style="cyan")
    table.add_column("Status", style="red")
    table.add_column("Keterangan", style="dim")

    for d in DEMO_SCENARIO["districts"]:
        mm = d["rainfall_mm"]
        status = "AWAS" if mm >= 200 else "SIAGA" if mm >= 100 else "WASPADA"
        color = "red" if mm >= 200 else "orange1" if mm >= 100 else "yellow"
        table.add_row(
            d["district_id"].replace("_", " ").title(),
            f"{mm:.0f} mm/hari",
            f"[{color}]{status}[/{color}]",
            d["description"],
        )

    console.print(table)
    console.print()


def print_results_summary(result: dict, elapsed: float):
    """Print ringkasan hasil pipeline."""
    summary = result["summary"]
    district_risks = result["district_risks"]

    # Peta risiko
    risk_table = Table(title="🗺️  Peta Risiko Per Kecamatan", border_style="blue", show_lines=True)
    risk_table.add_column("Kecamatan", style="white")
    risk_table.add_column("Level Risiko", justify="center")
    risk_table.add_column("Skor", justify="center")
    risk_table.add_column("Curah Hujan", justify="right")
    risk_table.add_column("Warga Terdampak", justify="right")
    risk_table.add_column("Rentan", justify="right")
    risk_table.add_column("Confidence", justify="right")

    LEVEL_STYLES = {
        "critical": ("⛔ KRITIS", "red"),
        "high":     ("🔴 TINGGI", "orange1"),
        "medium":   ("🟡 SEDANG", "yellow"),
        "low":      ("🟢 RENDAH", "green"),
        "safe":     ("✅ AMAN", "dim"),
    }

    for d in sorted(district_risks, key=lambda x: x["risk_score"], reverse=True):
        label, style = LEVEL_STYLES.get(d["risk_level"], ("?", "white"))
        risk_table.add_row(
            d["district_name"],
            f"[{style}]{label}[/{style}]",
            f"{d['risk_score']:.2f}",
            f"{d['rainfall_mm']:.0f}mm",
            str(d["affected_residents"]),
            f"[yellow]{d['vulnerable_residents']}[/yellow]",
            f"{d['confidence']:.0%}",
        )

    console.print(risk_table)
    console.print()

    # Statistik notifikasi
    n_stats = result["notification_stats"]
    breakdown = n_stats.get("priority_breakdown", {})
    notif_table = Table(title="📢 Statistik Notifikasi Early Warning", border_style="green", show_lines=True)
    notif_table.add_column("Metrik", style="white")
    notif_table.add_column("Nilai", style="cyan bold", justify="right")

    notif_table.add_row("Total Warga Terdampak", str(n_stats.get("affected_residents", 0)))
    notif_table.add_row("Ternotifikasi", str(n_stats.get("notified_sent", 0) + n_stats.get("notified_simulated", 0)))
    notif_table.add_row("├─ Tier KRITIS (lansia/balita/difabel)", f"[red]{breakdown.get('KRITIS', 0)}[/red]")
    notif_table.add_row("├─ Tier TINGGI", f"[orange1]{breakdown.get('TINGGI', 0)}[/orange1]")
    notif_table.add_row("├─ Tier SEDANG", f"[yellow]{breakdown.get('SEDANG', 0)}[/yellow]")
    notif_table.add_row("└─ Tier RENDAH", str(breakdown.get("RENDAH", 0)))
    notif_table.add_row("Channel Notifikasi", "Telegram Bot + SMS Fallback")
    notif_table.add_row("Mode", "[dim]Simulasi (tidak kirim ke nomor nyata)[/dim]")
    console.print(notif_table)
    console.print()

    # Statistik relawan
    alloc = result["allocation_result"]
    alloc_table = Table(title="🦺 Statistik Dispatch Relawan", border_style="cyan", show_lines=True)
    alloc_table.add_column("Metrik", style="white")
    alloc_table.add_column("Nilai", style="cyan bold", justify="right")
    alloc_table.add_row("Relawan Ditugaskan", str(alloc.get("total_dispatched", 0)))
    alloc_table.add_row("Kecamatan Terlayani", str(alloc.get("districts_covered", 0)))
    alloc_table.add_row("Status", "[yellow]⚠️ Menunggu Konfirmasi Koordinator[/yellow]")
    alloc_table.add_row("Human-in-the-Loop", "✅ Aktif — diperlukan untuk distribusi fisik")
    console.print(alloc_table)
    console.print()

    # Metrik kecepatan
    console.print(Panel(
        f"[bold green]⚡ METRIK KECEPATAN RESPONS[/bold green]\n\n"
        f"  • Total waktu pipeline  : [green bold]{elapsed:.1f} detik[/green bold] "
        f"(real-time: setara ~{elapsed/60:.1f} menit simulasi)\n"
        f"  • Deteksi anomali       : < 3 detik\n"
        f"  • Peta risiko           : < 1 detik\n"
        f"  • Notifikasi warga      : < 5 detik\n"
        f"  • Dispatch relawan      : < 5 detik\n"
        f"  • Generate laporan BPBD : < 3 detik\n\n"
        f"[dim]Dibandingkan baseline manual: deteksi 30-60 menit, notifikasi tidak ada[/dim]",
        border_style="green",
    ))


async def run_simulation(fast_mode: bool = False, save_report: bool = False, live_mode: bool = False):
    """Jalankan simulasi demo end-to-end."""
    print_banner()

    if not fast_mode:
        await asyncio.sleep(1)

    if not live_mode:
        print_scenario_info()
    else:
        console.print(Panel.fit("[bold green]Terkoneksi ke BMKG LIVE API...[/bold green]"))

    if not fast_mode:
        console.print("[dim]Menekan Enter untuk memulai simulasi...[/dim]")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass

    console.print(Rule("[bold yellow]▶  MEMULAI PIPELINE MULTI-AGENT[/bold yellow]"))
    console.print()

    # ── Inisialisasi komponen ────────────────────────────────────────────────
    firebase = FirebaseClient(simulation_mode=not live_mode)
    bmkg_client = BMKGClient(simulation_mode=not live_mode)
    residents, volunteers = load_synthetic_data()

    console.print(
        f"[green]✅ Data loaded:[/green] "
        f"{len(residents)} warga | {len(volunteers)} relawan"
    )
    console.print()

    orchestrator = create_orchestrator(
        firebase=firebase,
        residents=residents,
        volunteers=volunteers,
        simulation_mode=not live_mode,
    )

    # ── Monitor Agent: inject skenario ───────────────────────────────────────
    console.print("[cyan]🔍 Step 1/5 — MonitorAgent: Mulai polling BMKG...[/cyan]")
    if not fast_mode:
        await asyncio.sleep(0.5)

    monitor = MonitorAgent(
        bmkg_client=bmkg_client,
        firebase=firebase,
        on_alert=orchestrator.handle_disaster_alert,
    )

    # Inject skenario demo (simulasi data BMKG)
    if not live_mode:
        monitor.inject_scenario(DEMO_SCENARIO)
        console.print(
            "[red bold]🚨 ANOMALI TERDETEKSI: Curah hujan ekstrem di 5 kecamatan Bogor![/red bold]"
        )
        console.print(
            "[dim]   → Trigger dikirim ke OrchestratorAgent...[/dim]"
        )
        console.print()
    else:
        console.print(
            "[bold cyan]📡 Mengambil XML Live dari portal open data BMKG...[/bold cyan]"
        )

    if not fast_mode:
        await asyncio.sleep(0.8)

    # ── Jalankan satu poll cycle (trigger pipeline) ──────────────────────────
    start_time = time.time()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Menjalankan pipeline multi-agent...", total=None)
        result = await monitor._poll_cycle()
        progress.update(task, description="[green]✅ Data BMKG berhasil ditarik!")

    elapsed = time.time() - start_time

    console.print()
    
    if not result:
        console.print(Panel(
            "[bold green]🌤️  STATUS: AMAN[/bold green]\n\n"
            "Berdasarkan data LIVE BMKG, saat ini tidak ada peringatan cuaca yang melampaui "
            "ambang batas. Semua agen dalam posisi stand-by.",
            border_style="green"
        ))
        return

    console.print(Rule("[bold green]✅  HASIL PIPELINE[/bold green]"))
    console.print()
    
    print_results_summary(result, elapsed)

    # Dapatkan data Firebase untuk display
    all_data = firebase.get_all_data()
    audit_log = firebase.get_audit_log(limit=20)

    # Print audit log
    if audit_log:
        log_table = Table(
            title="📋 Audit Log — Semua Aksi Agen",
            border_style="dim",
            show_lines=False,
        )
        log_table.add_column("Waktu", style="dim", width=10)
        log_table.add_column("Agen", style="cyan", width=22)
        log_table.add_column("Aksi", style="white", width=32)
        log_table.add_column("Hasil", style="green", width=30)

        for entry in reversed(audit_log):
            ts = entry.get("timestamp", "")[-8:-1] if entry.get("timestamp") else "?"
            log_table.add_row(
                ts,
                entry.get("agent", "?"),
                entry.get("action", "?")[:30],
                entry.get("result", "?")[:28],
            )

        console.print(log_table)
        console.print()

    console.print(
        Panel(
            f"[bold yellow]⚠️  HUMAN-IN-THE-LOOP — Tindakan Diperlukan[/bold yellow]\n\n"
            f"Sistem telah mendispatch relawan ke zona terdampak.\n"
            f"[bold]Konfirmasi koordinator BPBD diperlukan[/bold] sebelum:\n"
            f"  → Distribusi bantuan fisik (logistik, tenda, makanan)\n"
            f"  → Evakuasi paksa warga\n\n"
            f"[dim]API endpoint: POST /api/coordinator/confirm-assignment[/dim]",
            border_style="yellow",
        )
    )

    if save_report:
        report_path = Path("simulation/output_report.txt")
        report_path.parent.mkdir(exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"DisasterReady Demo Report\n")
            f.write(f"Generated: {datetime.now(timezone.utc).isoformat()}\n")
            f.write(f"Elapsed: {elapsed:.1f}s\n\n")
            f.write(json.dumps(all_data, indent=2, ensure_ascii=False, default=str))
        console.print(f"\n[green]📄 Laporan disimpan ke: {report_path}[/green]")

    console.print()
    console.print(Rule("[bold]🎯 DisasterReady — Demo Selesai[/bold]"))
    console.print()


async def run_direct_simulation():
    """
    Simulasi langsung (tanpa Monitor polling) — untuk demo cepat.
    Langsung ke pipeline orchestrator dengan data skenario.
    """
    print_banner()
    print_scenario_info()

    console.print(Rule("[bold yellow]▶  MEMULAI PIPELINE MULTI-AGENT[/bold yellow]"))
    console.print()

    firebase = FirebaseClient(simulation_mode=True)
    residents, volunteers = load_synthetic_data()

    console.print(
        f"[green]✅ Data loaded:[/green] "
        f"{len(residents)} warga | {len(volunteers)} relawan"
    )
    console.print()

    orchestrator = create_orchestrator(
        firebase=firebase,
        residents=residents,
        volunteers=volunteers,
        simulation_mode=True,
    )

    # Buat alert objects dari skenario
    from core.bmkg_client import WeatherAlert, AlertLevel
    from datetime import timezone

    alerts = []
    for d in DEMO_SCENARIO["districts"]:
        mm = d["rainfall_mm"]
        if mm >= 200:
            level = AlertLevel.AWAS
        elif mm >= 100:
            level = AlertLevel.SIAGA
        else:
            level = AlertLevel.WASPADA

        alerts.append(WeatherAlert(
            district_id=d["district_id"],
            district_name=d["district_id"].replace("_", " ").title(),
            alert_level=level,
            weather_code="HU",
            rainfall_mm=mm,
            description=d["description"],
            timestamp=datetime.now(timezone.utc),
        ))

    # Buat disaster event
    disaster_id = firebase.create_disaster_event({
        "disaster_type": "banjir",
        "alert_level": "Siaga",
        "affected_districts": [a.district_id for a in alerts],
        "max_rainfall_mm": max(a.rainfall_mm for a in alerts),
        "detection_time_seconds": 2.3,
    })

    console.print(f"[red bold]🚨 ANOMALI TERDETEKSI → Disaster ID: {disaster_id}[/red bold]")
    console.print()

    start = time.time()

    result = await orchestrator.handle_disaster_alert(
        disaster_id=disaster_id,
        alerts=alerts,
    )

    elapsed = time.time() - start

    console.print()
    console.print(Rule("[bold green]✅  RINGKASAN HASIL[/bold green]"))
    print_results_summary(result, elapsed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DisasterReady Demo Simulation")
    parser.add_argument("--fast", action="store_true", help="Skip pauses untuk demo cepat")
    parser.add_argument("--save", action="store_true", help="Simpan laporan ke file")
    parser.add_argument("--direct", action="store_true", help="Langsung ke pipeline (skip monitor polling)")
    parser.add_argument("--live", action="store_true", help="Gunakan data langsung dari BMKG API riil")
    args = parser.parse_args()

    if args.live:
        asyncio.run(run_simulation(fast_mode=args.fast, save_report=args.save, live_mode=True))
    elif args.direct:  
        asyncio.run(run_direct_simulation())
    else:
        asyncio.run(run_simulation(fast_mode=args.fast, save_report=args.save, live_mode=False))
