"""Tes worker: alur berkas -> tabel, dan perilaku saat model gagal.

Model selalu dipalsukan di sini. Tes tidak boleh memanggil API berbayar, dan
hasil harus sama setiap kali dijalankan.
"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pymupdf
from PIL import Image

from tests.base import TempDbCase, fake_model
import config
import db
from services import extract
from worker import Worker


class WorkerTest(TempDbCase):

    def setUp(self):
        super().setUp()
        self.work = Path(tempfile.mkdtemp(prefix="nota-work-"))
        config.UPLOAD_DIR = self.work

    def _add_image_job(self, files=1):
        job_id = db.create_job(1001, "telegram", files)
        src = self.work / f"job{job_id}" / "src"
        src.mkdir(parents=True, exist_ok=True)
        for index in range(files):
            path = src / f"nota{index}.png"
            Image.new("RGB", (900, 1200), "white").save(path)
            db.add_file(job_id, path.name, str(path))
        return job_id

    def _run(self, job_id):
        worker = Worker()
        job = db.claim_next_job()
        self.assertEqual(job["id"], job_id)
        worker.run_job(job)
        return db.get_job(job_id)

    def test_satu_berkas_menghasilkan_satu_baris(self):
        job_id = self._add_image_job(1)
        with fake_model({"vendor": "Toko A", "total": "15000", "mata_uang": "IDR"}):
            job = self._run(job_id)
        self.assertEqual(job["status"], "done")
        hasil = db.receipts_for_job(job_id)
        self.assertEqual(len(hasil), 1)
        self.assertEqual(hasil[0]["vendor"], "Toko A")

    def test_nama_berkas_ikut_tercatat(self):
        job_id = self._add_image_job(1)
        with fake_model({"vendor": "A"}):
            self._run(job_id)
        self.assertEqual(db.receipts_for_job(job_id)[0]["named_file"], "nota0.png")

    def test_beberapa_berkas_diproses_semua(self):
        job_id = self._add_image_job(3)
        with fake_model({"vendor": "A", "total": "1"}) as model:
            job = self._run(job_id)
        self.assertEqual(job["status"], "done")
        self.assertEqual(len(db.receipts_for_job(job_id)), 3)
        self.assertEqual(model.calls, 3)

    def test_pdf_berhalaman_banyak_menjadi_beberapa_panggilan(self):
        job_id = db.create_job(1001, "telegram", 1)
        src = self.work / f"job{job_id}" / "src"
        src.mkdir(parents=True, exist_ok=True)
        path = src / "dua_halaman.pdf"
        doc = pymupdf.open()
        for index in range(3):
            page = doc.new_page()
            page.insert_text((72, 72), f"NOTA {index}")
        doc.save(path)
        doc.close()
        db.add_file(job_id, path.name, str(path))

        with fake_model({"vendor": "A"}) as model:
            self._run(job_id)
        self.assertEqual(model.calls, 3)

    def test_model_gagal_ditandai_tanpa_menghentikan_berkas_lain(self):
        job_id = self._add_image_job(2)
        calls = {"n": 0}

        def runner(paths, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return extract.Answer(payload={"vendor": "A"}, prompt_tokens=1,
                                      completion_tokens=1, model="x", seconds=0)
            raise extract.ModelError("model mati")

        with mock.patch("services.extract.read_receipts", side_effect=runner):
            job = self._run(job_id)
        self.assertEqual(job["status"], "done")   # sebagian berhasil
        self.assertIn("1 dari 2", job["error"])
        self.assertEqual(len(db.receipts_for_job(job_id)), 1)

    def test_semua_gagal_ditandai_gagal(self):
        job_id = self._add_image_job(1)
        with fake_model(error=extract.ModelError("mati")):
            job = self._run(job_id)
        self.assertEqual(job["status"], "failed")

    def test_berkas_hilang_tidak_menggagalkan_seluruh_pekerjaan(self):
        job_id = self._add_image_job(1)
        db.add_file(job_id, "hilang.jpg", str(self.work / "tidak_ada.jpg"))
        db.connect().execute("UPDATE jobs SET total_files = 2 WHERE id = ?", (job_id,))
        db.connect().commit()
        with fake_model({"vendor": "A"}):
            job = self._run(job_id)
        self.assertEqual(job["status"], "done")
        self.assertEqual(len(db.receipts_for_job(job_id)), 1)

    def test_pemakaian_token_tercatat_per_panggilan(self):
        job_id = self._add_image_job(1)
        with fake_model({"vendor": "A"}):
            self._run(job_id)
        usage = db.usage_since(1001, "2000-01-01T00:00:00+00:00")
        self.assertEqual(usage["calls"], 1)
        self.assertEqual(usage["total"], 450)   # 400 masuk + 50 keluar

    def test_jatah_token_habis_menghentikan_pekerjaan(self):
        job_id = self._add_image_job(3)
        # Batas diambil dari baris chat, jadi tes tidak perlu mengubah config global.
        db.upsert_chat(1001, allowed=1, daily_receipts=100, daily_tokens=100)
        with fake_model({"vendor": "A"}):
            job = self._run(job_id)
        self.assertEqual(job["status"], "cancelled")
        self.assertIn("token", job["error"])

    def test_hasil_ditandai_perlu_dicek(self):
        job_id = self._add_image_job(1)
        with fake_model({"vendor": "", "tanggal": "24/10/2026", "nomor_nota": "X",
                         "total": "1", "mata_uang": "IDR"}):
            self._run(job_id)
        hasil = db.receipts_for_job(job_id)[0]
        self.assertIn("vendor", hasil["review_flags"])
        self.assertIn("nomor_nota", hasil["review_flags"])


if __name__ == "__main__":
    unittest.main()
