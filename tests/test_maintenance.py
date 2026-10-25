"""Pembersihan data: yang lama dihapus, yang masih dipakai tidak.

Kenapa diuji terpisah: pembersih ini menghapus berkas user. Salah satu
kesalahan di sini tidak menghasilkan pesan galat — hasilnya baru terlihat
saat ada orang mengeluh notanya hilang. Jadi aturannya dikunci di sini.
"""
import os
import time
from pathlib import Path

import config
import db
import storage.maintenance as maintenance
from tests.base import TempDbCase


class MaintenanceTest(TempDbCase):
    CHAT = 4242

    def _job_selesai(self, umur_hari):
        """Pekerjaan selesai lengkap dengan satu berkas dan satu hasil."""
        job_id = db.create_job(self.CHAT, "telegram", 1)
        file_id = db.add_file(job_id, "nota.jpg", path="x", remote_id="UJI")
        db.add_receipt(file_id, "nota.jpg", {
            "vendor": "Toko", "tanggal": "2024-10-18", "nomor_nota": "A1",
            "total": "75400", "mata_uang": "IDR",
        })
        db.set_job_status(job_id, "done")

        # Mundurkan cap waktunya supaya benar-benar terlihat tua.
        lama = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(
            time.time() - umur_hari * 86400))
        conn = db.connect()
        conn.execute("UPDATE jobs SET created_at = ? WHERE id = ?", (lama, job_id))
        conn.execute("UPDATE receipts SET created_at = ? WHERE file_id = ?", (lama, file_id))
        conn.commit()

        folder = Path(config.UPLOAD_DIR) / f"job{job_id}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "nota.jpg").write_bytes(b"x" * 2048)
        # mtime ikut dimundurkan, karena pembersih folder memakainya
        waktu_lama = time.time() - umur_hari * 86400
        os.utime(folder, (waktu_lama, waktu_lama))

        return job_id, folder

    def test_pekerjaan_baru_tidak_disentuh(self):
        job_id, folder = self._job_selesai(0)
        hasil = maintenance.bersihkan_unggahan(hari=7, kering=True)
        self.assertIn(f"job{job_id}", hasil["dilewati"])
        self.assertNotIn(f"job{job_id}", hasil["dihapus"])
        self.assertTrue(folder.exists(), "folder pekerjaan baru tidak boleh hilang")

    def test_pekerjaan_lama_dihapus(self):
        job_id, folder = self._job_selesai(10)
        hasil = maintenance.bersihkan_unggahan(hari=7)
        self.assertIn(f"job{job_id}", hasil["dihapus"])
        self.assertFalse(folder.exists(), "folder lama harus benar-benar terhapus")

    def test_pekerjaan_berjalan_tidak_pernah_dihapus(self):
        """Meski umurnya berminggu-minggu, pekerjaan yang belum selesai tetap aman."""
        job_id, folder = self._job_selesai(30)
        db.set_job_status(job_id, "running")
        hasil = maintenance.bersihkan_unggahan(hari=1)
        self.assertIn(f"job{job_id}", hasil["dilewati"])
        self.assertTrue(folder.exists())

    def test_kering_tidak_menghapus_apa_pun(self):
        job_id, folder = self._job_selesai(10)
        maintenance.bersihkan_semua(hari=7, hari_basis_data=7, kering=True)
        self.assertTrue(folder.exists())
        self.assertIsNotNone(db.get_job(job_id), "data tidak boleh hilang saat kering")

    def test_basis_data_lama_dihapus_beserta_hasilnya(self):
        job_id, _ = self._job_selesai(40)
        hasil = maintenance.bersihkan_basis_data(hari=30)
        self.assertIn(job_id, hasil["pekerjaan"])
        self.assertEqual(hasil["hasil"], 1)
        self.assertIsNone(db.get_job(job_id))
        self.assertEqual(db.files_for_job(job_id), [])
        self.assertEqual(db.receipts_for_job(job_id), [])

    def test_basis_data_baru_tidak_disentuh(self):
        job_id, _ = self._job_selesai(1)
        hasil = maintenance.bersihkan_basis_data(hari=30)
        self.assertNotIn(job_id, hasil["pekerjaan"])
        self.assertIsNotNone(db.get_job(job_id))

    def test_contoh_ekspor_tidak_ikut_terhapus(self):
        """contoh.csv/xlsx dipakai dokumentasi; jangan hilang saat bersih-bersih."""
        folder = Path(config.EXPORT_DIR)
        folder.mkdir(parents=True, exist_ok=True)
        contoh = folder / "contoh.csv"
        contoh.write_text("a,b\n1,2\n")
        lama = time.time() - 30 * 86400
        os.utime(contoh, (lama, lama))

        hasil = maintenance.bersihkan_ekspor(hari=7)
        self.assertNotIn("contoh.csv", hasil["dihapus"])
        self.assertTrue(contoh.exists())
