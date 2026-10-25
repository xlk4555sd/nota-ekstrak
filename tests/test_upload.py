"""Tes pengiriman berkas lewat Telegram.

Yang dijaga: isi multipart. Kesalahan di sini muncul sebagai 400 dari Telegram
tanpa penjelasan, jadi bagian yang paling mudah salah diuji langsung di sini —
tanpa jaringan, dengan `urlopen` dipalsukan.
"""
import io
import json
import unittest
from pathlib import Path
from unittest import mock

from bot import telegram


class Izin:
    """Pengganti urlopen: mencatat isi permintaan, membalas seolah dari Telegram."""

    def __init__(self, terkirim):
        self.terkirim = terkirim

    def __call__(self, request, timeout=None):
        self.terkirim.append(request)
        return io.BytesIO(json.dumps({"ok": True, "result": {"message_id": 1}}).encode())

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class UnggahTest(unittest.TestCase):

    def setUp(self):
        self.terkirim = []
        self._patch = mock.patch("urllib.request.urlopen", side_effect=Izin(self.terkirim))
        self._patch.start()

    def tearDown(self):
        self._patch.stop()

    def test_setiap_isian_punya_pembatas_sendiri(self):
        berkas = Path(__file__).parent / "contoh_unggah.csv"
        berkas.write_text("vendor,total\nA,9\n")

        telegram.send_document(1234, berkas)

        badan = self.terkirim[0].data
        isi_kepala = self.terkirim[0].headers
        batas = isi_kepala["Content-type"].split("boundary=")[1].encode()

        # chat_id dan berkas = dua bagian, jadi pembatas muncul minimal 3 kali
        # (bukalah tiap bagian + penutup).
        self.assertGreaterEqual(badan.count(b"--" + batas), 3)
        self.assertIn(b'name="chat_id"', badan)
        self.assertIn(b'name="document"; filename="contoh_unggah.csv"', badan)
        self.assertTrue(badan.rstrip().endswith(b"--" + batas + b"--"))

        berkas.unlink()

    def test_caption_dan_berkas_sama_sama_terkirim(self):
        berkas = Path(__file__).parent / "contoh_unggah2.csv"
        berkas.write_text("a\n1\n")

        telegram.send_document(1234, berkas, caption="<b>Hasil</b>")

        badan = self.terkirim[0].data
        batas = self.terkirim[0].headers["Content-type"].split("boundary=")[1].encode()
        self.assertIn(b'name="caption"', badan)
        self.assertIn(b'name="parse_mode"', badan)
        self.assertIn(b'name="document"', badan)
        self.assertGreaterEqual(badan.count(b"--" + batas), 4)

        berkas.unlink()

    def test_telegram_menolak_dijadikan_galat_yang_jelas(self):
        berkas = Path(__file__).parent / "contoh_unggah3.csv"
        berkas.write_text("a\n1\n")

        salah = io.BytesIO(json.dumps({"ok": False, "description": "Bad Request"}).encode())
        with mock.patch("urllib.request.urlopen", return_value=salah):
            with self.assertRaises(telegram.TelegramError) as ctx:
                telegram.send_document(1234, berkas)
        self.assertIn("Bad Request", str(ctx.exception))

        berkas.unlink()


if __name__ == "__main__":
    unittest.main()
