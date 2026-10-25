"""Pembersih otomatis: berjalan sendiri selama layanan hidup.

Kenapa di thread terpisah dan bukan cron: mesin ini tidak punya akses cron,
dan menambah ketergantungan sistem untuk pekerjaan sesederhana ini tidak
sepadan. Cukup satu thread yang tidur, bangun tiap beberapa jam, lalu bersih.

Yang penting: thread ini tidak boleh membuat layanan mati kalau ada galat.
Semua kegagalan ditangkap dan dicatat ke log, lalu ia tidur lagi.
"""
import threading
import time
import traceback

import config
import storage.maintenance as maintenance

# Jeda pertama sengaja diberi jarak: layanan baru hidup biasanya sedang sibuk
# menerima kiriman, bukan saat yang tepat untuk menghapus berkas.
JEDA_AWAL_DETIK = 60


def jalankan_sekali():
    """Satu putaran pembersihan. Mengembalikan ringkasan seperti admin_cli."""
    return maintenance.bersihkan_semua(
        hari=config.CLEANUP_UPLOADS_DAYS,
        hari_basis_data=config.CLEANUP_DATABASE_DAYS,
        kering=False,
    )


def _catat(pesan):
    print(f"[pembersih] {pesan}", flush=True)


def _putaran():
    try:
        hasil = jalankan_sekali()
        unggahan = hasil["unggahan"]
        basis = hasil["basis_data"]
        _catat(
            f"{len(unggahan['dihapus'])} folder unggahan "
            f"({unggahan['byte'] / 1024:.0f} KB), "
            f"{len(hasil['ekspor']['dihapus'])} berkas ekspor, "
            f"{len(basis['pekerjaan'])} pekerjaan lama"
        )
    except Exception:
        # Pembersihan gagal bukan alasan mematikan bot. Catat, lalu coba lagi
        # di putaran berikutnya.
        _catat("gagal membersihkan:\n" + traceback.format_exc())


def mulai(di_latar=True):
    """Nyalakan pembersih. Panggil sekali dari serve.py saat layanan start."""

    def _loop():
        time.sleep(JEDA_AWAL_DETIK)
        while True:
            _putaran()
            time.sleep(config.CLEANUP_INTERVAL_HOURS * 3600)

    if not di_latar:
        _loop()
        return None

    thread = threading.Thread(target=_loop, name="pembersih", daemon=True)
    thread.start()
    _catat(f"aktif — berjalan tiap {config.CLEANUP_INTERVAL_HOURS} jam")
    return thread
