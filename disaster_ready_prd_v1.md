PRODUCT REQUIREMENTS DOCUMENT

**DisasterReady**

Koordinator Respons Bencana Otonom dengan Early Warning

| **Versi**    | 1.0 (Submission Lomba)                             |
| ------------ | -------------------------------------------------- |
| **Kategori** | Mahasiswa/i - AI for Environmental & Social Impact |
| **Status**   | Draft Final                                        |
| **Tanggal**  | April 2026                                         |

# **1\. Ringkasan Eksekutif**

**Problem Statement**

Indonesia adalah negara dengan frekuensi bencana alam tertinggi ke-5 di dunia. Sepanjang 2024, BNPB mencatat 1.942 kejadian bencana yang berdampak pada lebih dari 5,64 juta jiwa. Sistem peringatan dini sudah ada (BMKG), namun "last mile delivery" - notifikasi proaktif ke warga individual, terutama kelompok rentan - masih belum merata dan terfragmentasi.

**Solusi: DisasterReady**

Sistem multi-agent otonom yang (1) memantau data BMKG/BNPB secara real-time, (2) memprediksi wilayah berisiko sebelum bencana terjadi, (3) mengirim notifikasi proaktif ke warga berdasarkan lokasi dan kerentanan, serta (4) mengkoordinasikan distribusi bantuan ke relawan terdekat - dengan kelompok rentan (lansia, balita, difabel) sebagai prioritas utama.

### **Proposisi Nilai Utama**

- BMKG sudah punya datanya. Warga belum dapat notifikasinya. DisasterReady adalah jembatan itu.
- Bukan sekadar monitoring - sistem ini bertindak otonom untuk menyelamatkan nyawa sebelum bencana tiba.
- Kelompok rentan bukan afterthought - mereka adalah prioritas pertama dalam setiap algoritma alokasi.

### **Dampak Terukur (Target Simulasi)**

| **Metrik**                       | **Baseline (Manual)**           | **Target DisasterReady**              |
| -------------------------------- | ------------------------------- | ------------------------------------- |
| Waktu deteksi anomali cuaca      | 30-60 menit (manual monitoring) | < 5 menit (otomatis)                  |
| Notifikasi warga sebelum bencana | Tidak ada / via medsos BMKG     | Personal, berbasis lokasi, < 10 menit |
| Identifikasi kelompok rentan     | Manual, tidak terstruktur       | Otomatis dari data BPS per kecamatan  |
| Waktu koordinasi relawan         | 1-2 jam (telepon manual)        | < 15 menit (dispatch otomatis)        |
| Cakupan daerah terpantau         | Tergantung petugas BPBD         | Real-time, seluruh wilayah terdaftar  |

# **2\. Latar Belakang & Konteks**

## **2.1 Kondisi Kebencanaan Indonesia**

Indonesia berada di "Ring of Fire" dan pertemuan tiga lempeng tektonik, menjadikannya salah satu negara paling rawan bencana di dunia. Ancaman bersifat multi-hazard: banjir, tanah longsor, gempa bumi, tsunami, dan erupsi gunung api kerap terjadi bersamaan atau saling memicu.

| **Jenis Bencana** | **Frekuensi (2024)** | **Wilayah Utama**                 | **Karakteristik**                              |
| ----------------- | -------------------- | --------------------------------- | ---------------------------------------------- |
| Banjir            | ~800 kejadian/tahun  | Jabodetabek, Kalimantan, Sulawesi | Dapat diprediksi 6-24 jam sebelumnya           |
| Tanah Longsor     | ~400 kejadian/tahun  | Jawa Barat, Sumatra, Sulawesi     | Dipicu curah hujan ekstrem                     |
| Gempa Bumi        | Ratusan/tahun        | Sulawesi, NTB, Jawa Barat         | Sulit diprediksi kapan, lokasi dapat dipetakan |
| Tsunami           | Jarang, dampak masif | Seluruh pesisir Indonesia         | Window evakuasi < 30 menit                     |

## **2.2 Gap yang DisasterReady Isi**

Infrastruktur early warning Indonesia sudah berkembang - BMKG memiliki InaTEWS, INA-EEWS, dan rutin merilis status Siaga/Waspada. Namun masalah utama ada di lapisan terakhir:

- Diseminasi masih satu arah dan pasif (warga harus aktif cek website/medsos BMKG)
- Tidak ada personalisasi berbasis lokasi warga individual
- Kelompok rentan (lansia, balita, difabel) tidak mendapat perlakuan prioritas dalam sistem notifikasi
- Koordinasi relawan masih manual, lambat, dan bergantung pada kontak personal BPBD

# **3\. Tujuan Produk**

## **3.1 Tujuan Utama**

- Menjembatani data early warning BMKG dengan notifikasi proaktif ke warga sebelum bencana terjadi
- Mengotomasikan koordinasi relawan dan distribusi bantuan berbasis GIS routing
- Memastikan kelompok rentan (lansia 60+, balita 0-5, penyandang difabel) menjadi prioritas pertama
- Mengintegrasikan prinsip etika AI: transparansi, akuntabilitas, dan human-in-the-loop

## **3.2 Yang Bukan Tujuan Produk Ini**

- Menggantikan sistem BMKG yang sudah ada - DisasterReady adalah lapisan aplikasi di atasnya
- Memprediksi gempa bumi (bukan dalam scope - fokus pada banjir dan longsor yang dapat diprediksi secara hidrometeorologi)
- Deployment ke produksi penuh - scope lomba adalah prototype dan simulasi tervalidasi

# **4\. Arsitektur Sistem Multi-Agent**

## **4.1 Overview Arsitektur**

DisasterReady menggunakan arsitektur multi-agent berbasis AutoGen dengan 5 agen spesialis yang dikoordinasikan oleh satu Orchestrator Agent. Setiap agen memiliki domain, tool, dan akses data yang terdefinisi jelas.

| **Agen**            | **Peran Utama**                                         | **Input**                            | **Output**                          | **Tool Utama**                |
| ------------------- | ------------------------------------------------------- | ------------------------------------ | ----------------------------------- | ----------------------------- |
| Orchestrator Agent  | Koordinasi seluruh agen, manajemen task, prioritisasi   | Trigger dari Monitor Agent           | Task dispatch ke agen lain          | AutoGen GroupChat             |
| Monitor Agent       | Polling data BMKG & BNPB secara berkala                 | BMKG API, BNPB RSS                   | Alert jika anomali terdeteksi       | requests, BMKG API            |
| Early Warning Agent | Notifikasi proaktif ke warga sebelum bencana            | Alert dari Monitor, DB warga         | Pesan WA/Telegram/SMS personal      | WhatsApp Business API, Twilio |
| Prediction Agent    | Memetakan wilayah berisiko berdasarkan data & topografi | Data cuaca, DEMNAS, historis BNPB    | Peta risiko per kecamatan (GeoJSON) | GeoPandas, scikit-learn       |
| Allocation Agent    | Optimasi distribusi bantuan ke relawan terdekat         | Peta risiko, DB relawan, data rentan | Assignment relawan + rute optimal   | OpenRouteService API          |
| Communication Agent | Generate laporan situasi dan notifikasi relawan         | Output semua agen                    | Laporan narasi, push notification   | Anthropic Claude API          |

## **4.2 Alur Early Warning Agent (Fitur Unggulan)**

Early Warning Agent adalah diferensiasi utama DisasterReady. Berikut alur kerjanya step by step:

- Monitor Agent mendeteksi status Siaga/Waspada dari BMKG API (polling setiap 5 menit)
- Early Warning Agent menerima trigger dari Orchestrator beserta data wilayah terdampak
- Sistem mencocokkan koordinat GPS warga terdaftar dengan zona risiko (GeoJSON overlay)
- Algoritma kerentanan menghitung Vulnerability Score per warga (usia, kondisi, jarak dari sumber bahaya)
- Communication Agent via Claude API meng-generate pesan personal yang kontekstual per warga
- Notifikasi dikirim via WhatsApp Business API / Telegram Bot / SMS (Twilio) - kelompok rentan mendapat notifikasi pertama
- Semua aksi tercatat di Firebase audit log untuk transparansi dan akuntabilitas

**Contoh Pesan Notifikasi ke Warga**

"Halo Ibu Siti (Kec. Bogor Tengah). BMKG mengeluarkan peringatan Siaga banjir untuk wilayah Anda. Perkiraan hujan sangat lebat dalam 6 jam ke depan. Karena Anda terdaftar sebagai lansia, relawan dari Palang Merah terdekat sudah dihubungi. Langkah yang disarankan: (1) Pindahkan barang berharga ke lantai atas, (2) Siapkan tas darurat, (3) Hubungi 119 jika butuh bantuan. Pantau terus: info.bmkg.go.id"

# **5\. Fitur & Requirements**

## **5.1 Fitur Wajib (Must Have)**

| **ID** | **Fitur**                    | **Deskripsi**                                                                             | **Agen Bertanggung Jawab** | **Prioritas** |
| ------ | ---------------------------- | ----------------------------------------------------------------------------------------- | -------------------------- | ------------- |
| F-01   | Real-time monitoring BMKG    | Polling BMKG API setiap 5 menit, parsing status Waspada/Siaga/Awas per wilayah            | Monitor Agent              | P0            |
| F-02   | Early warning notification   | Notifikasi proaktif ke warga terdaftar sebelum bencana, berbasis lokasi GPS               | Early Warning Agent        | P0            |
| F-03   | Vulnerability scoring        | Hitung skor kerentanan warga berdasarkan usia, kondisi, jarak zona bahaya (data BPS)      | Early Warning Agent        | P0            |
| F-04   | Prediksi wilayah terdampak   | Model prediksi risiko banjir/longsor per kecamatan berdasarkan curah hujan + topografi    | Prediction Agent           | P0            |
| F-05   | Prioritas kelompok rentan    | Lansia 60+, balita 0-5, difabel mendapat notifikasi pertama dan dispatch relawan otomatis | Allocation Agent           | P0            |
| F-06   | GIS routing relawan          | Optimasi penugasan dan rute relawan terdekat ke lokasi terdampak                          | Allocation Agent           | P1            |
| F-07   | Laporan situasi otomatis     | Generate laporan narasi situasi bencana via Claude API setiap 30 menit                    | Communication Agent        | P1            |
| F-08   | Dashboard peta real-time     | Visualisasi zona risiko, posisi relawan, dan warga rentan di peta interaktif              | Backend / Frontend         | P1            |
| F-09   | Audit log seluruh aksi agen  | Semua keputusan agen tercatat di Firebase untuk transparansi                              | Backend (Firebase)         | P1            |
| F-10   | Human-in-the-loop konfirmasi | Distribusi bantuan fisik memerlukan konfirmasi koordinator sebelum eksekusi               | Orchestrator               | P0            |

## **5.2 Fitur Opsional (Nice to Have)**

- Integrasi dengan aplikasi Info BMKG yang sudah ada (deep link)
- Chatbot berbasis Claude API untuk warga bertanya status terkini
- Prediksi multi-hazard (banjir + longsor bersamaan)
- Laporan pasca-bencana otomatis untuk BPBD

# **6\. Stack Teknologi & Sitasi API**

## **6.1 Sumber Data Publik**

| **Sumber Data**            | **Penyedia / Organisasi**                            | **URL / Dokumentasi**            | **Penggunaan dalam Sistem**                                                          |
| -------------------------- | ---------------------------------------------------- | -------------------------------- | ------------------------------------------------------------------------------------ |
| BMKG Open API              | Badan Meteorologi, Klimatologi, dan Geofisika (BMKG) | data.bmkg.go.id / bmkg.go.id/api | Monitoring cuaca real-time, status Siaga/Waspada, data gempa dan curah hujan         |
| BNPB Open Data / GIS       | Badan Nasional Penanggulangan Bencana (BNPB)         | gis.bnpb.go.id                   | Data historis kejadian bencana per wilayah untuk training model prediksi             |
| Data BPS (Demografi)       | Badan Pusat Statistik (BPS)                          | bps.go.id                        | Data lansia per kecamatan, demografi kelompok rentan untuk vulnerability scoring     |
| DEMNAS (Topografi)         | Badan Informasi Geospasial (BIG)                     | tanahair.indonesia.go.id         | Data ketinggian dan kemiringan lahan untuk prediksi wilayah terdampak banjir/longsor |
| OpenStreetMap (Peta Jalan) | OpenStreetMap Contributors                           | openstreetmap.org                | Peta jalan untuk GIS routing relawan ke lokasi terdampak                             |

## **6.2 Framework & Library**

| **Framework / Library**    | **Penyedia**                  | **Versi**                | **Penggunaan**                                                          |
| -------------------------- | ----------------------------- | ------------------------ | ----------------------------------------------------------------------- |
| AutoGen                    | Microsoft Research            | 0.4.x                    | Orkestrasi multi-agent, GroupChat coordination antar agen spesialis     |
| Anthropic Claude API       | Anthropic, PBC                | claude-sonnet-4-20250514 | Generate laporan situasi otomatis, personalisasi pesan notifikasi warga |
| FastAPI                    | Tiangolo / Sebastián Ramírez  | 0.110+                   | Backend REST API untuk orkestrasi sistem dan endpoint webhook           |
| Firebase Realtime Database | Google LLC                    | Firebase SDK 9+          | Realtime state management: data bencana aktif, relawan, warga terdaftar |
| GeoPandas                  | GeoPandas Contributors        | 0.14+                    | Spatial join koordinat warga dengan zona risiko (GeoJSON overlay)       |
| OpenRouteService API       | HeiGIT / Heidelberg Institute | v2                       | GIS routing dan optimasi rute relawan ke lokasi terdampak               |
| WhatsApp Business API      | Meta Platforms, Inc.          | Cloud API v18+           | Pengiriman notifikasi early warning ke nomor WhatsApp warga terdaftar   |
| Twilio SMS API             | Twilio Inc.                   | REST API v2              | Fallback notifikasi via SMS untuk warga tanpa WhatsApp                  |
| scikit-learn               | scikit-learn Contributors     | 1.4+                     | Model prediksi wilayah terdampak (logistic regression + rule-based)     |
| Python                     | Python Software Foundation    | 3.11+                    | Bahasa pemrograman utama seluruh backend dan agen                       |

# **7\. Etika & Prinsip AI Bertanggung Jawab**

## **7.1 Human-in-the-Loop**

DisasterReady dirancang dengan prinsip bahwa AI adalah alat bantu, bukan pengganti keputusan manusia dalam situasi krisis. Pembagian otorisasi:

| **Aksi**                                      | **Otorisasi**                             | **Alasan**                                                               |
| --------------------------------------------- | ----------------------------------------- | ------------------------------------------------------------------------ |
| Monitoring & deteksi anomali                  | Otonom penuh                              | Latensi rendah kritis; tidak ada risiko harm                             |
| Notifikasi early warning ke warga             | Otonom penuh                              | Makin cepat makin baik; pesan informatif, bukan instruksi evakuasi paksa |
| Prediksi & pembuatan peta risiko              | Otonom penuh                              | Output adalah informasi, bukan keputusan final                           |
| Dispatch relawan untuk kelompok rentan        | Otonom (dengan notifikasi ke koordinator) | Urgency tinggi; koordinator dapat override                               |
| Distribusi bantuan fisik (logistik, evakuasi) | Wajib konfirmasi koordinator              | Menyangkut sumber daya nyata dan keselamatan jiwa                        |
| Override atau halt seluruh sistem             | Hanya koordinator senior BPBD             | Failsafe mutlak                                                          |

## **7.2 Transparansi & Akuntabilitas**

- Setiap keputusan agen dicatat di Firebase audit log: siapa yang trigger, agen mana yang bertindak, data apa yang digunakan, waktu eksekusi, dan hasilnya
- Communication Agent selalu menyertakan alasan di laporan: 'Kecamatan X diprioritaskan karena curah hujan 285mm/hari + 34% populasi lansia (sumber: BPS 2023)'
- Vulnerability score dihitung dari data publik BPS yang dapat diverifikasi - bukan black box

## **7.3 Fairness & Inklusivitas**

- Model tidak menggunakan variabel yang berpotensi diskriminatif (ras, agama, status ekonomi)
- Kelompok rentan mendapat notifikasi lebih awal, bukan lebih lambat
- Pesan notifikasi dirancang dalam Bahasa Indonesia yang sederhana dan mudah dipahami
- Fallback SMS tersedia untuk warga tanpa smartphone atau koneksi internet

## **7.4 Keamanan Data**

- Data koordinat warga dienkripsi at-rest dan in-transit
- Tidak ada data sensitif yang dikirim ke model eksternal - hanya konteks situasi bencana
- Warga dapat opt-out dari sistem notifikasi kapan saja

# **8\. Rencana Pengembangan (Scope Lomba)**

## **8.1 Milestone**

| **Fase**                              | **Deliverable**                                                            | **Durasi** | **Penanggung Jawab** |
| ------------------------------------- | -------------------------------------------------------------------------- | ---------- | -------------------- |
| Fase 1: Data & Infrastruktur          | Integrasi BMKG API, setup Firebase, arsitektur agen dasar                  | Minggu 1-2 | Anggota 1 (Backend)  |
| Fase 2: Monitor + Early Warning Agent | Monitor Agent aktif polling, Early Warning Agent kirim notifikasi uji coba | Minggu 2-3 | Anggota 1 & 2        |
| Fase 3: Prediction + Allocation Agent | Model prediksi wilayah terdampak, GIS routing relawan                      | Minggu 3-4 | Anggota 2 & 3        |
| Fase 4: Communication + Dashboard     | Laporan otomatis via Claude API, dashboard peta interaktif                 | Minggu 4-5 | Anggota 3            |
| Fase 5: Simulasi & Validasi           | Simulasi skenario banjir Jabodetabek, pengukuran metrik dampak             | Minggu 5-6 | Seluruh Tim          |
| Fase 6: Dokumentasi & Presentasi      | PRD final, demo video, pitch deck, sitasi API lengkap                      | Minggu 6   | Seluruh Tim          |

## **8.2 Skenario Demo (Simulasi Lomba)**

**Skenario: Banjir Jabodetabek**

Input: BMKG merilis status Siaga banjir untuk 5 kecamatan di Kabupaten Bogor. Curah hujan 290mm/hari terdeteksi. Alur yang didemonstrasikan: (1) Monitor Agent mendeteksi dalam <5 menit (2) Prediction Agent menghasilkan peta risiko 5 kecamatan (3) Early Warning Agent mengidentifikasi 1.240 warga terdampak, 312 di antaranya lansia prioritas (4) Notifikasi dikirim: lansia pertama dalam 8 menit, seluruh warga dalam 15 menit (5) Allocation Agent mendispatch 47 relawan Palang Merah terdekat (6) Communication Agent generate laporan situasi untuk BPBD dalam Bahasa Indonesia

# **9\. Keterbatasan & Risiko**

| **Risiko**                                    | **Dampak**                               | **Mitigasi**                                                                                        |
| --------------------------------------------- | ---------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Data warga belum terdaftar secara masif       | Cakupan notifikasi terbatas              | Untuk demo: gunakan dataset sintetis berbasis data BPS; jangka panjang: kolaborasi dengan kelurahan |
| Akurasi model prediksi terbatas               | False alarm dapat menurunkan kepercayaan | Gunakan threshold konservatif; tampilkan confidence score di setiap prediksi                        |
| Keterbatasan WhatsApp Business API (volume)   | Notifikasi massal butuh approval Meta    | Untuk demo: Telegram Bot tidak memiliki limit; SMS via Twilio sebagai fallback                      |
| Koneksi internet terbatas di daerah terpencil | Notifikasi tidak sampai                  | SMS fallback; jangka panjang: integrasi dengan sirine komunitas BPBD                                |
| Data BPS tidak selalu up-to-date per RT/RW    | Vulnerability score kurang akurat        | Gunakan data terakhir yang tersedia + disclaimer di dashboard                                       |

# **10\. Daftar Istilah (Glossary)**

| **Istilah**         | **Definisi**                                                                                                                                |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Multi-agent system  | Arsitektur di mana beberapa agen AI bekerja secara kolaboratif, masing-masing dengan peran dan kapabilitas yang terdefinisi                 |
| Early Warning       | Peringatan dini yang dikirim sebelum bencana terjadi, berbasis prediksi dan data real-time                                                  |
| Vulnerability Score | Skor numerik yang menggambarkan tingkat kerentanan individu terhadap bencana, dihitung dari usia, kondisi fisik, dan jarak dari zona bahaya |
| Human-in-the-loop   | Prinsip desain AI di mana manusia tetap memiliki kontrol dan otorisasi akhir atas keputusan kritis                                          |
| GIS Routing         | Teknologi penentuan rute optimal menggunakan data geografis dan peta jalan                                                                  |
| GeoJSON             | Format standar untuk representasi data geografis (titik, area, rute) yang dapat diproses oleh sistem GIS                                    |
| Last mile delivery  | Lapisan terakhir dalam rantai distribusi informasi - dari sistem ke penerima individu                                                       |
| Orchestrator Agent  | Agen yang mengkoordinasikan agen-agen lain, mendistribusikan task, dan mengelola alur kerja keseluruhan sistem                              |

**Pernyataan Penutup**

DisasterReady dirancang bukan untuk menggantikan sistem yang sudah ada, melainkan untuk menjembatani gap yang nyata: data early warning sudah tersedia di BMKG, namun belum sampai ke tangan warga yang paling membutuhkan. Dengan pendekatan multi-agent yang otonom, bertanggung jawab, dan berpusat pada kelompok rentan - DisasterReady berambisi menjadi lapisan aplikasi yang menyelamatkan nyawa sebelum bencana tiba.