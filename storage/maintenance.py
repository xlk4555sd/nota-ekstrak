"""Pembersihan data: folder unggahan, hasil ekspor, dan baris basis data lama.

Kenapa ada modul tersendiri: folder `data/uploads` tumbuh terus setiap kali
ada kiriman, dan tanpa pembersih disk akan penuh tanpa ada yang sadar. Aturan
di sini dibuat konservatif — yang dihapus hanya pekerjaan yang sudah selesai
dan lebih tua dari batas hari. Pekerjaan yang masih antre atau berjalan tidak
pernah disentuh, sekalipun umurnya sudah lama.
"""

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config

# Status yang boleh dibersihkan. `pending` dan `running` sengaja tidak ada di
# sini: menghapus keduanya akan membuat worker kehilangan pekerjaan.
STATUS_BOLEH_DIHAPUS = ("done", "failed", "cancelled")


def ringkasan():
    """Ukuran tiap folder data, untuk ditampilkan sebelum membersihkan."""
    out = {}
    for label, folder in (("unggahan", config.UPLOAD_DIR),
                          ("ekspor", config.EXPORT_DIR)):
        folder = Path(folder)
        total, jumlah = 0, 0
        if folder.exists():
            for item in folder.iterdir():
                jumlah += 1
                if item.is_file():
                    total += item.stat().st_size
                elif item.is_dir():
                    total += sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
        out[label] = {"berkas": jumlah, "byte": total}
    out["basis_data"] = {"berkas": 1 if Path(config.DB_PATH).exists() else 0,
                         "byte": Path(config.DB_PATH).stat().st_size if Path(config.DB_PATH).exists() else 0}
    return out


def pekerjaan_lama(hari):
    """Pekerjaan selesai yang lebih tua dari `hari` hari.

    Batasnya berupa cap waktu, bukan sekadar "pekerjaan selesai". Tanpa itu
    pembersih akan menghapus pekerjaan yang baru masuk pagi ini.
    """
    import db
    batas = (datetime.now(timezone.utc) - timedelta(days=hari)).isoformat(timespec="seconds")
    return db.selesai_sebelum(batas)


def bersihkan_unggahan(hari=7, kering=False):
    """Hapus folder unggahan milik pekerjaan yang sudah selesai dan lama.

    `kering=True` hanya menghitung, tidak menghapus — dipakai admin untuk
    melihat dampaknya sebelum benar-benar dijalankan.
    """
    folder_induk = Path(config.UPLOAD_DIR)
    dihapus, byte, dilewati = [], 0, []

    # Pekerjaan yang masih menunggu atau berjalan tidak boleh kehilangan
    # berkasnya, sekalipun umurnya sudah lewat batas.
    hidup = {f"job{row['id']}" for row in _pekerjaan_aktif()}
    from db import connect
    semua = {f"job{row['id']}" for row in connect().execute("SELECT id FROM jobs")}

    if folder_induk.exists():
        for item in sorted(folder_induk.iterdir()):
            if not item.is_dir():
                continue
            umur_ok = _lebih_tua_dari(item, hari)
            if item.name in hidup:
                dilewati.append(item.name)
            elif item.name in semua and not umur_ok:
                dilewati.append(item.name)      # pekerjaannya masih baru
            elif item.name in semua or not semua:
                ukuran = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                dihapus.append(item.name)
                byte += ukuran
                if not kering:
                    shutil.rmtree(item, ignore_errors=True)

    return {"dihapus": dihapus, "byte": byte, "dilewati": dilewati, "kering": kering}


def bersihkan_ekspor(hari=7, kering=False):
    """Hapus berkas CSV/Excel lama di folder ekspor."""
    folder = Path(config.EXPORT_DIR)
    batas = datetime.now(timezone.utc) - timedelta(days=hari)
    dihapus, byte = [], 0
    if not folder.exists():
        return {"dihapus": dihapus, "byte": byte, "kering": kering}

    for item in folder.iterdir():
        if not item.is_file() or item.name.startswith("contoh."):
            continue          # contoh.csv/xlsx dipakai dokumentasi, jangan dihapus
        waktu = datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc)
        if waktu < batas:
            byte += item.stat().st_size
            dihapus.append(item.name)
            if not kering:
                item.unlink(missing_ok=True)

    return {"dihapus": dihapus, "byte": byte, "kering": kering}


def bersihkan_basis_data(hari=30, kering=False):
    """Hapus baris pekerjaan lama beserta berkas dan hasilnya.

    Urutan penting: koreksi → hasil → berkas → pekerjaan. Walau tabel memakai
    ON DELETE CASCADE, menghapus dari anak ke induk lebih mudah diperiksa
    kalau nanti skema berubah.
    """
    from db import connect
    lama = pekerjaan_lama(hari)
    if not lama or kering:
        return {"pekerjaan": [row["id"] for row in lama], "hasil": 0, "kering": kering}

    conn = connect()
    ids = [row["id"] for row in lama]
    tanda = ",".join("?" * len(ids))

    hasil = conn.execute(
        f"SELECT COUNT(*) AS n FROM receipts r JOIN files f ON f.id = r.file_id "
        f"WHERE f.job_id IN ({tanda})", ids,
    ).fetchone()["n"]

    conn.execute(
        f"DELETE FROM corrections WHERE receipt_id IN ("
        f"SELECT r.id FROM receipts r JOIN files f ON f.id = r.file_id WHERE f.job_id IN ({tanda}))",
        ids,
    )
    conn.execute(
        f"DELETE FROM receipts WHERE file_id IN (SELECT id FROM files WHERE job_id IN ({tanda}))",
        ids,
    )
    conn.execute(f"DELETE FROM usage WHERE job_id IN ({tanda})", ids)
    conn.execute(f"DELETE FROM files WHERE job_id IN ({tanda})", ids)
    conn.execute(f"DELETE FROM jobs WHERE id IN ({tanda})", ids)
    conn.commit()

    return {"pekerjaan": ids, "hasil": hasil, "kering": kering}


def bersihkan_semua(hari=7, hari_basis_data=30, kering=False):
    """Jalankan seluruh pembersihan dengan satu ringkasan."""
    return {
        "unggahan": bersihkan_unggahan(hari, kering=kering),
        "ekspor": bersihkan_ekspor(hari, kering=kering),
        "basis_data": bersihkan_basis_data(hari_basis_data, kering=kering),
    }


def _pekerjaan_aktif():
    """Pekerjaan yang belum selesai — berkasnya tidak boleh dihapus."""
    from db import connect
    return [dict(r) for r in connect().execute(
        "SELECT id FROM jobs WHERE status IN ('pending', 'running')"
    )]


def _lebih_tua_dari(item, hari):
    """Apakah folder/berkas ini lebih tua dari `hari` hari."""
    batas = datetime.now(timezone.utc) - timedelta(days=hari)
    waktu = datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc)
    return waktu < batas
