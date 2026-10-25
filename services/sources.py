"""Dari mana berkas datang: pesan Telegram atau folder Google Drive publik.

Perbedaan keduanya hanya soal cara mendapat daftar berkas. Setelah diunduh,
keduanya menghasilkan bentuk yang sama supaya worker tidak perlu tahu asalnya.
"""
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import config


class SourceError(Exception):
    """Pesan untuk user: apa yang salah dan apa yang harus dilakukan."""


@dataclass
class Incoming:
    filename: str
    path: Path
    size: int


DRIVE_FOLDER = re.compile(r"drive\.google\.com/drive/(?:u/\d+/)?folders/([A-Za-z0-9_-]+)")
DRIVE_FILE = re.compile(r"drive\.google\.com/file/d/([A-Za-z0-9_-]+)")


def folder_id_from(text):
    """Ambil ID folder dari link Drive. None kalau bukan link folder.

    Link ke satu berkas sengaja tidak diterima: bedanya tipis di mata user,
    tapi hasilnya berbeda jauh (satu nota vs. folder penuh), jadi lebih baik
    ditolak terus terang.
    """
    if not text:
        return None
    match = DRIVE_FOLDER.search(text)
    return match.group(1) if match else None


def is_drive_file_link(text):
    return bool(text and DRIVE_FILE.search(text))


def list_folder(folder_id, wanted_ext=(".pdf", ".jpg", ".jpeg", ".png", ".webp")):
    """Daftar berkas di folder Drive yang dibagikan publik.

    Cara ini sengaja dipilih: membaca halaman
    'embeddedfolderview' yang tidak butuh API key. Karena itu hanya folder
    publik yang bisa dibaca — folder privat terlihat kosong, dan itu harus
    dikatakan terus terang ke user, bukan dibiarkan menunggu.
    """
    html = _fetch_text(
        f"https://drive.google.com/embeddedfolderview?id={folder_id}#list"
    )
    if "Google Drive" in html and "embeddedfolderview" not in html:
        raise SourceError("folder Drive tidak bisa dibaca. Pastikan aksesnya 'siapa saja yang punya link'")

    entries = re.findall(
        r'<div class="flip-entry" id="entry-([A-Za-z0-9_-]+)".*?'
        r'<div class="flip-entry-title">(.*?)</div>',
        html, re.S,
    )
    files = []
    for file_id, title in entries:
        name = re.sub(r"<[^>]+>", "", title).strip()
        if not name.lower().endswith(wanted_ext):
            continue
        files.append((file_id, name))

    if not files:
        raise SourceError(
            "tidak ada PDF atau gambar di folder itu. "
            "Kalau berkasnya ada di subfolder, pindahkan dulu ke folder utama."
        )
    if len(files) > config.MAX_FILES_PER_JOB:
        raise SourceError(f"folder berisi {len(files)} berkas, batasnya {config.MAX_FILES_PER_JOB} per kiriman")
    return files


def download_drive_file(file_id, name, dest_dir):
    dest = Path(dest_dir) / _safe_name(name)
    _download(f"https://drive.google.com/uc?export=download&id={file_id}", dest)
    return Incoming(filename=name, path=dest, size=dest.stat().st_size)


def download_telegram_file(file_id, name, dest_dir, bot_token=None):
    """Ambil berkas yang dikirim ke bot lewat getFile.

    Batas 20 MB milik Telegram sudah ditolak sebelum ini, tapi ukuran tetap
    diperiksa lagi: lebih baik menolak dengan kalimat jelas daripada menulis
    berkas besar ke disk yang ruangnya terbatas.
    """
    token = bot_token or config.TELEGRAM_BOT_TOKEN
    if not token:
        raise SourceError("token bot belum diisi")

    try:
        info = _fetch_json(f"{config.TELEGRAM_API}/bot{token}/getFile?file_id={file_id}")
    except Exception as exc:
        raise SourceError("Telegram tidak bisa dihubungi saat mengambil berkas") from exc

    if not info.get("ok"):
        raise SourceError(
            "Telegram menolak memberikan berkas ini. Kalau ukurannya di atas "
            f"{config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB, kirim sebagai "
            "dokumen atau perkecil dulu."
        )

    result = info["result"]
    size = result.get("file_size") or 0
    if size > config.MAX_UPLOAD_BYTES:
        raise SourceError(
            f"berkas {size // (1024 * 1024)} MB, batasnya "
            f"{config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB"
        )

    dest = Path(dest_dir) / _safe_name(name)
    _download(f"{config.TELEGRAM_API}/file/bot{token}/{result['file_path']}", dest)
    return Incoming(filename=name, path=dest, size=dest.stat().st_size)


def _safe_name(name):
    """Buang bagian berbahaya dari nama berkas.

    Nama dari Telegram dan Drive berasal dari luar, jadi jangan sampai berisi
    '../' yang bisa menulis ke luar folder data.
    """
    base = Path(name).name
    cleaned = re.sub(r"[^A-Za-z0-9._ ()\-]", "_", base).strip() or "berkas"
    return cleaned[:120]


def _download(url, dest):
    request = urllib.request.Request(url, headers={"User-Agent": "nota-ekstrak/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            with open(dest, "wb") as handle:
                written = 0
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > config.MAX_UPLOAD_BYTES:
                        raise SourceError("berkas lebih besar dari batas, unduhan dihentikan")
                    handle.write(chunk)
    except SourceError:
        dest.unlink(missing_ok=True)
        raise
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise SourceError(f"gagal mengunduh berkas: {exc}") from exc
    if dest.stat().st_size == 0:
        dest.unlink(missing_ok=True)
        raise SourceError("berkas yang terunduh kosong")


def _fetch_text(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read().decode("utf-8", errors="replace")


def _fetch_json(url):
    import json
    return json.loads(_fetch_text(url))
