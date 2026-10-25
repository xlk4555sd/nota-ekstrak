"""Berkas masuk -> gambar siap dikirim ke model.

Model hanya menerima gambar, bukan PDF. Ini bukan pilihan desain, itu batas
yang sudah diuji: mengirim PDF mentah membuat model menjawab "tidak ada
dokumen". Jadi semua bentuk masukan diseragamkan jadi JPEG di sini.
"""
from dataclasses import dataclass
from pathlib import Path

import pymupdf  # dulu bernama fitz; nama lama sudah usang di 1.26
from PIL import Image, UnidentifiedImageError

import config


class ConvertError(Exception):
    """Berkas tidak bisa dijadikan gambar. Pesannya ditulis untuk user, bukan log."""


@dataclass
class Page:
    path: Path
    page_no: int | None      # None untuk gambar tunggal
    name: str


def convert_file(src, out_dir, name=None):
    """Ubah satu berkas menjadi daftar halaman gambar.

    Berkas berupa gambar diedarkan apa adanya (tetap dinormalkan supaya
    ukurannya hemat token). PDF dipecah per halaman.
    """
    src = Path(src)
    name = name or src.name
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    suffix = src.suffix.lower()
    if suffix == ".pdf":
        return _from_pdf(src, out_dir, name)
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return [_from_image(src, out_dir, name)]
    sebutan = suffix or "berkas ini"
    raise ConvertError(f"format {sebutan} belum didukung")


def _from_pdf(src, out_dir, name):
    try:
        doc = pymupdf.open(src)
    except Exception as exc:
        raise ConvertError("PDF tidak bisa dibaca, mungkin berkasnya rusak") from exc

    try:
        if doc.page_count == 0:
            raise ConvertError("PDF tidak punya halaman")
        if doc.page_count > config.MAX_PDF_PAGES:
            raise ConvertError(f"PDF {doc.page_count} halaman, batasnya {config.MAX_PDF_PAGES}")

        pages = []
        stem = Path(name).stem
        for index in range(doc.page_count):
            page = doc.load_page(index)
            pix = page.get_pixmap(dpi=config.PDF_RENDER_DPI)
            target = out_dir / f"{stem}__p{index + 1:03d}.jpg"
            pix.pil_save(target, format="JPEG", quality=88)
            pages.append(Page(path=target, page_no=index + 1, name=name))
        return pages
    finally:
        doc.close()   # selalu tutup, termasuk saat melempar ConvertError


def _from_image(src, out_dir, name):
    try:
        with Image.open(src) as img:
            img = img.convert("RGB")
            img.thumbnail((config.IMAGE_MAX_SIDE, config.IMAGE_MAX_SIDE))
            target = out_dir / (Path(name).stem + ".jpg")
            img.save(target, format="JPEG", quality=88)
    except UnidentifiedImageError as exc:
        raise ConvertError("berkas gambar tidak bisa dibaca") from exc
    return Page(path=target, page_no=None, name=name)
