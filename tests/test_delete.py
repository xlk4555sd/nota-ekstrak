"""Tes /help dan /delete.

Yang dijaga:
  - /help menjelaskan cara pakai, bukan cuma daftar perintah;
  - /delete tidak pernah menghapus milik chat lain, walau nomornya benar;
  - pekerjaan yang masih berjalan tidak bisa dihapus di tengah jalan;
  - hapus semua butuh konfirmasi, jadi salah ketik tidak menghabiskan riwayat;
  - berkas di disk dan hasil CSV ikut hilang, bukan cuma baris di tabel.
"""
import unittest
from pathlib import Path

import config
import db
from bot import handler, telegram
from tests.base import FakeTelegram, TempDbCase


class BantuanCase(TempDbCase):
    def setUp(self):
        super().setUp()
        self.fake = FakeTelegram()
        self._asli = (telegram.send_message, telegram.answer_callback,
                      telegram.edit_message, telegram.send_document)
        telegram.send_message = self.fake.send_message
        telegram.send_document = self.fake.send_document
        telegram.answer_callback = self.fake.answer_callback
        telegram.edit_message = lambda *a, **k: {"message_id": 1}

    def tearDown(self):
        (telegram.send_message, telegram.answer_callback,
         telegram.edit_message, telegram.send_document) = self._asli
        super().tearDown()

    def ketik(self, teks, chat=1001):
        handler.handle_update({"message": {"chat": {"id": chat}, "message_id": 1,
                                           "text": teks}})
        return self.fake.last_text()

    def siapkan_pekerjaan(self, chat=1001, status="done", total=2):
        job_id = db.create_job(chat, "upload", total)
        for i in range(total):
            db.add_file(job_id, f"remote-{i}", f"nota{i}.pdf", 1000)
        db.set_job_status(job_id, status)
        return job_id

    def buat_berkas(self, job_id):
        """Berkas dan hasil yang seharusnya ikut terhapus."""
        folder = Path(config.UPLOAD_DIR) / f"job{job_id}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "nota.pdf").write_bytes(b"x" * 2048)
        Path(config.EXPORT_DIR).mkdir(parents=True, exist_ok=True)
        (Path(config.EXPORT_DIR) / f"nota_{job_id}.csv").write_text("a,b\n")
        (Path(config.EXPORT_DIR) / f"nota_{job_id}.xlsx").write_bytes(b"PK")
        return folder


class HelpCase(BantuanCase):
    def test_help_menjelaskan_cara_kirim_bukan_cuma_daftar_perintah(self):
        teks = self.ketik("/help")
        for bagian in ("Mengirim nota", "Mengambil hasil", "periksa", "Batas"):
            self.assertIn(bagian, teks)

    def test_help_menyebut_semua_perintah_termasuk_delete(self):
        teks = self.ketik("/help")
        for perintah in ("/help", "/status", "/batal", "/delete"):
            self.assertIn(perintah, teks)

    def test_help_tanpa_jargon_teknis(self):
        teks = self.ketik("/help").lower()
        for kata in ("api", "endpoint", "webhook", "json", "token", "sql"):
            self.assertNotIn(kata, teks)

    def test_help_tetap_menyebut_batas_ukuran(self):
        teks = self.ketik("/help")
        self.assertIn("MB", teks)
        self.assertIn(str(config.MAX_PDF_PAGES), teks)


class DeleteCase(BantuanCase):
    def test_tanpa_argumen_menampilkan_daftar(self):
        job_id = self.siapkan_pekerjaan()
        teks = self.ketik("/delete")
        self.assertIn(f"#{job_id}", teks)
        self.assertIn("/delete NOMOR", teks)

    def test_hapus_satu_menghilangkan_baris_dan_berkas(self):
        job_id = self.siapkan_pekerjaan()
        folder = self.buat_berkas(job_id)

        teks = self.ketik(f"/delete {job_id}")

        self.assertIn("Terhapus", teks)
        self.assertIsNone(db.get_job(job_id))
        self.assertFalse(folder.exists())
        self.assertFalse((Path(config.EXPORT_DIR) / f"nota_{job_id}.csv").exists())
        self.assertFalse((Path(config.EXPORT_DIR) / f"nota_{job_id}.xlsx").exists())

    def test_nomor_dengan_pagar_tetap_dikenali(self):
        job_id = self.siapkan_pekerjaan()
        teks = self.ketik(f"/delete #{job_id}")
        self.assertIn("Terhapus", teks)
        self.assertIsNone(db.get_job(job_id))

    def test_tidak_bisa_menghapus_milik_chat_lain(self):
        # Di sinilah kesalahan paling mahal kalau batas kepemilikan lupa.
        db.upsert_chat(2002, allowed=1, daily_receipts=100, daily_tokens=200_000)
        milik_orang = self.siapkan_pekerjaan(chat=2002)

        teks = self.ketik(f"/delete {milik_orang}", chat=1001)

        self.assertIn("bukan milikmu", teks)
        self.assertIsNotNone(db.get_job(milik_orang))

    def test_pekerjaan_berjalan_tidak_bisa_dihapus(self):
        job_id = self.siapkan_pekerjaan(status="running")
        teks = self.ketik(f"/delete {job_id}")
        self.assertIn("masih berjalan", teks)
        self.assertIsNotNone(db.get_job(job_id))

    def test_nomor_asing_ditolak_dengan_sopan(self):
        teks = self.ketik("/delete 99999")
        self.assertIn("tidak ada", teks)

    def test_argumen_ngawur_diberi_cara_pakai(self):
        teks = self.ketik("/delete hapusdong")
        self.assertIn("/delete NOMOR", teks)

    def test_daftar_kosong_dijelaskan_bukan_diam(self):
        teks = self.ketik("/delete")
        self.assertIn("Belum ada", teks)

    def test_hapus_semua_butuh_konfirmasi_dua_langkah(self):
        satu = self.siapkan_pekerjaan()
        dua = self.siapkan_pekerjaan()

        tanya = self.ketik("/delete semua")
        self.assertIn("Hapus semua", tanya)
        self.assertIsNotNone(db.get_job(satu))   # belum ada yang hilang
        self.assertIsNotNone(db.get_job(dua))

        selesai = self.ketik("/delete ya")
        self.assertIn("2 kiriman terhapus", selesai)
        self.assertIsNone(db.get_job(satu))
        self.assertIsNone(db.get_job(dua))

    def test_hapus_semua_melewati_yang_masih_berjalan(self):
        selesai = self.siapkan_pekerjaan()
        berjalan = self.siapkan_pekerjaan(status="running")

        self.ketik("/delete semua")
        teks = self.ketik("/delete ya")

        self.assertIsNone(db.get_job(selesai))
        self.assertIsNotNone(db.get_job(berjalan))
        self.assertIn(f"#{berjalan}", teks)

    def test_hasil_tabel_ikut_terhapus(self):
        job_id = db.create_job(1001, "upload", 1)
        file_id = db.add_file(job_id, "r1", "nota.pdf", 100)
        db.add_receipt(file_id, "nota.pdf",
                       {"vendor": "Toko", "tanggal": "01/01/2026",
                        "nomor_nota": "A1", "total": "1000", "mata_uang": "IDR"})
        db.set_job_status(job_id, "done")
        self.assertEqual(len(db.receipts_for_job(job_id)), 1)

        self.ketik(f"/delete {job_id}")

        self.assertEqual(db.receipts_for_job(job_id), [])

    def test_pemakaian_model_ikut_dibersihkan(self):
        job_id = self.siapkan_pekerjaan(total=1)
        db.add_usage(1001, job_id, "model-uji", 400, 50)

        self.ketik(f"/delete {job_id}")

        from db import connect
        sisa = connect().execute(
            "SELECT COUNT(*) AS n FROM usage WHERE job_id = ?", (job_id,)
        ).fetchone()["n"]
        self.assertEqual(sisa, 0)

    def test_chat_asing_tidak_bisa_memakai_delete_sama_sekali(self):
        teks = self.ketik("/delete 1", chat=555)
        self.assertIn("belum terdaftar", teks)


if __name__ == "__main__":
    unittest.main()
