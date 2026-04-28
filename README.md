# DisasterReady 🚨

**Sistem Koordinasi Respons Bencana Otonom dengan Early Warning**

> Kategori: AI for Environmental & Social Impact — Mahasiswa/i Sederajat
> Tim: DisasterReady Team | April 2026

---

## Deskripsi

DisasterReady adalah sistem multi-agent otonom yang menjembatani gap kritis dalam sistem peringatan dini bencana Indonesia. BMKG sudah punya datanya — warga belum dapat notifikasinya. DisasterReady adalah jembatan itu.

**Masalah yang dipecahkan:**
- 1.942 kejadian bencana di Indonesia (2024, data BNPB), berdampak pada 5,64 juta jiwa
- Sistem early warning sudah ada (BMKG InaTEWS) namun *last-mile delivery* ke warga individual tidak merata
- Kelompok rentan (lansia, balita, difabel) tidak mendapat perlakuan prioritas

## Arsitektur Multi-Agent

```
BMKG API ──► MonitorAgent ──► OrchestratorAgent
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
             PredictionAgent  EarlyWarning     AllocationAgent
             (Peta Risiko)    Agent (Notif)    (GIS Routing)
                    │               │               │
                    └───────────────┴───────────────┘
                                    │
                            CommunicationAgent
                            (Laporan via Claude)
```

| Agen | Peran | Otorisasi |
|------|-------|-----------|
| Monitor Agent | Polling BMKG setiap 5 menit | Otonom penuh |
| Prediction Agent | Peta risiko per kecamatan | Otonom penuh |
| Early Warning Agent | Notifikasi warga (prioritas rentan) | Otonom penuh |
| Allocation Agent | Dispatch relawan + GIS routing | Otonom + konfirmasi |
| Communication Agent | Laporan narasi Claude API | Otonom penuh |
| Orchestrator Agent | Koordinasi semua agen | Sistem koordinasi |

## Quick Start

### 1. Setup Environment

```bash
git clone <repo-url>
cd disaster_ready

# Buat virtual environment
python -m venv venv
source venv/bin/activate   # Mac/Linux
# atau: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Copy dan isi environment variables
cp .env.example .env
# Edit .env dengan API keys yang dimiliki
```

### 2. Generate Data Sintetis

```bash
python data/generate_synthetic.py
# Output: data/synthetic/residents.json (2000 warga)
#         data/synthetic/volunteers.json (150 relawan)
```

### 3. Jalankan Demo Simulasi (Terminal)

```bash
python simulation/run_demo.py
```

Output terminal akan menampilkan seluruh pipeline multi-agent secara visual dengan Rich formatting.

**Contoh output:**

```
🗺️  Peta Risiko Per Kecamatan
┌────────────────┬──────────────┬───────┬────────────┬──────────────────┬────────┐
│ Kecamatan      │ Level Risiko │ Skor  │ Curah Hujan│ Warga Terdampak  │ Rentan │
├────────────────┼──────────────┼───────┼────────────┼──────────────────┼────────┤
│ Ciawi          │ ⛔ KRITIS    │ 0.87  │ 310mm      │ 198              │ 28     │
│ Bogor Tengah   │ ⛔ KRITIS    │ 0.82  │ 290mm      │ 245              │ 34     │
│ Cisarua        │ ⛔ KRITIS    │ 0.85  │ 285mm      │ 167              │ 23     │
```

### 4. Jalankan Server Dashboard

```bash
# Di terminal baru:
uvicorn api.main:app --reload --port 8000

# Buka browser:
# http://localhost:8000/dashboard
```

Dashboard menampilkan:
- 🗺️ Peta Leaflet.js interaktif dengan zona risiko berwarna
- 📊 Metrik real-time (warga ternotifikasi, relawan, waktu respons)
- 🤖 Status semua agen secara live
- 📋 Audit log lengkap untuk transparansi
- ▶️ Panel simulasi demo one-click

## Stack Teknologi

### Framework & Library

| Software/API | Penyedia | Versi | Penggunaan |
|---|---|---|---|
| **AutoGen** | Microsoft Research | 0.4.x | Orkestrasi multi-agent, GroupChat pattern |
| **Anthropic Claude API** | Anthropic, PBC | claude-sonnet-4-20250514 | Generate laporan situasi, personalisasi notifikasi |
| **FastAPI** | Sebastián Ramírez | 0.115.0 | Backend REST API, SSE streaming |
| **Firebase Realtime DB** | Google LLC | SDK 9+ | State management, audit log real-time |
| **GeoPandas** | GeoPandas Contributors | 0.14+ | Spatial join koordinat dengan zona risiko |
| **OpenRouteService API** | HeiGIT, Heidelberg | v2 | GIS routing relawan ke lokasi terdampak |
| **scikit-learn** | scikit-learn Contributors | 1.4+ | Model prediksi risiko banjir/longsor |
| **Leaflet.js** | Vladimir Agafonkin | 1.9.4 | Visualisasi peta interaktif di dashboard |
| **Chart.js** | Chart.js Contributors | 4.4+ | Grafik statistik notifikasi |
| **python-telegram-bot** | python-telegram-bot | 21.3 | Notifikasi early warning via Telegram |
| **Twilio SMS API** | Twilio Inc. | REST v2 | Fallback notifikasi SMS |

### Sumber Data Publik

| Sumber | Penyedia | URL | Penggunaan |
|---|---|---|---|
| **BMKG Open API** | BMKG | data.bmkg.go.id | Monitoring cuaca, status Siaga/Waspada/Awas |
| **BNPB Open Data** | BNPB | gis.bnpb.go.id | Data historis bencana per wilayah |
| **Data BPS** | BPS | bps.go.id | Demografi lansia per kecamatan |
| **DEMNAS** | BIG | tanahair.indonesia.go.id | Topografi (kemiringan lahan) |
| **OpenStreetMap** | OSM Contributors | openstreetmap.org | Peta dasar dan GIS routing |

## Struktur Proyek

```
disaster_ready/
├── agents/               # 6 agen spesialis
│   ├── orchestrator.py   # Koordinator utama
│   ├── monitor_agent.py  # Polling BMKG
│   ├── early_warning_agent.py  # Notifikasi warga
│   ├── prediction_agent.py     # Peta risiko
│   ├── allocation_agent.py     # GIS routing
│   └── communication_agent.py  # Laporan Claude
├── core/                 # Utilities
│   ├── bmkg_client.py
│   ├── firebase_client.py
│   ├── vulnerability_scorer.py
│   ├── geo_utils.py
│   └── notification_dispatcher.py
├── api/                  # FastAPI backend
│   └── main.py
├── dashboard/            # Frontend dashboard
│   ├── index.html
│   ├── css/style.css
│   └── js/
├── data/                 # Data sintetis
│   └── synthetic/
├── simulation/           # Demo script
│   └── run_demo.py
└── requirements.txt
```

## Prinsip AI Bertanggung Jawab

### Human-in-the-Loop

| Aksi | Otorisasi |
|------|-----------|
| Monitoring & deteksi anomali | ✅ Otonom penuh |
| Notifikasi early warning | ✅ Otonom penuh |
| Prediksi & peta risiko | ✅ Otonom penuh |
| Dispatch relawan (informasi) | ✅ Otonom + notif koordinator |
| **Distribusi bantuan fisik** | ⚠️ **Wajib konfirmasi koordinator** |

### Fairness & Inklusivitas
- Tidak menggunakan variabel diskriminatif (ras, agama, status ekonomi)
- Kelompok rentan mendapat notifikasi **lebih awal**, bukan lebih lambat
- Pesan dalam Bahasa Indonesia sederhana
- SMS fallback untuk warga tanpa smartphone

### Transparansi
- Setiap aksi agen tercatat di Firebase audit log
- Vulnerability score dihitung dari data publik BPS — bukan black box
- Setiap prediksi disertai confidence score dan reasoning yang dapat diaudit

## Metrik Target Demo

| Metrik | Baseline Manual | Target DisasterReady |
|--------|-----------------|---------------------|
| Waktu deteksi anomali | 30-60 menit | < 5 menit (demo: < 5 detik) |
| Notifikasi lansia pertama | Tidak ada | < 10 menit (demo: < 10 detik) |
| Coverage notifikasi | Tidak terstruktur | > 95% warga di zona risiko |
| Koordinasi relawan | 1-2 jam (manual) | < 15 menit (demo: < 15 detik) |
| Audit log completeness | Tidak ada | 100% semua aksi tercatat |

---

*DisasterReady dirancang bukan untuk menggantikan BMKG, melainkan untuk menjembatani gap antara data early warning yang sudah ada dengan warga yang paling membutuhkan.*
