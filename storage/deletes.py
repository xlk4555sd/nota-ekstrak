"""Menghapus milik user sendiri: satu kiriman, atau seluruh riwayat.

Kenapa dipisah dari `maintenance.py`: modul itu membersihkan data berdasarkan
UMUR (otomatis, konservatif, untuk menghemat disk). Modul ini menghapus
berdasarkan PERMINTAAN user, dan harus benar dalam dua hal yang tidak dipedulikan
pembersih otomatis:

  - batas kepemilikan: satu chat tidak boleh menghapus kiriman chat lain;
  - pekerjaan yang masih berjalan tidak boleh dihapus di tengah jalan.

Semua penghapusan di sini memakai `dry_run` untuk menghitung dulu, sehingga
user diberi tahu apa yang akan hilang sebelum benar-benar hilang.
"""

import shutil
from pathlib import Path

import config


class DeleteRefused(Exception):
    """Permintaan hapus ditolak karena tidak aman atau bukan miliknya."""


def rincian(job):
    """Apa saja yang akan hilang kalau pekerjaan ini dihapus.

    Dipakai dua kali: untuk memberi tahu user, dan untuk menghitung jumlah
    yang benar-benar terhapus — keduanya harus memakai angka yang sama.
    """
    from db import connect

    job_id = job["id"]
    conn = connect()
    hasil = conn.execute(
        "SELECT COUNT(*) AS n FROM receipts r JOIN files f ON f.id = r.file_id "
        "WHERE f.job_id = ?", (job_id,),
    ).fetchone()["n"]
    berkas = conn.execute(
        "SELECT COUNT(*) AS n FROM files WHERE job_id = ?", (job_id,),
    ).fetchone()["n"]
    folder = Path(config.UPLOAD_DIR) / f"job{job_id}"
    byte = 0
    if folder.exists():
        byte = sum(f.stat().st_size for f in folder.rglob("*") if f.is_file())
    return {"hasil": hasil, "berkas": berkas, "byte": byte, "folder": folder}


def hapus_pekerjaan(job, chat_id):
    """Hapus satu pekerjaan beserta berkas dan hasilnya.

    `job` harus sudah diperiksa pemanggil; di sini diperiksa ulang karena
    fungsi ini juga dipanggil lewat tombol, dan tombol bisa dikirim siapa pun
    yang tahu nomornya.
    """
    if job is None:
        raise DeleteRefused("Kiriman itu tidak ada.")
    if job["chat_id"] != chat_id:
        raise DeleteRefused("Kiriman itu bukan milikmu.")
    if job["status"] in ("pending", "running"):
        raise DeleteRefused(
            f"Kiriman #{job['id']} masih berjalan. Hentikan dulu dengan /batal."
        )

    info = rincian(job)
    job_id = job["id"]

    # Urutan dari anak ke induk. ON DELETE CASCADE sudah ada, tapi menghapus
    # eksplisit membuat perilakunya sama walau skema berubah.
    from db import connect
    conn = connect()
    conn.execute(
        "DELETE FROM corrections WHERE receipt_id IN ("
        "SELECT r.id FROM receipts r JOIN files f ON f.id = r.file_id WHERE f.job_id = ?)",
        (job_id,),
    )
    conn.execute(
        "DELETE FROM receipts WHERE file_id IN (SELECT id FROM files WHERE job_id = ?)",
        (job_id,),
    )
    conn.execute("DELETE FROM usage WHERE job_id = ?", (job_id,))
    conn.execute("DELETE FROM files WHERE job_id = ?", (job_id,))
    conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()

    # Berkas di disk dihapus setelah baris basis data: kalau penghapusan disk
    # gagal, yang tersisa hanya folder yatim yang bisa dibersihkan belakangan —
    # bukan baris basis data yang menunjuk berkas yang sudah tidak ada.
    shutil.rmtree(info["folder"], ignore_errors=True)

    _hapus_ekspor(job_id)
    return info


def hapus_semua(chat_id):
    """Hapus seluruh riwayat satu chat. Pekerjaan yang berjalan tidak disentuh."""
    from db import list_jobs_for_chat

    dihapus, dilewati, byte, hasil = [], [], 0, 0
    for job in list_jobs_for_chat(chat_id):
        if job["status"] in ("pending", "running"):
            dilewati.append(job["id"])
            continue
        info = hapus_pekerjaan(job, chat_id)
        dihapus.append(job["id"])
        byte += info["byte"]
        hasil += info["hasil"]
    return {"dihapus": dihapus, "dilewati": dilewati, "byte": byte, "hasil": hasil}


def _hapus_ekspor(job_id):
    """Hasil CSV/Excel yang sudah dibuat ikut dihapus.

    Tanpa ini, user menghapus kirimannya tapi berkas hasilnya masih tertinggal
    di server dan masih bisa diunduh lewat tombol lama.
    """
    folder = Path(config.EXPORT_DIR)
    if not folder.exists():
        return
    for ext in (".csv", ".xlsx"):
        (folder / f"nota_{job_id}{ext}").unlink(missing_ok=True)
