"""Tes worker pada jalur unduhan: dari id di antrean sampai berkas di disk.

Model tetap dipalsukan. Yang diuji di sini bukan kecerdasan model, melainkan
apa yang terjadi kalau unduhan gagal, PDF rusak, atau satu berkas tidak bisa
dibaca — kasus yang justru paling sering muncul dan paling mahal kalau
diam-diam menghasilkan tabel kosong.
"""
import unittest
from pathlib import Path
from unittest import mock

from tests.base import TempDbCase, fake_model
import config
import db
from services import sources
from worker import Worker


class DownloadCase(TempDbCase):

    def buat_pekerjaan(self, source="telegram", berkas=(("f1", "a.jpg"),)):
        job_id = db.create_job(1001, source, len(berkas),
                               drive_url="FOLDER" if source == "drive" else None)
        for remote_id, name in berkas:
            db.add_file(job_id, name, remote_id=remote_id)
        return job_id

    def jalankan(self, job_id):
        worker = Worker()
        job = db.claim_next_job()
        self.assertIsNotNone(job, "pekerjaan tidak bisa diklaim")
        self.assertEqual(job["id"], job_id)
        worker.run_job(job)
        return db.get_job(job_id)


class UnduhanTest(DownloadCase):

    def test_berkas_telegram_diunduh_lalu_dibaca(self):
        job_id = self.buat_pekerjaan()
        contoh = Path(__file__).parent.parent / "eval" / "dataset" / "images" / "X00016469612.jpg"

        def palsu(file_id, name, dest_dir, bot_token=None):
            return sources.Incoming(filename=name, path=contoh, size=contoh.stat().st_size)

        with mock.patch.object(sources, "download_telegram_file", side_effect=palsu), \
             fake_model():
            job = self.jalankan(job_id)

        self.assertEqual(job["status"], "done")
        self.assertEqual(len(db.receipts_for_job(job_id)), 1)

    def test_unduhan_gagal_menandai_berkas_dan_tidak_menggantung(self):
        job_id = self.buat_pekerjaan()
        with mock.patch.object(sources, "download_telegram_file",
                               side_effect=sources.SourceError("terlalu besar")):
            job = self.jalankan(job_id)

        self.assertEqual(job["status"], "failed")
        self.assertIn("gagal", job["error"])
        self.assertEqual(db.receipts_for_job(job_id), [])

    def test_satu_berkas_gagal_lainnya_tetap_diproses(self):
        job_id = self.buat_pekerjaan(berkas=(("f1", "a.jpg"), ("f2", "b.jpg")))
        contoh = Path(__file__).parent.parent / "eval" / "dataset" / "images" / "X00016469619.jpg"

        def palsu(file_id, name, dest_dir, bot_token=None):
            if file_id == "f1":
                raise sources.SourceError("hilang")
            return sources.Incoming(filename=name, path=contoh, size=100)

        with mock.patch.object(sources, "download_telegram_file", side_effect=palsu), \
             fake_model():
            job = self.jalankan(job_id)

        self.assertEqual(job["status"], "done")
        self.assertIn("1 dari 2", job["error"] or "")
        self.assertEqual(len(db.receipts_for_job(job_id)), 1)

    def test_folder_drive_dibaca_ulang_oleh_worker(self):
        job_id = self.buat_pekerjaan(source="drive", berkas=())
        contoh = Path(__file__).parent.parent / "eval" / "dataset" / "images" / "X00016469620.jpg"

        def ambil(file_id, name, dest_dir):
            return sources.Incoming(filename=name, path=contoh, size=100)

        with mock.patch.object(sources, "list_folder",
                               return_value=[("d1", "a.jpg"), ("d2", "b.jpg")]), \
             mock.patch.object(sources, "download_drive_file", side_effect=ambil), \
             fake_model():
            job = self.jalankan(job_id)

        self.assertEqual(job["status"], "done")
        self.assertEqual(job["total_files"], 2)
        self.assertEqual(len(db.receipts_for_job(job_id)), 2)

    def test_folder_drive_kosong_saat_dikerjakan_jadi_gagal_jelas(self):
        job_id = self.buat_pekerjaan(source="drive", berkas=())
        with mock.patch.object(sources, "list_folder", return_value=[]), fake_model():
            job = self.jalankan(job_id)

        self.assertEqual(job["status"], "failed")
        self.assertIn("tidak ada berkas", job["error"])


if __name__ == "__main__":
    unittest.main()
