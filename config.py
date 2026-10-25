"""Konfigurasi terpusat. Semua pembacaan environment terjadi di sini, tidak tersebar.

Setiap batas punya nilai bawaan yang aman; environment hanya perlu diisi kalau
nilainya berbeda. Kalau variabel wajib tidak ada, kita gagal cepat saat start
(fail fast) alih-alih meledak di tengah pekerjaan user.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("NOTA_DATA_DIR", BASE_DIR / "data"))
DB_PATH = DATA_DIR / "nota.sqlite3"
UPLOAD_DIR = DATA_DIR / "uploads"
EXPORT_DIR = DATA_DIR / "exports"

# --- Model -----------------------------------------------------------------
RIVER_BASE_URL = os.environ.get("RIVER_BASE_URL", "https://api.river.ai/v1")
MODEL_NAME = os.environ.get("MODEL_NAME", "deepseek-ai/DeepSeek-V4.1-Flash-1017")
MODEL_TIMEOUT = 60          # detik; satu panggilan model tidak boleh lebih lama
MODEL_MAX_RETRY = 1         # total percobaan = 1 + retry. Dua percobaan, bukan tak terbatas.

# --- Batas per pekerjaan ---------------------------------------------------
MAX_FILES_PER_JOB = 50      # lebih dari ini ditolak sebelum diproses
MAX_IMAGES_PER_CALL = 5     # lima yang terbukti di uji; di atas itu belum diuji
MAX_UPLOAD_BYTES = 20 * 1024 * 1024   # batas ambil berkas dari Telegram
MAX_PDF_PAGES = 100         # PDF 100 halaman masih masuk akal untuk satu pekerjaan

# --- Batas per chat --------------------------------------------------------
DAILY_RECEIPTS_PER_CHAT = 100
DAILY_TOKENS_PER_CHAT = 200_000
GLOBAL_DAILY_TOKENS = 2_000_000       # pengaman kalau ada penyalahgunaan

# --- Rendering -------------------------------------------------------------
PDF_RENDER_DPI = 150        # cukup tajam untuk teks nota, tidak boros token
IMAGE_MAX_SIDE = 2000       # model mengecilkan ke ~1300 px; kirim lebih kecil = hemat

# --- Pembersihan data ------------------------------------------------------
# Tanpa pembersih, folder unggahan tumbuh terus sampai disk penuh. Angka di
# bawah sengaja longgar: notanya masih bisa diunduh ulang dari Telegram, tapi
# kita tetap memberi waktu seminggu sebelum berkasnya dibuang.
CLEANUP_UPLOADS_DAYS = 7        # umur minimal berkas unggahan sebelum dihapus
CLEANUP_EXPORTS_DAYS = 7        # berkas CSV/Excel lama
CLEANUP_DATABASE_DAYS = 30      # baris pekerjaan lama; lebih lama dari berkasnya
CLEANUP_INTERVAL_HOURS = 12     # seberapa sering pembersih berjalan di serve.py

# --- Telegram --------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
TELEGRAM_API = "https://api.telegram.org"

# Alamat publik tempat Telegram mengirim pesan. Kalau diisi, serve.py
# mendaftarkan webhook sendiri saat start — berguna untuk tunnel sementara
# yang alamatnya berganti tiap kali dinyalakan.
PUBLIC_URL = os.environ.get("PUBLIC_URL", "")

# --- Model API -------------------------------------------------------------
RIVER_API_KEY = os.environ.get("RIVER_API_KEY", "")


def ensure_dirs():
    for d in (DATA_DIR, UPLOAD_DIR, EXPORT_DIR):
        d.mkdir(parents=True, exist_ok=True)


def missing_required():
    """Nama variabel yang belum diisi. Dipakai app.py untuk gagal cepat.

    Test dan mode lokal tidak butuh token, jadi fungsi ini tidak dipanggil
    otomatis saat import.
    """
    missing = []
    if not RIVER_API_KEY:
        missing.append("RIVER_API_KEY")
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_WEBHOOK_SECRET:
        missing.append("TELEGRAM_WEBHOOK_SECRET")
    return missing
