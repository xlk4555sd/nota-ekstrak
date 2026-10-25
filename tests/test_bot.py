"""Tes alur bot: siapa boleh memakai, dan apa yang terjadi saat kirim berkas.

Telegram dan Google Drive dipalsukan. Yang diuji keputusan bot: kapan
menolak, kapan membuat antrean, dan apakah pesan yang keluar masuk akal.

Berkas sengaja TIDAK diunduh di sini — pengunduhan milik worker. Kalau tes
ini mengunduh, uji Telegram bisa menggantung menunggu jaringan.
"""
import unittest
from unittest import mock

from tests.base import TempDbCase
import db
from bot import handler
from services import sources


class _Recorder:
    """Menggantikan bot.telegram supaya tidak ada permintaan jaringan."""

    def __init__(self):
        self.messages = []
        self.documents = []
        self.callbacks = []
        self.answers = []

    def send_message(self, chat_id, text, reply_markup=None, parse_mode="HTML"):
        self.messages.append({"chat": chat_id, "text": text, "markup": reply_markup})
        return {"message_id": len(self.messages)}

    def send_document(self, chat_id, path, filename=None, caption=None):
        self.documents.append({"chat": chat_id, "path": path, "caption": caption})
        return {"message_id": 99}

    def edit_message(self, chat_id, message_id, text, reply_markup=None):
        self.messages.append({"chat": chat_id, "text": text, "markup": reply_markup})

    def answer_callback(self, callback_id, text=None):
        self.answers.append({"id": callback_id, "text": text})


class _HandlerCase(TempDbCase):

    def setUp(self):
        super().setUp()
        self.tg = _Recorder()
        patch = mock.patch.object(handler, "telegram", self.tg)
        patch.start()
        self.addCleanup(patch.stop)

    def say(self, chat_id, **payload):
        message = {"chat": {"id": chat_id}}
        message.update(payload)
        handler.handle_update({"message": message})
        return self.tg.messages[-1]["text"] if self.tg.messages else ""

    def press(self, chat_id, data, text="Selesai #1"):
        handler.handle_update({"callback_query": {
            "id": "cb",
            "data": data,
            "message": {"chat": {"id": chat_id}, "text": text},
        }})


class AksesTest(_HandlerCase):

    def test_chat_belum_terdaftar_ditolak(self):
        teks = self.say(5555, text="/start")
        self.assertIn("belum terdaftar", teks)

    def test_chat_terdaftar_mendapat_penjelasan(self):
        teks = self.say(1001, text="/start")
        self.assertIn("nota.ekstrak", teks)

    def test_help_dan_start_beda_isi(self):
        mulai = self.say(1001, text="/start")
        bantuan = self.say(1001, text="/help")
        self.assertNotEqual(mulai, bantuan)

    def test_teks_biasa_dibalas_penjelasan(self):
        teks = self.say(1001, text="halo apa kabar")
        self.assertIn("nota.ekstrak", teks)


class KirimBerkasTest(_HandlerCase):

    def test_berkas_bukan_pdf_atau_gambar_ditolak(self):
        teks = self.say(1001, document={"file_id": "x", "file_name": "catatan.docx"})
        self.assertIn("belum didukung", teks)

    def test_pdf_membuat_pekerjaan_tanpa_mengunduh(self):
        teks = self.say(1001, document={"file_id": "abc", "file_name": "nota.pdf"})
        self.assertIn("Menunggu antrean", teks)
        job = db.active_job_for(1001)
        self.assertEqual(job["total_files"], 1)
        berkas = db.files_for_job(job["id"])
        self.assertEqual(berkas[0]["remote_id"], "abc")
        self.assertEqual(berkas[0]["path"], "")

    def test_foto_memilih_ukuran_terbesar(self):
        self.say(1001, photo=[
            {"file_id": "kecil", "file_unique_id": "aaa111", "file_size": 100},
            {"file_id": "besar", "file_unique_id": "bbb222", "file_size": 900},
        ])
        job = db.active_job_for(1001)
        self.assertEqual(db.files_for_job(job["id"])[0]["remote_id"], "besar")

    def test_kiriman_baru_ditolak_saat_sedang_dikerjakan(self):
        job_id = db.create_job(1001, "telegram", 1)
        db.set_job_status(job_id, "running")
        teks = self.say(1001, document={"file_id": "abc", "file_name": "nota.jpg"})
        self.assertIn("Masih ada kiriman", teks)

    def test_album_lima_foto_jadi_satu_pekerjaan(self):
        handler.handle_update({"message": {
            "chat": {"id": 1001},
            "media_group_id": "g1",
            "photo": [{"file_id": "f1", "file_unique_id": "u1", "file_size": 500}],
        }})
        handler.handle_update({"message": {
            "chat": {"id": 1001},
            "media_group_id": "g1",
            "photo": [{"file_id": "f2", "file_unique_id": "u2", "file_size": 500}],
        }})
        job = db.active_job_for(1001)
        self.assertEqual(len(db.files_for_job(job["id"])), 2)


class DriveTest(_HandlerCase):

    def test_folder_kosong_ditolak_dengan_jelas(self):
        with mock.patch.object(sources, "list_folder",
                               side_effect=sources.SourceError("tidak ada PDF atau gambar di folder itu")):
            teks = self.say(1001, text="https://drive.google.com/drive/folders/ABC123")
        self.assertIn("tidak ada PDF", teks)

    def test_folder_membuat_pekerjaan(self):
        with mock.patch.object(sources, "list_folder",
                               return_value=[("id1", "a.pdf"), ("id2", "b.jpg")]):
            teks = self.say(1001, text="https://drive.google.com/drive/folders/ABC123")
        self.assertIn("2 berkas", teks)
        self.assertEqual(db.active_job_for(1001)["total_files"], 2)

    def test_link_berkas_tunggal_ditolak(self):
        teks = self.say(1001, text="https://drive.google.com/file/d/XYZ/view")
        self.assertIn("kirim berkasnya langsung", teks)


class PerintahTest(_HandlerCase):

    def test_batal_menghentikan_kiriman(self):
        job_id = db.create_job(1001, "telegram", 2)
        teks = self.say(1001, text="/batal")
        self.assertIn("dihentikan", teks)
        self.assertEqual(db.get_job(job_id)["status"], "cancelled")

    def test_status_menampilkan_sisa_jatah(self):
        teks = self.say(1001, text="/status")
        self.assertIn("Hari ini:", teks)


class TombolTest(_HandlerCase):

    def test_tombol_csv_mengirim_berkas(self):
        job_id = db.create_job(1001, "telegram", 1)
        file_id = db.add_file(job_id, "a.jpg", "/tmp/a.jpg")
        db.add_receipt(file_id, "a.jpg", {"vendor": "A", "total": "1000"})
        self.press(1001, f"csv:{job_id}", text=f"Selesai #{job_id}")
        self.assertEqual(len(self.tg.documents), 1)
        self.assertTrue(str(self.tg.documents[0]["path"]).endswith(".csv"))

    def test_tombol_excel_mengirim_berkas(self):
        job_id = db.create_job(1001, "telegram", 1)
        file_id = db.add_file(job_id, "a.jpg", "/tmp/a.jpg")
        db.add_receipt(file_id, "a.jpg", {"vendor": "A", "total": "1000"})
        self.press(1001, f"xlsx:{job_id}", text=f"Selesai #{job_id}")
        self.assertTrue(str(self.tg.documents[0]["path"]).endswith(".xlsx"))

    def test_tombol_tanpa_hasil_dijawab_jelas(self):
        job_id = db.create_job(1001, "telegram", 1)
        self.press(1001, f"csv:{job_id}", text=f"Selesai #{job_id}")
        self.assertTrue(any("Tidak ada hasil" in m["text"] for m in self.tg.messages))
        self.assertEqual(len(self.tg.documents), 0)

    def test_tombol_hentikan_mengubah_status(self):
        job_id = db.create_job(1001, "telegram", 1)
        self.press(1001, f"cancel:{job_id}", text="antre")
        self.assertEqual(db.get_job(job_id)["status"], "cancelled")

    def test_tombol_dari_chat_lain_ditolak(self):
        # Berkas hasil tidak boleh bisa diambil orang yang tahu nomor pekerjaan.
        job_id = db.create_job(1001, "telegram", 1)
        file_id = db.add_file(job_id, "a.jpg", "/tmp/a.jpg")
        db.add_receipt(file_id, "a.jpg", {"vendor": "A", "total": "1000"})
        self.press(2002, f"csv:{job_id}", text=f"Selesai #{job_id}")
        self.assertEqual(len(self.tg.documents), 0)
        self.assertTrue(any("Tidak ada hasil" in m["text"] for m in self.tg.messages))


if __name__ == "__main__":
    unittest.main()
