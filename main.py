import os
import time
import sqlite3
from datetime import datetime
from typing import Optional

import cv2
import numpy as np
import requests
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from ultralytics import YOLO

# ==============================================================================
# KONFIGURASI FONNTE (WHATSAPP GATEWAY) & SISTEM
# ==============================================================================
FONNTE_TOKEN = "ISI_TOKEN_FONNTE_KAMU_DI_SINI"
NOMOR_WA_TUJUAN = "081234567890"  # Nomor WA penerima peringatan
WA_COOLDOWN_DETIK = 60            # Jeda minimal antar-notif WA agar tidak spam

CAPTURE_DIR = "captures"
DB_PATH = "jagaruang.db"
os.makedirs(CAPTURE_DIR, exist_ok=True)
os.makedirs("templates", exist_ok=True)

# Muat model YOLOv8 Nano (ringan dan cepat untuk laptop; otomatis download saat pertama run)
model_yolo = YOLO("yolov8n.pt")

app = FastAPI(title="JagaRuang IoT + AI Server")
app.mount("/captures", StaticFiles(directory=CAPTURE_DIR), name="captures")
templates = Jinja2Templates(directory="templates")

# ==============================================================================
# INISIALISASI DATABASE SQLITE (UNTUK RIWAYAT & STATISTIK LAPORAN)
# ==============================================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            category TEXT,
            detail TEXT,
            image_path TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS sensor_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            temperature REAL,
            humidity REAL
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ==============================================================================
# STATE PERANGKAT REAL-TIME DI MEMORI
# ==============================================================================
state = {
    "last_seen": 0.0,               # Timestamp terakhir ESP32 menghubungi server
    "armed": True,                  # Status sistem alarm aktif/nonaktif
    "alarm_active": False,          # Status buzzer menyala/mati
    "lamp_on": False,               # Status relay lampu menyala/mati
    "auto_lamp_ldr": True,          # Otomatis nyalakan lampu saat gelap
    "backup_csi_mode": False,       # Mode cadangan Wi-Fi CSI (jika ESP32-CAM rusak)
    "temperature": 0.0,
    "humidity": 0.0,
    "ldr": 0,
    "is_dark": False,
    "pir_triggered": False,
    "wifi_csi_motion": False,
    "last_wa_sent": 0.0,
    "last_wa_status": "Belum ada peringatan terkirim",
    "latest_image": "",
    "latest_result": "Menunggu pemicu gerakan...",
}

# ==============================================================================
# FUNGSI PENGIRIM NOTIFIKASI WHATSAPP VIA FONNTE (BACKGROUND TASK)
# ==============================================================================
def kirim_notif_wa(image_path: str, jumlah_orang: int, waktu_kejadian: str):
    if FONNTE_TOKEN == "ISI_TOKEN_FONNTE_KAMU_DI_SINI" or not FONNTE_TOKEN:
        state["last_wa_status"] = "Token Fonnte belum diisi"
        return

    url = "https://api.fonnte.com/send"
    headers = {"Authorization": FONNTE_TOKEN}
    pesan = (
        f"🚨 *PERINGATAN KEAMANAN JAGARUANG*\n\n"
        f"Terdeteksi *{jumlah_orang} orang* masuk ke dalam ruangan!\n"
        f"🕒 Waktu: {waktu_kejadian}\n"
        f"🔔 Status: Buzzer & Lampu Ruangan *AKTIF*\n\n"
        f"Buka dashboard JagaRuang untuk mematikan alarm."
    )
    payload = {
        "target": NOMOR_WA_TUJUAN,
        "message": pesan,
    }

    try:
        with open(image_path, "rb") as foto:
            files = {"file": (os.path.basename(image_path), foto, "image/jpeg")}
            resp = requests.post(
                url, headers=headers, data=payload, files=files, timeout=12
            )
        if resp.status_code == 200:
            state["last_wa_status"] = f"Terkirim ke WA ({waktu_kejadian})"
        else:
            state["last_wa_status"] = f"Gagal kirim WA (HTTP {resp.status_code})"
    except Exception as e:
        state["last_wa_status"] = f"Error koneksi Fonnte: {str(e)}"

# ==============================================================================
# MODEL DATA REQUEST API
# ==============================================================================
class SensorPayload(BaseModel):
    temperature: float
    humidity: float
    ldr: int
    is_dark: bool = False
    pir_triggered: bool = False
    wifi_csi_motion: bool = False

class ControlPayload(BaseModel):
    action: str
    value: Optional[bool] = None

# ==============================================================================
# ENDPOINT 1: HALAMAN WEB DASHBOARD
# ==============================================================================
@app.get("/")
async def halaman_dashboard():
    return FileResponse("templates/index.html")

# ==============================================================================
# ENDPOINT 2: TERIMA DATA SENSOR RUTIN DARI ESP32 UTAMA
# ==============================================================================
@app.post("/api/sensor")
async def terima_data_sensor(data: SensorPayload):
    now = time.time()
    waktu_str = datetime.now().strftime("%H:%M:%S")
    waktu_full = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    state["last_seen"] = now
    state["temperature"] = round(data.temperature, 1)
    state["humidity"] = round(data.humidity, 1)
    state["ldr"] = data.ldr
    state["is_dark"] = data.is_dark
    state["pir_triggered"] = data.pir_triggered
    state["wifi_csi_motion"] = data.wifi_csi_motion

    # Simpan riwayat suhu & kelembapan untuk grafik
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO sensor_logs (timestamp, temperature, humidity) VALUES (?, ?, ?)",
        (waktu_str, state["temperature"], state["humidity"]),
    )
    conn.commit()

    # Logika Mode Cadangan Rp0 (Wi-Fi CSI vs PIR saat ESP32-CAM tidak dipakai)
    if state["backup_csi_mode"] and data.pir_triggered:
        if data.wifi_csi_motion:
            c.execute(
                "INSERT INTO events (timestamp, category, detail, image_path) VALUES (?, ?, ?, ?)",
                (waktu_full, "ORANG TERDETEKSI", "Mode Cadangan: PIR + Gangguan Sinyal Wi-Fi CSI", ""),
            )
            if state["armed"]:
                state["alarm_active"] = True
                state["lamp_on"] = True
        else:
            c.execute(
                "INSERT INTO events (timestamp, category, detail, image_path) VALUES (?, ?, ?, ?)",
                (waktu_full, "ALARM PALSU PIR", "Mode Cadangan: PIR aktif tapi sinyal Wi-Fi CSI stabil", ""),
            )
        conn.commit()

    conn.close()
    return {"status": "ok"}

# ==============================================================================
# ENDPOINT 3: PERINTAH AKTUATOR UNTUK DIBACA ESP32 UTAMA (POLLING)
# ==============================================================================
@app.get("/api/state")
async def kirim_perintah_esp32():
    state["last_seen"] = time.time()
    return {
        "armed": 1 if state["armed"] else 0,
        "alarm_active": 1 if state["alarm_active"] else 0,
        "lamp_on": 1 if state["lamp_on"] else 0,
        "auto_lamp_ldr": 1 if state["auto_lamp_ldr"] else 0,
        "backup_csi_mode": 1 if state["backup_csi_mode"] else 0,
    }

# ==============================================================================
# ENDPOINT 4: TERIMA FOTO DARI ESP32-CAM & VERIFIKASI AI YOLOv8
# ==============================================================================
@app.post("/api/detect")
async def verifikasi_foto_yolo(request: Request, background_tasks: BackgroundTasks):
    state["last_seen"] = time.time()

    # Mendukung pengiriman raw JPEG bytes langsung dari ESP32-CAM maupun multipart form
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        upload_file = form.get("file") or form.get("image")
        img_bytes = await upload_file.read()
    else:
        img_bytes = await request.body()

    if not img_bytes:
        return JSONResponse(status_code=400, content={"error": "Data gambar kosong"})

    # Decode gambar JPEG ke format OpenCV
    np_arr = np.frombuffer(img_bytes, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if frame is None:
        return JSONResponse(status_code=400, content={"error": "Format JPEG tidak valid"})

    # Jalankan inferensi AI YOLOv8
    results = model_yolo(frame, conf=0.45, verbose=False)
    jumlah_orang = 0
    objek_lain = []

    for r in results:
        for box in r.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            label_nama = model_yolo.names[cls_id]
            x1, y1, x2, y2 = map(int, box.xyxy[0])

            if label_nama == "person":
                jumlah_orang += 1
                warna = (0, 0, 255)  # Merah untuk orang
            else:
                objek_lain.append(f"{label_nama} ({int(conf*100)}%)")
                warna = (0, 200, 255)  # Kuning untuk non-orang (kucing, dll)

            # Gambar bounding box pada foto
            cv2.rectangle(frame, (x1, y1), (x2, y2), warna, 2)
            cv2.putText(
                frame,
                f"{label_nama} {int(conf*100)}%",
                (x1, max(y1 - 8, 15)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                warna,
                2,
            )

    # Simpan hasil gambar ber-bounding box
    nama_file = f"event_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    path_simpan = os.path.join(CAPTURE_DIR, nama_file)
    cv2.imwrite(path_simpan, frame)
    url_foto = f"/captures/{nama_file}"

    waktu_full = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    if jumlah_orang > 0:
        detail_teks = f"AI Verifikasi: Terdeteksi {jumlah_orang} orang"
        c.execute(
            "INSERT INTO events (timestamp, category, detail, image_path) VALUES (?, ?, ?, ?)",
            (waktu_full, "ORANG TERDETEKSI", detail_teks, url_foto),
        )
        state["latest_image"] = url_foto
        state["latest_result"] = f"ORANG TERDETEKSI ({jumlah_orang} orang)"

        if state["armed"]:
            state["alarm_active"] = True
            state["lamp_on"] = True

            # Kirim notifikasi WhatsApp via Fonnte dengan jeda anti-spam
            if (time.time() - state["last_wa_sent"]) >= WA_COOLDOWN_DETIK:
                state["last_wa_sent"] = time.time()
                background_tasks.add_task(kirim_notif_wa, path_simpan, jumlah_orang, waktu_full)
    else:
        keterangan_lain = ", ".join(set(objek_lain)) if objek_lain else "Tidak ada orang (gorden/panas/bayangan)"
        detail_teks = f"Alarm Palsu PIR disaring AI ({keterangan_lain})"
        c.execute(
            "INSERT INTO events (timestamp, category, detail, image_path) VALUES (?, ?, ?, ?)",
            (waktu_full, "ALARM PALSU PIR", detail_teks, url_foto),
        )
        state["latest_image"] = url_foto
        state["latest_result"] = f"ALARM PALSU DISARING ({keterangan_lain})"

    conn.commit()
    conn.close()

    return {
        "person_detected": jumlah_orang > 0,
        "person_count": jumlah_orang,
        "alarm_active": state["alarm_active"],
    }

# ==============================================================================
# ENDPOINT 5: KONTROL DARI TOMBOL WEB DASHBOARD
# ==============================================================================
@app.post("/api/control")
async def kontrol_dashboard(ctrl: ControlPayload):
    if ctrl.action == "toggle_armed":
        state["armed"] = not state["armed"]
        if not state["armed"]:
            state["alarm_active"] = False
    elif ctrl.action == "toggle_lamp":
        state["lamp_on"] = not state["lamp_on"]
    elif ctrl.action == "reset_alarm":
        state["alarm_active"] = False
    elif ctrl.action == "toggle_backup_csi":
        state["backup_csi_mode"] = not state["backup_csi_mode"]
    return {"status": "ok", "state": state}

# ==============================================================================
# ENDPOINT 6: DATA LENGKAP UNTUK DASHBOARD WEB (AUTO-REFRESH)
# ==============================================================================
@app.get("/api/dashboard")
async def data_dashboard():
    is_online = (time.time() - state["last_seen"]) < 10.0

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Hitung statistik PIR vs AI
    c.execute("SELECT COUNT(*) FROM events WHERE category = 'ORANG TERDETEKSI'")
    total_orang = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM events WHERE category = 'ALARM PALSU PIR'")
    total_palsu = c.fetchone()[0]

    total_pir = total_orang + total_palsu
    persen_reduksi = round((total_palsu / total_pir) * 100, 1) if total_pir > 0 else 0.0

    # Ambil 10 riwayat kejadian terbaru
    c.execute("SELECT timestamp, category, detail, image_path FROM events ORDER BY id DESC LIMIT 10")
    riwayat = [
        {"timestamp": r[0], "category": r[1], "detail": r[2], "image_path": r[3]}
        for r in c.fetchall()
    ]
 
    # Ambil 20 titik grafik suhu & kelembapan terbaru
    c.execute("SELECT timestamp, temperature, humidity FROM sensor_logs ORDER BY id DESC LIMIT 20")
    logs = c.fetchall()[::-1]
    conn.close()

    return {
        "online": is_online,
        "state": state,
        "stats": {
            "total_pir": total_pir,
            "total_orang": total_orang,
            "total_palsu": total_palsu,
            "persen_reduksi": persen_reduksi,
        },
        "history": riwayat,
        "chart": {
            "labels": [x[0] for x in logs],
            "temp": [x[1] for x in logs],
            "hum": [x[2] for x in logs],
        },
    }