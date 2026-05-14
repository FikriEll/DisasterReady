# Pantara 🚨

**Sistem Koordinasi Respons Bencana Otonom dengan Early Warning**

> Kategori: AI for Environmental & Social Impact — Mahasiswa/i Sederajat
> Tim: Pantara Team | April 2026

---

## Deskripsi

Pantara adalah sistem multi-agent otonom yang menjembatani gap kritis dalam sistem peringatan dini bencana Indonesia. BMKG sudah punya datanya — warga belum dapat notifikasinya. Pantara adalah jembatan itu.

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
                            (Laporan via Gemini API)
```

| Agen | Peran | Otorisasi |
|------|-------|-----------| 
| Monitor Agent | Polling BMKG setiap 5 menit | Otonom penuh |
| Prediction Agent | Peta risiko per kecamatan (rule-based + BNPB historis) | Otonom penuh |
| Early Warning Agent | Notifikasi warga (prioritas rentan) | Otonom penuh |
| Allocation Agent | Dispatch relawan + GIS routing (haversine / ORS API) | Otonom + konfirmasi |
| Communication Agent | Laporan narasi via Google Gemini API | Otonom penuh |
| Orchestrator Agent | Koordinasi pipeline multi-agent (Python async) | Sistem koordinasi |

## Quick Start

### 1. Setup Environment

```bash
git clone <repo-url>
cd Pantara-main

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
# Output: data/synthetic/residents.json  (2000 warga)
#         data/synthetic/volunteers.json (150 relawan)
```

### 3. Jalankan Server Dashboard

```bash
python api/main.py
# atau:
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

### 4. Jalankan Demo Simulasi (Terminal — Opsional)

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

## Stack Teknologi

### Framework & Library

| Software/API | Penyedia | Versi | Penggunaan |
|---|---|---|---|
| **Google Gemini API** | Google | gemini-2.0-flash | Generate laporan situasi, personalisasi notifikasi warga |
| **FastAPI** | Sebastián Ramírez | 0.115.0 | Backend REST API, SSE streaming real-time ke dashboard |
| **Firebase Realtime DB** | Google LLC | SDK 9+ | State management in-memory (simulasi) / cloud (produksi) |
| **scikit-learn** | scikit-learn Contributors | 1.4+ | Komponen model prediksi risiko (rule-based + logistic) |
| **NumPy** | NumPy Contributors | 1.26+ | Operasi array untuk kalkulasi risiko |
| **httpx** | Encode | 0.27+ | HTTP async client untuk BMKG API & ORS API |
| **OpenRouteService API** | HeiGIT, Heidelberg | v2 | GIS routing relawan ke lokasi terdampak (opsional) |
| **Leaflet.js** | Vladimir Agafonkin | 1.9.4 | Visualisasi peta interaktif di dashboard |
| **Chart.js** | Chart.js Contributors | 4.4+ | Grafik statistik notifikasi |
| **Twilio SMS API** | Twilio Inc. | REST v2 | Notifikasi SMS (produksi, fallback) |
| **WhatsApp Business API** | Meta Platforms | Cloud API v18+ | Notifikasi WA (produksi, primary) |
| **python-dotenv** | Theskumar | — | Manajemen environment variables |

### Sumber Data Publik

| Sumber | Penyedia | URL | Penggunaan |
|---|---|---|---|
| **BMKG Open API** | BMKG | data.bmkg.go.id | Monitoring cuaca, status Siaga/Waspada/Awas |
| **BNPB Open Data** | BNPB | gis.bnpb.go.id | Data historis bencana per wilayah (embedded di PredictionAgent) |
| **Data BPS** | BPS | bps.go.id | Demografi lansia per kecamatan (vulnerability scoring) |
| **DEMNAS** | BIG | tanahair.indonesia.go.id | Topografi (kemiringan lahan, embedded di DISTRICTS_META) |
| **OpenStreetMap** | OSM Contributors | openstreetmap.org | Peta dasar (CartoDB Dark Tiles) dan GIS routing |

## Struktur Proyek

```
DisasterReady-main/
├── agents/                       # 6 agen spesialis
│   ├── orchestrator.py           # Koordinator utama (Python async pipeline)
│   ├── monitor_agent.py          # Polling BMKG + deteksi anomali
│   ├── early_warning_agent.py    # Notifikasi warga (prioritas rentan)
│   ├── prediction_agent.py       # Peta risiko (rule-based + BNPB historis)
│   ├── allocation_agent.py       # GIS routing + dispatch relawan
│   └── communication_agent.py   # Laporan narasi via Google Gemini API
├── core/                         # Utilities bersama
│   ├── bmkg_client.py            # Client BMKG Open API
│   ├── firebase_client.py        # State management (in-memory / Firebase)
│   ├── vulnerability_scorer.py   # Hitung vulnerability score per warga
│   ├── geo_utils.py              # Haversine, GIS routing, GeoJSON builder
│   └── notification_dispatcher.py # Multi-channel notif (WA/SMS/simulasi)
├── api/                          # FastAPI backend
│   └── main.py                   # REST endpoints + SSE streaming
├── dashboard/                    # Frontend dashboard
│   ├── index.html
│   ├── css/style.css
│   └── js/
│       ├── dashboard.js          # Controller utama SSE + simulasi
│       ├── map.js                # Leaflet peta risiko + marker relawan
│       └── charts.js             # Chart.js visualisasi prioritas
├── data/                         # Data sintetis
│   ├── generate_synthetic.py
│   └── synthetic/
│       ├── residents.json        # 2000 warga (generated)
│       └── volunteers.json       # 150 relawan (generated)
├── simulation/                   # Demo script terminal
│   └── run_demo.py
├── disaster_ready_prd_v1.md      # Product Requirements Document
├── requirements.txt
└── .env.example                  # Template environment variables
```

## Alur Kerja Dashboard

### Siapa yang Menggunakan Dashboard?

Dashboard di `http://localhost:8000/dashboard` ditujukan untuk **koordinator BPBD / operator pusat**.
Warga biasa **tidak melihat dashboard** — mereka hanya menerima notifikasi personal via Telegram/WhatsApp/SMS.

### Alur Penuh Dari Awal Hingga Akhir

```
1. Koordinator buka dashboard → klik "Jalankan Simulasi Demo"
2. OrchestratorAgent memulai pipeline:
   [Step 1] PredictionAgent → peta risiko muncul di peta
   [Step 2&3, paralel]:
     EarlyWarningAgent → notifikasi dikirim ke warga (lansia/difabel PERTAMA)
     AllocationAgent  → relawan ditemukan, marker biru muncul di peta
   [Step 4] CommunicationAgent → laporan situasi via Gemini API
3. Koordinator melihat peta + laporan → klik "✓ Konfirmasi Penugasan"
   → Status relawan berubah dari pending_confirmation → confirmed
   → (Produksi: relawan mulai bergerak ke lokasi)
4. Bencana mereda → koordinator klik "↺ Reset"
   → State Firebase dihapus, agen direset, peta bersih
   → Siap untuk simulasi berikutnya
```

### Human-in-the-Loop

| Aksi | Otorisasi | Alasan |
|------|-----------|--------|
| Monitoring & deteksi anomali | ✅ Otonom penuh | Latensi rendah kritis |
| Notifikasi early warning | ✅ Otonom penuh | Makin cepat makin baik |
| Prediksi & peta risiko | ✅ Otonom penuh | Output informasi, bukan keputusan |
| Dispatch relawan (informasi) | ✅ Otonom + notif koordinator | Urgency tinggi, bisa di-override |
| **Distribusi bantuan fisik** | ⚠️ **Wajib konfirmasi koordinator** | Menyangkut sumber daya nyata |

## Prinsip AI Bertanggung Jawab

### Fairness & Inklusivitas
- Tidak menggunakan variabel diskriminatif (ras, agama, status ekonomi)
- Kelompok rentan mendapat notifikasi **lebih awal**, bukan lebih lambat
- Pesan dalam Bahasa Indonesia sederhana
- SMS fallback untuk warga tanpa smartphone

### Transparansi
- Setiap aksi agen tercatat di Firebase audit log
- Vulnerability score dihitung dari data publik BPS — bukan black box
- Setiap prediksi disertai confidence score dan reasoning yang dapat diaudit:
  `"Curah hujan 290mm (faktor: 1.00) + Kemiringan 8.5° DEMNAS (faktor: 0.55) + Historis BNPB (faktor: 0.55) = Skor risiko 0.83 → CRITICAL | Confidence: 90%"`

### Keamanan Data
- Data koordinat warga tidak dikirim ke model AI eksternal
- Gemini API hanya menerima konteks situasi (kecamatan, curah hujan, statistik)
- Warga dapat opt-out dari sistem notifikasi kapan saja

## Metrik Target Demo

| Metrik | Baseline Manual | Target DisasterReady |
|--------|-----------------|---------------------|
| Waktu deteksi anomali | 30-60 menit | < 5 menit (demo: < 5 detik) |
| Notifikasi lansia pertama | Tidak ada | < 10 menit (demo: < 10 detik) |
| Coverage notifikasi | Tidak terstruktur | > 95% warga di zona risiko |
| Koordinasi relawan | 1-2 jam (manual) | < 15 menit (demo: < 15 detik) |
| Audit log completeness | Tidak ada | 100% semua aksi tercatat |

## Environment Variables

Lihat `.env.example` untuk daftar lengkap. Variabel kunci:

```
# Wajib untuk laporan AI
GEMINI_API_KEY=your_gemini_api_key

# Opsional — tanpa ini sistem tetap berjalan (simulasi mode)
OPENROUTESERVICE_API_KEY=   # GIS routing akurat (fallback: haversine)
TWILIO_ACCOUNT_SID=          # SMS produksi
TWILIO_AUTH_TOKEN=
WHATSAPP_ACCESS_TOKEN=       # WhatsApp Business produksi
FIREBASE_DATABASE_URL=        # Firebase cloud (fallback: in-memory)

# Mode
SIMULATION_MODE=true          # true = in-memory, false = Firebase cloud
```

---

*DisasterReady dirancang bukan untuk menggantikan BMKG, melainkan untuk menjembatani gap antara data early warning yang sudah ada dengan warga yang paling membutuhkan.*
