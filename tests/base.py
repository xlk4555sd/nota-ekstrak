"""Dasar untuk semua tes.

Dua hal yang dijaga di sini:
  - setiap tes memakai basis data sementara sendiri, jadi data asli tidak
    pernah tersentuh dan urutan tes tidak saling memengaruhi;
  - model bahasa selalu dipalsukan, jadi tes gratis, cepat, dan hasilnya sama
    setiap kali dijalankan.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Data tes tidak boleh menyentuh folder data sungguhan. Variabel ini dibaca
# config saat diimpor, jadi harus dipasang sebelum config diimpor.
_TMP = tempfile.mkdtemp(prefix="nota-test-")
os.environ.setdefault("NOTA_DATA_DIR", str(Path(_TMP) / "home"))

import config  # noqa: E402
import db  # noqa: E402

_REAL_DB_PATH = config.DB_PATH


class TempDbCase(unittest.TestCase):
    """Menyediakan basis data bersih untuk tiap tes."""

    def setUp(self):
        self.data_dir = Path(tempfile.mkdtemp(prefix="nota-case-", dir=_TMP))
        config.DATA_DIR = self.data_dir
        config.DB_PATH = self.data_dir / "nota.sqlite3"
        config.UPLOAD_DIR = self.data_dir / "uploads"
        config.EXPORT_DIR = self.data_dir / "exports"
        config.ensure_dirs()
        db.reset_connection()
        db.init_db()
        db.upsert_chat(1001, allowed=1, daily_receipts=100, daily_tokens=200_000)

    def tearDown(self):
        # Koneksi ditutup supaya tidak ada pegangan ke berkas tes yang sudah
        # selesai; ini juga menghindari sqlite mengunci folder sementara.
        db.reset_connection()


class FakeModel:
    """Pengganti services.extract.read_receipts.

    Bisa disuruh gagal, lambat, atau mengembalikan JSON rusak — tiga hal yang
    paling sering terjadi di dunia nyata dan paling sulit diuji tanpa tiruan.
    """

    def __init__(self, answer=None, error=None, broken_json=False, payload_text=None):
        self.answer = answer or {"vendor": "Toko Uji", "tanggal": "24/10/2026",
                                 "nomor_nota": "INV-1", "total": "1000",
                                 "mata_uang": "IDR"}
        self.error = error
        self.broken_json = broken_json
        self.payload_text = payload_text
        self.calls = 0

    def __call__(self, image_paths, model=None, api_key=None):
        from services import extract

        self.calls += 1
        if self.error:
            raise extract.ModelError(self.error)
        if self.broken_json:
            raise extract.ModelRefused("model tidak menjawab JSON")
        text = self.payload_text or json.dumps(self.answer, ensure_ascii=False)
        return extract.Answer(payload=text, prompt_tokens=400, completion_tokens=50,
                              model="model-tiruan", seconds=0.01)


def fake_model(answer=None, error=None, broken_json=False):
    """Pasang model tiruan selama blok `with`, lepas lagi setelahnya."""
    return mock.patch(
        "services.extract.read_receipts",
        FakeModel(answer=answer, error=error, broken_json=broken_json),
    )


class FakeTelegram:
    """Menggantikan bot.telegram: mencatat pesan, tidak menghubungi internet."""

    def __init__(self):
        self.messages = []
        self.documents = []
        self.callbacks = []

    def send_message(self, chat_id, text, reply_markup=None, parse_mode="HTML"):
        self.messages.append({"chat": chat_id, "text": text, "markup": reply_markup})
        return {"message_id": len(self.messages)}

    def send_document(self, chat_id, path, filename=None, caption=None):
        self.documents.append({"chat": chat_id, "path": str(path), "caption": caption})
        return {"message_id": 900 + len(self.documents)}

    def answer_callback(self, callback_id, text=None):
        self.callbacks.append({"id": callback_id, "text": text})

    def edit_message(self, chat_id, message_id, text, reply_markup=None):
        self.messages.append({"chat": chat_id, "text": text, "markup": reply_markup})

    def last_text(self):
        return self.messages[-1]["text"] if self.messages else ""
