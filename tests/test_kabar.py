"""Tes pengabaran setelah pekerjaan selesai.

Dua kesalahan yang pernah terjadi di Telegram sungguhan dan dijaga di sini:

1. Satu foto dibalas dua kali ("Diterima" muncul dobel).
2. Hasil akhir tidak pernah dikirim — worker selesai tanpa mengabari chat,
   jadi user hanya melihat "masuk antrean" lalu tidak tahu apa-apa lagi.
"""
import unittest
from pathlib import Path
from unittest import mock

import db
from bot import handler, reply
from tests.base import TempDbCase, fake_model


def _foto(file_id="f1", unique="uniq1234"):
    return [{"file_id": file_id, "file_unique_id": unique, "file_size": 900}]


class SekaliKabarTest(TempDbCase):
    """Satu kiriman hanya boleh menghasilkan satu pesan 'Diterima'."""

    CHAT = 1001

    def test_satu_foto_dibalas_sekali(self):
        with mock.patch.object(handler.telegram, "send_message") as kirim:
            handler._handle_photo(self.CHAT, _foto(), group_id=None)

        diterima = [c for c in kirim.call_args_list if "Menunggu antrean" in str(c)]
        self.assertEqual(len(diterima), 1, f"pesan terkirim: {kirim.call_args_list}")


class KabarSelesaiTest(TempDbCase):
    """Worker wajib mengabari chat saat pekerjaan selesai."""

    CHAT = 1001

    def _siapkan(self):
        berkas = Path(self.data_dir) / "nota.png"
        from PIL import Image
        Image.new("RGB", (600, 800), "white").save(berkas)
        job_id = db.create_job(self.CHAT, "telegram", 1)
        db.add_file(job_id, "nota.png", str(berkas))
        return job_id

    def test_worker_mengirim_hasil_dan_tombol_unduh(self):
        from worker import Worker

        job_id = self._siapkan()
        with fake_model({"vendor": "Toko A", "total": "1000", "mata_uang": "IDR"}):
            with mock.patch.object(handler.telegram, "send_message"):
                from bot import telegram as tg
                with mock.patch.object(tg, "send_message") as kirim:
                    job = db.claim_next_job()
                    Worker().run_job(job)

        teks = [c for c in kirim.call_args_list if c.args and isinstance(c.args[1], str)]
        self.assertTrue(teks, "worker tidak mengirim pesan apa pun")
        pesan = " ".join(c.args[1] for c in teks)
        self.assertIn("Selesai", pesan)

        tombol = [c.kwargs.get("reply_markup") for c in kirim.call_args_list]
        self.assertTrue(any(t for t in tombol), "tombol unduh tidak ikut dikirim")

    def test_pekerjaan_gagal_mengirim_pesan_gagal(self):
        from worker import Worker

        job_id = db.create_job(self.CHAT, "telegram", 1)
        # Berkas yang tidak ada di disk: unduhan/persiapan gagal total.
        db.add_file(job_id, "hilang.png", "/tidak/ada/hilang.png")

        from bot import telegram as tg
        with mock.patch.object(tg, "send_message") as kirim:
            job = db.claim_next_job()
            Worker().run_job(job)

        pesan = " ".join(c.args[1] for c in kirim.call_args_list if c.args and isinstance(c.args[1], str))
        self.assertIn("Gagal", pesan)


if __name__ == "__main__":
    unittest.main()
