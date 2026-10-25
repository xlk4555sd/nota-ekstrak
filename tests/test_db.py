"""Tes basis data: status pekerjaan, koreksi, dan pembatasan akses."""
import unittest

from tests.base import TempDbCase
import db


class JobTest(TempDbCase):

    def test_pekerjaan_baru_berstatus_menunggu(self):
        job_id = db.create_job(1001, "telegram", 3)
        self.assertEqual(db.get_job(job_id)["status"], "pending")

    def test_ambil_pekerjaan_menandainya_berjalan(self):
        job_id = db.create_job(1001, "telegram", 1)
        job = db.claim_next_job()
        self.assertEqual(job["id"], job_id)
        self.assertEqual(job["status"], "running")
        self.assertIsNotNone(job["started_at"])

    def test_pekerjaan_tidak_diambil_dua_kali(self):
        db.create_job(1001, "telegram", 1)
        pertama = db.claim_next_job()
        kedua = db.claim_next_job()
        self.assertIsNotNone(pertama)
        self.assertIsNone(kedua)

    def test_antrean_mengikuti_urutan_masuk(self):
        satu = db.create_job(1001, "telegram", 1)
        dua = db.create_job(1001, "telegram", 1)
        self.assertEqual(db.claim_next_job()["id"], satu)
        self.assertEqual(db.claim_next_job()["id"], dua)

    def test_status_selesai_mencatat_waktu_selesai(self):
        job_id = db.create_job(1001, "telegram", 1)
        db.set_job_status(job_id, "done")
        job = db.get_job(job_id)
        self.assertEqual(job["status"], "done")
        self.assertIsNotNone(job["finished_at"])

    def test_pekerjaan_berjalan_terdeteksi_per_chat(self):
        job_id = db.create_job(1001, "telegram", 1)
        self.assertEqual(db.active_job_for(1001)["id"], job_id)
        self.assertIsNone(db.active_job_for(2002))

    def test_pekerjaan_selesai_tidak_dihitung_aktif(self):
        job_id = db.create_job(1001, "telegram", 1)
        db.set_job_status(job_id, "done")
        self.assertIsNone(db.active_job_for(1001))

    def test_kemajuan_bertambah_satu_per_berkas(self):
        job_id = db.create_job(1001, "telegram", 2)
        db.bump_job_progress(job_id)
        db.bump_job_progress(job_id)
        self.assertEqual(db.get_job(job_id)["done_files"], 2)


class ChatTest(TempDbCase):

    def test_chat_baru_tidak_boleh_pakai_bot(self):
        db.upsert_chat(2002)
        self.assertEqual(db.get_chat(2002)["allowed"], 0)

    def test_chat_bisa_diizinkan_dan_dibatasi(self):
        db.upsert_chat(2002, allowed=1, daily_receipts=20, note="tester")
        row = db.get_chat(2002)
        self.assertEqual(row["allowed"], 1)
        self.assertEqual(row["daily_receipts"], 20)
        self.assertEqual(row["note"], "tester")

    def test_mengubah_izin_tidak_menghapus_batas_lain(self):
        db.upsert_chat(2002, allowed=1, daily_receipts=20)
        db.upsert_chat(2002, allowed=0)
        row = db.get_chat(2002)
        self.assertEqual(row["allowed"], 0)
        self.assertEqual(row["daily_receipts"], 20)

    def test_chat_bisa_dihapus(self):
        db.upsert_chat(2002, allowed=1)
        db.delete_chat(2002)
        self.assertIsNone(db.get_chat(2002))


class ReceiptTest(TempDbCase):

    def _receipt(self):
        job_id = db.create_job(1001, "telegram", 1)
        file_id = db.add_file(job_id, "a.jpg", "/tmp/a.jpg")
        return job_id, file_id

    def test_hasil_disimpan_lengkap(self):
        job_id, file_id = self._receipt()
        db.add_receipt(file_id, "a.jpg", {
            "vendor": "Toko A", "tanggal": "24/10/2026",
            "nomor_nota": "INV-1", "total": "15000", "mata_uang": "IDR",
        }, review_flags=["nomor_nota"])
        hasil = db.receipts_for_job(job_id)[0]
        self.assertEqual(hasil["vendor"], "Toko A")
        self.assertEqual(hasil["review_flags"], ["nomor_nota"])

    def test_koreksi_menyimpan_nilai_lama_dan_baru(self):
        job_id, file_id = self._receipt()
        receipt_id = db.add_receipt(file_id, "a.jpg", {"vendor": "Toko A"})
        self.assertTrue(db.update_receipt(receipt_id, "vendor", "Toko B"))
        catatan = db.corrections_for_job(job_id)[0]
        self.assertEqual(catatan["value_before"], "Toko A")
        self.assertEqual(catatan["value_after"], "Toko B")
        self.assertEqual(db.receipts_for_job(job_id)[0]["vendor"], "Toko B")

    def test_koreksi_dengan_nilai_sama_tidak_dicatat(self):
        job_id, file_id = self._receipt()
        receipt_id = db.add_receipt(file_id, "a.jpg", {"vendor": "Toko A"})
        self.assertFalse(db.update_receipt(receipt_id, "vendor", "Toko A"))
        self.assertEqual(db.corrections_for_job(job_id), [])

    def test_kolom_asing_tidak_boleh_diubah(self):
        _, file_id = self._receipt()
        receipt_id = db.add_receipt(file_id, "a.jpg", {"vendor": "A"})
        with self.assertRaises(ValueError):
            db.update_receipt(receipt_id, "catatan_admin", "x")

    def test_hasil_yang_tidak_ada_ditolak(self):
        with self.assertRaises(LookupError):
            db.update_receipt(9999, "vendor", "x")


class UsageTest(TempDbCase):

    def test_pemakaian_dijumlahkan_per_chat(self):
        db.add_usage(1001, 1, "m", 400, 50)
        db.add_usage(1001, 1, "m", 300, 40)
        hasil = db.usage_since(1001, "2000-01-01T00:00:00+00:00")
        self.assertEqual(hasil["total"], 790)
        self.assertEqual(hasil["calls"], 2)

    def test_pemakaian_chat_lain_tidak_tercampur(self):
        db.add_usage(2002, 1, "m", 5000, 0)
        hasil = db.usage_since(1001, "2000-01-01T00:00:00+00:00")
        self.assertEqual(hasil["total"], 0)


if __name__ == "__main__":
    unittest.main()
