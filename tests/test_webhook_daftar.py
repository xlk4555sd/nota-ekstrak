"""Pendaftaran webhook: alamat publik ikut berpindah saat tunnel berganti.

Masalah yang dijaga di sini nyata dan gejalanya menyesatkan. Cloudflare Quick
Tunnel memberi alamat baru setiap kali dinyalakan. Kalau webhook lama tidak
diperbarui, Telegram terus mengirim ke alamat mati: proses bot hidup, basis
data sehat, tidak ada galat di log — tapi bot tidak pernah menerima pesan.
"""
import config
import serve
from bot import telegram
from tests.base import TempDbCase


class WebhookTest(TempDbCase):
    def setUp(self):
        super().setUp()
        self.asli_url = serve.config.PUBLIC_URL
        self.asli_secret = serve.config.TELEGRAM_WEBHOOK_SECRET
        self.didaftarkan = []
        self._asli_set = telegram.set_webhook

        def palsu(url):
            self.didaftarkan.append(url)
            return {"ok": True}

        telegram.set_webhook = palsu

    def tearDown(self):
        telegram.set_webhook = self._asli_set
        serve.config.PUBLIC_URL = self.asli_url
        serve.config.TELEGRAM_WEBHOOK_SECRET = self.asli_secret
        super().tearDown()

    def test_alamat_lengkap_didaftarkan(self):
        serve.config.PUBLIC_URL = "https://contoh.trycloudflare.com"
        serve.config.TELEGRAM_WEBHOOK_SECRET = "rahasia123"
        serve._daftarkan_webhook()
        self.assertEqual(self.didaftarkan,
                         ["https://contoh.trycloudflare.com/telegram/rahasia123"])

    def test_garis_miring_di_akhir_tidak_menggandakan(self):
        serve.config.PUBLIC_URL = "https://contoh.trycloudflare.com/"
        serve.config.TELEGRAM_WEBHOOK_SECRET = "rahasia123"
        serve._daftarkan_webhook()
        self.assertEqual(self.didaftarkan,
                         ["https://contoh.trycloudflare.com/telegram/rahasia123"])

    def test_tanpa_public_url_tidak_mendaftar(self):
        """Pemasangan yang mendaftar webhook manual tidak boleh diganggu."""
        serve.config.PUBLIC_URL = ""
        serve._daftarkan_webhook()
        self.assertEqual(self.didaftarkan, [])

    def test_gagal_daftar_tidak_mematikan_layanan(self):
        """Telegram bisa saja menolak; bot harus tetap hidup."""
        serve.config.PUBLIC_URL = "https://contoh.trycloudflare.com"
        serve.config.TELEGRAM_WEBHOOK_SECRET = "rahasia123"

        def meledak(url):
            raise telegram.TelegramError("jaringan putus")

        telegram.set_webhook = meledak
        serve._daftarkan_webhook()   # tidak boleh melempar
