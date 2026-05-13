**🚨 DisasterReady**

_Koordinator Respons Bencana Otonom dengan Early Warning_

PRD v2.0 • April 2026 • Mahasiswa/i - AI for Environmental & Social Impact

| **Versi**              | **Kategori**                                       | **Status**  | **Tanggal** |
| ---------------------- | -------------------------------------------------- | ----------- | ----------- |
| 2.0 (Submission Lomba) | Mahasiswa/i - AI for Environmental & Social Impact | Final | April 2026  |

# **1\. Ringkasan Eksekutif**

## **1.1 Problem Statement**

Indonesia adalah negara dengan frekuensi bencana alam tertinggi ke-5 di dunia. Sepanjang 2024, BNPB mencatat 1.942 kejadian bencana yang berdampak pada lebih dari 5,64 juta jiwa. Infrastruktur early warning seperti BMKG dan InaTEWS sudah ada - namun masalah sesungguhnya ada di lapisan terakhir.

_"BMKG sudah punya datanya. Warga belum dapat notifikasinya. DisasterReady adalah jembatan itu."_

Tiga gap kritis yang belum terpecahkan:

- Diseminasi masih satu arah dan pasif - warga harus aktif cek website/medsos BMKG
- Tidak ada personalisasi berbasis lokasi warga individual
- Kelompok rentan (lansia, balita, difabel) tidak mendapat prioritas dalam sistem notifikasi
- Koordinasi relawan masih manual, lambat, dan bergantung kontak personal BPBD

## **1.2 Solusi: DisasterReady**

DisasterReady adalah sistem multi-agent otonom yang dibangun di atas teknologi open-source dan AI gratis, yang:

- Memantau data BMKG/BNPB secara real-time setiap 5 menit
- Memprediksi wilayah berisiko sebelum bencana terjadi menggunakan model ringan (rule-based + ML sederhana)
- Mengirim notifikasi proaktif ke warga berdasarkan lokasi dan kerentanan
- Mengkoordinasikan distribusi bantuan ke relawan terdekat - dengan kelompok rentan sebagai prioritas utama
- Menghasilkan rekomendasi jalur evakuasi yang aman dan terhindar dari zona bahaya secara real-time

## **1.3 Dampak Terukur (Target Simulasi)**

| **Metrik**                       | **Baseline (Manual)**           | **Target DisasterReady**              | **Dasar Perhitungan**                              |
| -------------------------------- | ------------------------------- | ------------------------------------- | -------------------------------------------------- |
| Waktu deteksi anomali cuaca      | 30-60 menit (monitoring manual) | < 5 menit (otomatis)                  | Polling interval 5 menit + async XML parsing BMKG  |
| Notifikasi warga sebelum bencana | Tidak ada / via medsos BMKG     | Personal, berbasis lokasi, < 10 menit | GeoJSON overlay + Telegram Bot API delivery        |
| Identifikasi kelompok rentan     | Manual, tidak terstruktur       | Otomatis dari data BPS per kecamatan  | Vulnerability scoring dari data BPS per kecamatan  |
| Waktu koordinasi relawan         | 1-2 jam (telepon manual)        | < 15 menit (dispatch otomatis)        | ORS routing + radius-based greedy assignment       |
| Cakupan daerah terpantau         | Tergantung petugas BPBD         | Real-time, seluruh wilayah terdaftar  | Semua wilayah dengan data BMKG aktif tercakup      |

# **2\. Latar Belakang & Konteks**

## **2.1 Kondisi Kebencanaan Indonesia**

Indonesia berada di "Ring of Fire" dan pertemuan tiga lempeng tektonik, menjadikannya salah satu negara paling rawan bencana di dunia. Ancaman bersifat multi-hazard: banjir, tanah longsor, gempa bumi, tsunami, dan erupsi gunung api kerap terjadi bersamaan atau saling memicu.

| **Jenis Bencana** | **Frekuensi (2024)** | **Wilayah Utama**                 | **Karakteristik**                        |
| ----------------- | -------------------- | --------------------------------- | ---------------------------------------- |
| Banjir            | ~800 kejadian/tahun  | Jabodetabek, Kalimantan, Sulawesi | Dapat diprediksi 6-24 jam sebelumnya     |
| Tanah Longsor     | ~400 kejadian/tahun  | Jawa Barat, Sumatra, Sulawesi     | Dipicu curah hujan ekstrem               |
| Gempa Bumi        | Ratusan/tahun        | Sulawesi, NTB, Jawa Barat         | Sulit diprediksi; lokasi dapat dipetakan |
| Tsunami           | Jarang, dampak masif | Seluruh pesisir Indonesia         | Window evakuasi < 30 menit               |

# **3\. Arsitektur Sistem Multi-Agent**

## **3.1 Overview**

DisasterReady menggunakan arsitektur multi-agent berbasis Python dengan 5 agen spesialis yang dikoordinasikan oleh satu Orchestrator Agent. Seluruh komponen dibangun di atas stack open-source dan gratis - tidak ada biaya API berbayar untuk core AI.

| **Agen**                | **Peran Utama**                                              | **Tool Utama**                      |
| ----------------------- | ------------------------------------------------------------ | ----------------------------------- |
| Orchestrator Agent      | Koordinasi seluruh agen, manajemen task, prioritisasi        | CrewAI (gratis)                     |
| Monitor Agent           | Polling data BMKG & BNPB secara berkala                      | requests + BMKG Open API            |
| Early Warning Agent     | Notifikasi proaktif ke warga sebelum bencana                 | Telegram Bot API (gratis)           |
| Prediction Agent        | Memetakan wilayah berisiko dari data & topografi             | GeoPandas + scikit-learn            |
| Allocation Agent        | Optimasi distribusi bantuan ke relawan terdekat              | OpenRouteService API (gratis)       |
| Communication Agent     | Generate laporan & pesan kontekstual via LLM gratis          | Groq API (Llama 3, gratis)          |
| Post-Disaster Agent *(opsional)* | Evaluasi akurasi prediksi pasca-bencana & update threshold model | SQLite + scikit-learn retrain |

## **3.2 Alur Early Warning Agent**

Berikut alur kerja step-by-step fitur unggulan DisasterReady:

| **#** | **Langkah**                                                                                         | **Agen**            | **Output**               |
| ----- | --------------------------------------------------------------------------------------------------- | ------------------- | ------------------------ |
| 1     | Monitor BMKG API polling setiap 5 menit - deteksi status Siaga/Waspada                              | Monitor Agent       | Alert + data wilayah     |
| 2     | Orchestrator mendistribusikan trigger ke agen relevan                                               | Orchestrator        | Task dispatch            |
| 3     | GeoJSON overlay: koordinat GPS warga vs zona risiko + peta banjir historis BNPB                     | Early Warning Agent | Daftar warga terdampak   |
| 4     | Vulnerability Score dihitung: usia + kondisi + jarak bahaya (data BPS)                              | Early Warning Agent | Skor prioritas per warga |
| 5     | OpenRouteService (ORS) menghitung jalur evakuasi teraman ke titik kumpul terdekat                   | Allocation Agent    | Rute Evakuasi Aman       |
| 6     | Groq/Llama 3 generate pesan personal kontekstual per warga, termasuk instruksi jalur evakuasi       | Communication Agent | Pesan notifikasi         |
| 7     | Notifikasi via Telegram Bot - kelompok rentan mendapat notifikasi pertama                           | Early Warning Agent | Pesan terkirim           |
| 7a    | Jika Telegram gagal delivered dalam 2 menit → eskalasi ke WhatsApp via Fonnte                      | Early Warning Agent | Delivery confirmation    |
| 7b    | Jika WhatsApp gagal → SMS via ZenzVA (kelompok rentan only)                                        | Early Warning Agent | SMS sent log             |
| 8     | Semua aksi dicatat di SQLite audit log untuk transparansi                                           | Backend             | Audit trail lengkap      |

_Contoh Pesan Notifikasi: "Halo Ibu Siti (Kec. Bogor Tengah). BMKG mengeluarkan peringatan Siaga banjir untuk wilayah Anda. Perkiraan hujan sangat lebat dalam 6 jam ke depan. Karena Anda terdaftar sebagai lansia, relawan dari Palang Merah terdekat sudah dihubungi. Jalur evakuasi paling aman untuk Anda adalah menuju titik kumpul di Balai Desa melalui Jl. Sudirman (hindari Jl. Mawar karena potensi genangan). Langkah yang disarankan: (1) Siapkan tas darurat, (2) Segera menuju titik kumpul melalui jalur evakuasi."_

# **4\. Stack Teknologi (Sederhana & Gratis)**

_Filosofi: Maksimalkan dampak dengan tools gratis dan open-source. Tidak perlu API berbayar untuk membangun sistem yang powerful._

## **4.1 AI & LLM (Gratis)**

| **Komponen**            | **Tool / Layanan**                                                | **Kenapa Dipilih**                                                                      |
| ----------------------- | ----------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| Orkestrasi Multi-Agent  | CrewAI (open-source, gratis)                                      | Framework ringan untuk multi-agent, komunitas aktif, dokumentasi lengkap                |
| LLM untuk Generate Teks | Groq API + Llama 3.1 8B (gratis tier)                             | Inferensi sangat cepat (<1 detik), free tier 30 req/menit, cukup untuk demo             |
| Fallback LLM            | Ollama + Llama 3.2 (lokal)                                        | 100% offline, tidak ada limit, cocok untuk simulasi tanpa internet                      |
| Model Prediksi          | scikit-learn (rule-based + **Random Forest + confidence scoring**) | Lebih akurat untuk multi-feature (hujan + topografi + historis); confidence score transparan |

## **4.2 Notifikasi & Komunikasi (Gratis)**

| **Channel**         | **Tool**                     | **Limit Gratis**          | **Catatan**                                         |
| ------------------- | ---------------------------- | ------------------------- | --------------------------------------------------- |
| Notifikasi utama    | Telegram Bot API             | Tidak ada limit!          | Gratis selamanya, mudah setup, tidak butuh approval |
| Notifikasi fallback | WhatsApp via Fonnte (gratis) | 50 pesan/hari (free tier) | Untuk demo; cukup untuk simulasi skala kecil        |
| SMS fallback        | ZenzVA / Watzap (lokal)      | Trial gratis              | Alternatif lokal yang terjangkau                    |

## **4.3 Data, Backend & Infrastruktur (Gratis)**

| **Komponen**          | **Tool**                                             | **Keterangan**                                                                     |
| --------------------- | ---------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Backend API           | FastAPI (Python)                                     | Gratis, open-source, performa tinggi                                               |
| Database              | SQLite (development) / Supabase free tier (produksi) | SQLite untuk lokal, Supabase 500MB gratis untuk cloud                              |
| Peta & GIS            | GeoPandas + Folium + OpenRouteService API            | Semua gratis; ORS free tier 2.000 req/hari                                         |
| Dashboard Visualisasi | **FastAPI + HTML/JS Dashboard** (gratis)             | Custom web dashboard dengan Leaflet.js + Chart.js; lebih fleksibel dari Streamlit  |
| Data Cuaca            | BMKG Open API (resmi & gratis)                       | data.bmkg.go.id - data cuaca, gempa, siaga per wilayah                             |
| Data Historis Bencana | BNPB Open Data / GIS (gratis)                        | gis.bnpb.go.id - data historis untuk training model                                |
| Peta Zona Banjir      | **BNPB Flood Zone Layer (GIS, gratis)**              | Vektor zona banjir historis per kabupaten; input tambahan ke Prediction Agent      |
| Data Demografi        | BPS Open Data (gratis)                               | Lansia per kecamatan untuk vulnerability scoring                                   |
| Data Topografi        | DEMNAS via BIG (gratis)                              | Ketinggian & kemiringan lahan untuk prediksi terdampak                             |

# **5\. Fitur & Requirements**

## **5.1 Fitur Wajib (Must Have)**

| **ID** | **Fitur**                       | **Deskripsi**                                                                                                        | **Prioritas** |
| ------ | ------------------------------- | -------------------------------------------------------------------------------------------------------------------- | ------------- |
| F-01   | Real-time monitoring BMKG       | Polling BMKG API setiap 5 menit, parsing status Waspada/Siaga/Awas per wilayah                                       | P0            |
| F-02   | Early warning notification      | Notifikasi proaktif via Telegram ke warga terdaftar sebelum bencana, berbasis lokasi GPS                             | P0            |
| F-03   | Vulnerability scoring           | Skor kerentanan dari usia, kondisi fisik, jarak zona bahaya (data BPS)                                               | P0            |
| F-04   | Prediksi wilayah terdampak      | Model prediksi risiko banjir/longsor per kecamatan (curah hujan + topografi + peta zona banjir historis BNPB) + confidence score (0-100%) | P0 |
| F-05   | Prioritas kelompok rentan       | Lansia 60+, balita 0-5, difabel - notifikasi pertama + dispatch relawan otomatis                                     | P0            |
| F-06   | Human-in-the-loop               | Distribusi bantuan fisik wajib konfirmasi koordinator sebelum eksekusi                                               | P0            |
| F-07   | GIS routing & Evakuasi          | Optimasi rute relawan dan penentuan jalur evakuasi teraman untuk warga menuju titik kumpul via ORS                   | P1            |
| F-08   | Laporan situasi otomatis        | Generate laporan narasi via Groq/Llama 3 setiap 30 menit                                                             | P1            |
| F-09   | Dashboard Web Interaktif        | Visualisasi zona risiko, posisi relawan, dan warga rentan di peta interaktif (FastAPI + Leaflet.js + Chart.js)       | P1            |
| F-10   | Audit log                       | Semua keputusan agen tercatat di SQLite untuk transparansi dan akuntabilitas                                         | P1            |

## **5.2 Fitur Opsional (Nice to Have)**

- Chatbot Telegram berbasis Llama 3 untuk warga bertanya status terkini
- Prediksi multi-hazard (banjir + longsor bersamaan)
- Laporan pasca-bencana otomatis untuk BPBD
- Integrasi deep link ke aplikasi Info BMKG
- **(F-11) Self-improvement loop**: Post-Disaster Agent membandingkan prediksi vs kejadian nyata, update threshold model secara otomatis

# **6\. Etika & Prinsip AI Bertanggung Jawab**

## **6.1 Human-in-the-Loop**

| **Aksi**                               | **Otorisasi**                      | **Alasan**                                                      |
| -------------------------------------- | ---------------------------------- | --------------------------------------------------------------- |
| Monitoring & deteksi anomali           | Otonom penuh                       | Latensi rendah kritis; tidak ada risiko harm                    |
| Notifikasi early warning ke warga      | Otonom penuh                       | Makin cepat makin baik; pesan informatif, bukan instruksi paksa |
| Prediksi & pembuatan peta risiko       | Otonom penuh                       | Output adalah informasi, bukan keputusan final                  |
| Dispatch relawan untuk kelompok rentan | Otonom (notifikasi ke koordinator) | Urgency tinggi; koordinator dapat override                      |
| Distribusi bantuan fisik               | Wajib konfirmasi koordinator       | Menyangkut sumber daya nyata dan keselamatan jiwa               |
| Override atau halt seluruh sistem      | Hanya koordinator senior BPBD      | Failsafe mutlak                                                 |

## **6.2 Transparansi & Akuntabilitas**

- Setiap keputusan agen dicatat di SQLite audit log: siapa yang trigger, agen mana yang bertindak, data apa yang digunakan, waktu eksekusi, dan hasilnya
- Communication Agent selalu menyertakan alasan di laporan: "Kecamatan X diprioritaskan karena curah hujan 285mm/hari + 34% populasi lansia (sumber: BPS 2023)"
- Vulnerability score dihitung dari data publik BPS yang dapat diverifikasi - bukan black box

## **6.3 Fairness & Inklusivitas**

- Model tidak menggunakan variabel diskriminatif (ras, agama, status ekonomi)
- Kelompok rentan mendapat notifikasi lebih awal, bukan lebih lambat
- Pesan notifikasi dalam Bahasa Indonesia sederhana dan mudah dipahami
- Telegram gratis tersedia untuk semua warga dengan smartphone tanpa biaya tambahan

## **6.4 Keamanan Data**

- Data koordinat warga dienkripsi at-rest dan in-transit
- Tidak ada data sensitif yang dikirim ke model eksternal - hanya konteks situasi bencana
- Warga dapat opt-out dari sistem notifikasi kapan saja
- Model LLM (Llama 3 via Groq) memiliki data privacy policy yang jelas; alternatif Ollama lokal sepenuhnya offline

## **6.5 Graceful Degradation**

Sistem dirancang untuk tetap berfungsi secara minimal bahkan saat komponen utama mengalami gangguan:

| **Komponen Gagal**       | **Perilaku Fallback**                                                              |
| ------------------------ | ---------------------------------------------------------------------------------- |
| Groq API down            | Fallback ke template pesan statis (pre-written) tanpa LLM generation              |
| ORS routing down         | Dispatch relawan berdasarkan radius terdekat tanpa rute optimal                    |
| BMKG API timeout         | Retry 3x dengan exponential backoff; alert ke koordinator jika gagal total         |
| Telegram delivery gagal  | Eskalasi ke WhatsApp (2 menit) → SMS via ZenzVA (kelompok rentan only)             |
| SQLite corrupt           | In-memory logging sementara + alert darurat ke koordinator                         |

# **7\. Rencana Pengembangan (Scope Lomba)**

| **Fase**                              | **Deliverable**                                                                     | **Durasi** | **PIC**       |
| ------------------------------------- | ----------------------------------------------------------------------------------- | ---------- | ------------- |
| Fase 1: Data & Infrastruktur          | Integrasi BMKG API, setup SQLite, arsitektur agen dasar dengan CrewAI               | Minggu 1-2 | Anggota 1     |
| Fase 2: Monitor + Early Warning Agent | Monitor Agent aktif polling, Early Warning Agent kirim notifikasi Telegram uji coba | Minggu 2-3 | Anggota 1 & 2 |
| Fase 3: Prediction + Allocation Agent | Model prediksi wilayah terdampak (scikit-learn), GIS routing via ORS                | Minggu 3-4 | Anggota 2 & 3 |
| Fase 4: Communication + Dashboard     | Laporan otomatis via Groq/Llama 3, dashboard Streamlit interaktif                   | Minggu 4-5 | Anggota 3     |
| Fase 5: Simulasi & Validasi           | Simulasi skenario banjir Jabodetabek, pengukuran metrik dampak                      | Minggu 5-6 | Seluruh Tim   |
| Fase 6: Dokumentasi & Presentasi      | PRD final, demo video, pitch deck, sitasi API lengkap                               | Minggu 6   | Seluruh Tim   |

## **7.2 Alignment Kriteria Lomba**

| **Kriteria Lomba**                  | **Fitur DisasterReady**                                                       |
| ----------------------------------- | ----------------------------------------------------------------------------- |
| Dampak sosial & lingkungan          | Early warning kelompok rentan, coverage nasional berbasis data BMKG            |
| Inovasi teknologi AI                | Multi-agent otonom, vulnerability scoring berbasis BPS, Random Forest + confidence score |
| Skalabilitas & sustainability       | Zero-cost stack, open-source sepenuhnya, deployable di cloud gratis            |
| Etika & responsible AI              | Human-in-the-loop, audit log lengkap, opt-out warga, fairness tanpa diskriminasi |
| Kelayakan teknis implementasi       | Semua API aktif dan terverifikasi, kode berjalan, skenario demo terukur        |

## **7.1 Skenario Demo (Simulasi Lomba)**

Skenario: Banjir Jabodetabek

Input: BMKG merilis status Siaga banjir untuk 5 kecamatan di Kabupaten Bogor. Curah hujan 290mm/hari terdeteksi.

| **#** | **Kejadian dalam Demo**                                                                  | **Waktu Target** |
| ----- | ---------------------------------------------------------------------------------------- | ---------------- |
| 1     | Monitor Agent mendeteksi status Siaga dari BMKG API                                      | < 5 menit        |
| 2     | Prediction Agent menghasilkan peta risiko 5 kecamatan (ditampilkan di Streamlit)         | < 3 menit        |
| 3     | Early Warning Agent identifikasi 1.240 warga terdampak, 312 lansia prioritas             | < 2 menit        |
| 4     | Allocation Agent menghitung rute jalur evakuasi teraman menuju titik kumpul terdekat untuk warga         | < 3 menit        |
| 5     | Notifikasi Telegram (dengan jalur evakuasi) terkirim: lansia pertama dalam 8 menit, lainnya dalam 15 mnt | < 15 menit total |
| 6     | Allocation Agent mendispatch 47 relawan terdekat dengan rute optimal (ORS) ke titik evakuasi kelompok    | < 5 menit        |
| 7     | Communication Agent generate laporan situasi untuk BPBD via Groq/Llama 3                                 | < 1 menit        |

# **8\. Keterbatasan & Risiko**

| **Risiko**                                    | **Dampak**                               | **Mitigasi**                                                                            |
| --------------------------------------------- | ---------------------------------------- | --------------------------------------------------------------------------------------- |
| Data warga belum terdaftar secara masif       | Cakupan notifikasi terbatas              | Demo: dataset sintetis berbasis BPS; jangka panjang: kolaborasi dengan kelurahan        |
| Groq API free tier terbatas (30 req/menit)    | Generate pesan lambat saat bencana masif | Batching pesan + fallback ke Ollama lokal yang unlimited                                |
| Akurasi model prediksi terbatas               | False alarm menurunkan kepercayaan       | Random Forest + threshold konservatif; confidence score (0-100%) ditampilkan di dashboard |
| Koneksi internet terbatas di daerah terpencil | Notifikasi tidak sampai                  | Multi-channel escalation: Telegram → WhatsApp → SMS; jangka panjang: sirine komunitas BPBD |
| Data BPS tidak selalu up-to-date per RT/RW    | Vulnerability score kurang akurat        | Gunakan data terakhir tersedia + disclaimer jelas di dashboard interaktif               |
| Model confidence score disalahartikan         | Over-reliance pada prediksi AI           | Confidence score selalu ditampilkan + label penjelasan metodologi di dashboard          |

# **9\. Daftar Istilah (Glossary)**

| **Istilah**         | **Definisi**                                                                                                         |
| ------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Multi-agent system  | Arsitektur di mana beberapa agen AI bekerja kolaboratif, masing-masing dengan peran dan kapabilitas yang terdefinisi |
| Early Warning       | Peringatan dini yang dikirim sebelum bencana terjadi, berbasis prediksi dan data real-time                           |
| Vulnerability Score | Skor numerik kerentanan individu terhadap bencana: usia, kondisi fisik, dan jarak dari zona bahaya                   |
| Human-in-the-loop   | Prinsip desain AI di mana manusia tetap memiliki kontrol dan otorisasi akhir atas keputusan kritis                   |
| GIS Routing         | Teknologi penentuan rute optimal menggunakan data geografis dan peta jalan                                           |
| GeoJSON             | Format standar untuk representasi data geografis (titik, area, rute) yang dapat diproses sistem GIS                  |
| Last mile delivery  | Lapisan terakhir dalam rantai distribusi informasi - dari sistem ke penerima individu                                |
| CrewAI              | Framework open-source Python untuk membangun sistem multi-agent kolaboratif tanpa biaya lisensi                      |
| Groq API            | Layanan inferensi LLM berbasis cloud dengan free tier yang menggunakan model Llama 3 Meta                            |
| Ollama              | Runtime LLM lokal yang memungkinkan menjalankan model seperti Llama 3 tanpa koneksi internet dan tanpa biaya         |

**Pernyataan Penutup**

_DisasterReady dirancang bukan untuk menggantikan sistem yang sudah ada, melainkan untuk menjembatani gap yang nyata: data early warning sudah tersedia di BMKG, namun belum sampai ke tangan warga yang paling membutuhkan. Dengan pendekatan multi-agent otonom yang dibangun sepenuhnya dari tools gratis dan open-source - DisasterReady membuktikan bahwa dampak nyata tidak harus bergantung pada anggaran besar._