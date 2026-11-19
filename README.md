# 🛡️ JagaRuang-IoT
> **Sistem Keamanan & Monitoring Ruangan Pintar Berbasis IoT, Verifikasi AI (YOLOv8), dan Notifikasi WhatsApp**

---

## 📖 Tentang Proyek

Sensor gerak konvensional (seperti PIR) sering menghasilkan **alarm palsu (*false alarm*)** karena mendeteksi hembusan angin, tirai bergoyang, atau perubahan suhu. 

**JagaRuang** memecahkan masalah ini dengan sistem **dua lapis verifikasi**:
1. **Lapis 1 (IoT):** Sensor PIR mendeteksi adanya pergerakan di ruangan dan memerintahkan ESP32-CAM mengambil gambar.
2. **Lapis 2 (AI Computer Vision):** Server memverifikasi foto tersebut menggunakan model **YOLOv8**. Hanya jika terdeteksi **manusia (*person*)**, alarm (buzzer), lampu ruangan, dan pesan darurat WhatsApp berisi foto pelaku akan langsung dikirim ke ponsel Anda.

---

## ✨ Fitur Utama

- 👁️ **Verifikasi AI Anti-False Alarm (YOLOv8 Nano):** Menyaring alarm palsu secara otomatis dan memberi kotak pembatas (*bounding box*) pada objek yang terdeteksi.
- 📱 **Notifikasi WhatsApp Otomatis (Fonnte):** Mengirim peringatan darurat seketika beserta bukti foto tangkapan kamera ke nomor WhatsApp Anda.
- 🚨 **Sistem Alarm & Otomasi Lampu:** Mengaktifkan buzzer darurat dan relay lampu ruangan otomatis saat penyusup terdeteksi.
- 📊 **Dashboard Web Real-time:** 
  - Status koneksi alat (*Online / Offline*).
  - Grafik riwayat suhu & kelembapan (Sensor DHT).
  - Indikator intensitas cahaya (Sensor LDR).
  - Galeri riwayat foto tangkapan kejadian terbaru.
  - Kontrol saklar manual (Mode Siaga/Armed, Lampu, dan Reset Alarm).
- 📶 **Mode Cadangan Wi-Fi CSI (Rp0):** Verifikasi cadangan berbasis gangguan sinyal Wi-Fi jika kamera tidak aktif/rusak.

---

## 🛠️ Kebutuhan Sistem

### Perangkat Keras (Hardware):
- **ESP32 DevKit** (Mikrokontroler Utama)
- **ESP32-CAM** (Kamera Pengambil Gambar)
- **Sensor PIR** (Deteksi Gerakan)
- **Sensor DHT11 / DHT22** (Monitoring Suhu & Kelembapan)
- **Sensor LDR** (Sensor Cahaya)
- **Modul Relay 5V** (Kontrol Lampu Ruangan)
- **Buzzer Aktif 5V** (Suara Alarm)

### Perangkat Lunak (Software):
- **Python 3.10+ / 3.11**
- **FastAPI** & **Uvicorn** (Backend Server & API)
- **Ultralytics YOLOv8** (Model Computer Vision)
- **OpenCV** (Pengolah Gambar)
- **SQLite** (Penyimpanan Riwayat Kejadian & Sensor)
- **Akun Fonnte** (Gateway API WhatsApp)

---

## 🚀 Panduan Instalasi & Menjalankan

### 1. Clone Repositori
```bash
git clone https://github.com/G-than12/JagaRuang-Iot.git
cd JagaRuang-Iot
```

### 2. Install Dependensi Python
Pastikan Python sudah terpasang, lalu jalankan:
```bash
pip install -r requirements.txt
```

### 3. Konfigurasi WhatsApp (Fonnte)
Buka file `main.py`, lalu sesuaikan baris 20-21 dengan token Fonnte dan nomor WhatsApp Anda:
```python
FONNTE_TOKEN = "MASUKKAN_TOKEN_FONNTE_ANDA"
NOMOR_WA_TUJUAN = "081234567890"  # Nomor WhatsApp penerima notifikasi
```
*(Token gratis bisa didapatkan di situs [fonnte.com](https://fonnte.com))*.

### 4. Jalankan Server
Jalankan server backend menggunakan Uvicorn:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
> Atau melalui Python launcher di Windows:  
> `py -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload`

### 5. Buka Dashboard Web
Akses antarmuka dashboard monitoring melalui browser Anda:
```text
http://localhost:8000
```
*(Jika ingin diakses dari HP di jaringan Wi-Fi yang sama, gunakan alamat IP laptop Anda, misal: `http://192.168.1.100:8000`)*.

---

## 🔌 Dokumentasi Endpoint API

Server FastAPI menyediakan endpoint berikut untuk komunikasi dengan mikrokontroler ESP32:

| Metode | Endpoint | Deskripsi |
|---|---|---|
| `GET` | `/` | Menampilkan halaman antarmuka Web Dashboard |
| `POST` | `/api/sensor` | Menerima data sensor berkala dari ESP32 (suhu, kelembapan, LDR, PIR) |
| `POST` | `/api/detect` | Menerima kiriman foto dari ESP32-CAM untuk diverifikasi oleh AI YOLOv8 |
| `GET` | `/api/state` | Endpoint polling untuk ESP32 membaca status aktuator (Buzzer & Lampu) |
| `POST` | `/api/control` | Menerima aksi tombol dari web (Armed, Saklar Lampu, Reset Alarm) |
| `GET` | `/api/dashboard` | Menyediakan data real-time, statistik reduksi false alarm, dan grafik untuk web |

---

## 📁 Struktur Direktori

```text
jagaruang/
├── captures/           # Folder penyimpanan foto hasil tangkapan AI
├── templates/
│   └── index.html      # Tampilan Dashboard Web (TailwindCSS + Chart.js)
├── .gitignore          # File penyaring git agar database & cache tidak terupload
├── main.py             # Server Utama FastAPI + Logika AI & WhatsApp
├── requirements.txt    # Daftar dependensi library Python
├── yolov8n.pt          # Model bobot AI YOLOv8 Nano
└── README.md           # Panduan proyek
```

---

## 👤 Pengembang
- **Nama:** Gathan Hilabi
- **NIM:** 24059
- **Email:** gathan.hilabi24059@mhs.uingusdur.ac.id
- **GitHub:** [@G-than12](https://github.com/G-than12)
