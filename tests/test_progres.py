"""Tes pesan progres yang berubah sendiri.

Yang dijaga di sini adalah keluhan paling wajar dari user: "sudah kirim,
kok diam?". Pesan antrean harus muncul seketika, lalu berubah jadi
"memproses" saat worker mulai, tanpa menambah pesan baru di chat.
"""

import unittest
from unittest import mock

import db
import worker
from bot import reply
from tests.base import TempDbCase


class ProgresTest(TempDbCase):
    CHAT = 4242

    def _buat_job(self, total=3):
        job_id = db.create_job(self.CHAT, "telegram", total)
        for i in range(total):
            db.add_file(job_id, f"foto_{i}.jpg", path="")
        db.set_job_total(job_id, total)
        return db.get_job(job_id)

    def test_pesan_antrean_dikirim_dan_nomornya_disimpan(self):
        job = self._buat_job(2)
        job = db.get_job(job["id"])
        teks = reply.antre_text(job)
        self.assertIn("Menunggu antrean", teks)
        self.assertIn("0 dari 2", teks)

    def test_progres_disunting_bukan_dikirim_baru(self):
        job = self._buat_job(2)
        db.set_job_progress_message(job["id"], 555)
        db.set_job_total(job["id"], 2)
        db.bump_job_progress(job["id"])

        with mock.patch("bot.telegram.edit_message") as sunting, \
             mock.patch("bot.telegram.send_message") as kirim:
            worker.Worker()._tampilkan_progres(job["id"], paksa=True)

        self.assertEqual(kirim.call_count, 0, "progres tidak boleh jadi pesan baru")
        self.assertEqual(sunting.call_count, 1)
        chat, message_id, teks = sunting.call_args.args
        self.assertEqual(message_id, 555)
        self.assertIn("Memproses", teks)
        self.assertIn("1 dari 2", teks)

    def test_jeda_menahan_suntingan_beruntun(self):
        """Telegram membatasi suntingan; dua kali berturut-turut harus ditahan."""
        job = self._buat_job(1)
        db.set_job_progress_message(job["id"], 777)

        with mock.patch("bot.telegram.edit_message") as sunting:
            w = worker.Worker()
            w._tampilkan_progres(job["id"], paksa=True)
            w._tampilkan_progres(job["id"])          # terlalu cepat, harus dilewati

        self.assertEqual(sunting.call_count, 1)

    def test_tanpa_pesan_progres_tidak_melempar(self):
        """Pekerjaan dari sumber lain belum tentu punya pesan progres."""
        job = self._buat_job(1)
        worker.Worker()._tampilkan_progres(job["id"], paksa=True)  # tidak boleh error

    def test_selesai_menggantikan_baris_terakhir(self):
        job = self._buat_job(2)
        db.bump_job_progress(job["id"])
        db.bump_job_progress(job["id"])
        job = db.get_job(job["id"])
        teks = reply.progress_text(job)
        self.assertIn("Merapikan hasil", teks)
        self.assertIn("2 dari 2", teks)

    def test_bar_tidak_pernah_melewati_total(self):
        """Data sesaat bisa membuat done > total; tampilannya tidak boleh aneh."""
        teks = reply._bar(6, 3)
        self.assertEqual(len(teks), 10)
        self.assertEqual(teks.count("█"), 10)

    def test_halaman_pdf_menambah_batas_atas(self):
        """PDF 3 halaman = 3 nota, jadi progres harus 1..3, bukan 1..1."""
        job = self._buat_job(1)          # satu berkas PDF
        db.set_job_total(job["id"], (db.get_job(job["id"])["total_files"] or 0) + 2)
        db.bump_job_progress(job["id"])
        job = db.get_job(job["id"])
        self.assertEqual(job["total_files"], 3)
        self.assertIn("1 dari 3", reply.progress_text(job))


if __name__ == "__main__":
    unittest.main()
