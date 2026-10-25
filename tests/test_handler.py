"""Tes penerimaan pesan Telegram.

Yang dijaga:
  - chat yang belum terdaftar tidak bisa memakai bot sama sekali;
  - pesan yang tidak layak tidak membuat antrean terisi;
  - satu chat tidak bisa menumpuk kiriman sebelum yang lama selesai;
  - handler tidak pernah memanggil model (kalau iya, tes ini akan menggantung
    dan biayanya keluar tanpa disadari).
"""
import unittest

import db
from bot import handler, telegram
from tests.base import FakeTelegram, TempDbCase


class HandlerCase(TempDbCase):
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

    def kirim(self, teks=None, chat=1001, **tambahan):
        pesan = {"chat": {"id": chat}, "message_id": 11}
        if teks is not None:
            pesan["text"] = teks
        pesan.update(tambahan)
        handler.handle_update({"message": pesan})
        return self.fake.messages[-1]["text"] if self.fake.messages else ""

    def test_chat_asing_ditolak_dan_idnya_disebut(self):
        teks = self.kirim("/start", chat=555)
        self.assertIn("belum terdaftar", teks)
        self.assertIn("555", teks)
        self.assertIsNone(db.active_job_for(555))

    def test_start_menjelaskan_batas(self):
        teks = self.kirim("/start")
        self.assertIn("nota.ekstrak", teks)
        self.assertIn("MB", teks)

    def test_dokumen_pdf_masuk_antrean(self):
        teks = self.kirim(document={"file_id": "ABC", "file_name": "nota.pdf"})
        self.assertIn("Menunggu antrean", teks)
        pekerjaan = db.active_job_for(1001)
        self.assertEqual(pekerjaan["status"], "pending")
        self.assertEqual(pekerjaan["total_files"], 1)
        berkas = db.pending_files(pekerjaan["id"])
        self.assertEqual(berkas[0]["remote_id"], "ABC")

    def test_berkas_ekstensi_aneh_ditolak_tanpa_antrean(self):
        teks = self.kirim(document={"file_id": "X", "file_name": "virus.exe"})
        self.assertIn("belum didukung", teks)
        self.assertIsNone(db.active_job_for(1001))

    def test_foto_memakai_ukuran_paling_besar(self):
        self.kirim(photo=[{"file_id": "kecil", "file_size": 100},
                          {"file_id": "besar", "file_size": 5000}])
        pekerjaan = db.active_job_for(1001)
        self.assertEqual(db.pending_files(pekerjaan["id"])[0]["remote_id"], "besar")

    def test_dua_berkas_selama_menunggu_masuk_satu_pekerjaan(self):
        # Album Telegram datang sebagai beberapa pesan; semuanya harus jadi
        # satu tabel, bukan satu tabel per foto.
        self.kirim(document={"file_id": "S1", "file_name": "a.pdf"})
        self.kirim(document={"file_id": "S2", "file_name": "b.pdf"})
        self.assertEqual(len(db.list_jobs()), 1)
        pekerjaan = db.active_job_for(1001)
        self.assertEqual(len(db.files_for_job(pekerjaan["id"])), 2)

    def test_kiriman_baru_ditolak_saat_yang_lama_sedang_dikerjakan(self):
        self.kirim(document={"file_id": "S1", "file_name": "a.pdf"})
        pekerjaan = db.active_job_for(1001)
        db.set_job_status(pekerjaan["id"], "running")
        teks = self.kirim(document={"file_id": "S2", "file_name": "b.pdf"})
        self.assertIn("Masih ada kiriman", teks)
        self.assertEqual(len(db.list_jobs()), 1)

    def test_link_bukan_drive_mendapat_panduan(self):
        teks = self.kirim("https://example.com/nota.pdf")
        self.assertIn("kirim foto nota", teks.lower())
        self.assertIsNone(db.active_job_for(1001))

    def test_teks_biasa_tidak_membuat_antrean(self):
        self.kirim("halo selamat pagi")
        self.assertIsNone(db.active_job_for(1001))

    def test_batal_menghentikan_kiriman(self):
        self.kirim(document={"file_id": "S1", "file_name": "a.pdf"})
        pekerjaan = db.active_job_for(1001)
        teks = self.kirim("/batal")
        self.assertIn("dihentikan", teks)
        self.assertEqual(db.get_job(pekerjaan["id"])["status"], "cancelled")

    def test_batal_tanpa_kiriman_menjawab_sopan(self):
        self.assertIn("Tidak ada kiriman", self.kirim("/batal"))

    def test_jatah_nota_habis_ditolak_sebelum_masuk_antrean(self):
        db.upsert_chat(1001, allowed=1, daily_receipts=0, daily_tokens=200_000)
        teks = self.kirim(document={"file_id": "S1", "file_name": "a.pdf"})
        self.assertIn("habis", teks)
        self.assertEqual(db.list_jobs(), [])

    def test_perintah_bot_di_grup_tetap_dikenali(self):
        self.assertIn("Perintah", self.kirim("/help@nota_bot"))


class TombolCase(HandlerCase):
    """Kelas terpisah supaya tombol diuji sekali, bukan diulang per kasus pesan."""

    # Tes pesan dari kelas induk tidak perlu dijalankan ulang di sini.
    test_chat_asing_ditolak_dan_idnya_disebut = None
    test_start_menjelaskan_batas = None
    test_dokumen_pdf_masuk_antrean = None
    test_berkas_ekstensi_aneh_ditolak_tanpa_antrean = None
    test_foto_memakai_ukuran_paling_besar = None
    test_kiriman_kedua_menunggu_yang_pertama = None
    test_link_bukan_drive_mendapat_panduan = None
    test_teks_biasa_tidak_membuat_antrean = None
    test_batal_menghentikan_kiriman = None
    test_batal_tanpa_kiriman_menjawab_sopan = None
    test_jatah_nota_habis_ditolak_sebelum_masuk_antrean = None
    test_perintah_bot_di_grup_tetap_dikenali = None

    def tekan(self, data, chat=1001):
        handler.handle_update({"callback_query": {
            "id": "cb1", "data": data,
            "message": {"message_id": 5, "chat": {"id": chat}},
        }})

    def test_tombol_hentikan_mengubah_status(self):
        self.kirim(document={"file_id": "S1", "file_name": "a.pdf"})
        pekerjaan = db.active_job_for(1001)
        self.tekan(f"cancel:{pekerjaan['id']}")
        self.assertEqual(db.get_job(pekerjaan["id"])["status"], "cancelled")

    def test_unduh_csv_tanpa_hasil_tidak_mengirim_berkas(self):
        pekerjaan = db.active_job_for(1001) or db.get_job(
            db.create_job(1001, "telegram", 1))
        self.tekan(f"csv:{pekerjaan['id']}")
        self.assertEqual(self.fake.documents, [])
        self.assertIn("Tidak ada hasil", self.fake.messages[-1]["text"])

    def test_tombol_rusak_tidak_melempar(self):
        self.tekan("csv:bukan-angka")
        self.tekan("")
        self.tekan("entah:1")


if __name__ == "__main__":
    unittest.main()
