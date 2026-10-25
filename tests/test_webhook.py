"""Tes webhook dan titik kesehatan.

Webhook adalah satu-satunya pintu masuk dari internet, jadi yang diuji di
sini adalah penolakan: alamat rahasia yang salah, isi yang bukan JSON, dan
memastikan endpoint tetap hidup walau sekitarnya belum dikonfigurasi.
"""
import unittest
from unittest import mock

import config
import db
from tests.base import TempDbCase


class WebhookTest(TempDbCase):

    def setUp(self):
        super().setUp()
        import app as app_module
        config.TELEGRAM_WEBHOOK_SECRET = "rahasia-uji"
        self.client = app_module.create_app(start_worker=False).test_client()

    def tearDown(self):
        config.TELEGRAM_WEBHOOK_SECRET = ""
        super().tearDown()

    def test_alamat_rahasia_salah_ditolak(self):
        response = self.client.post("/telegram/salah", json={"message": {}})
        self.assertEqual(response.status_code, 404)

    def test_kunci_belum_diisi_berarti_tidak_ada_jalur_masuk(self):
        config.TELEGRAM_WEBHOOK_SECRET = ""
        response = self.client.post("/telegram/", json={"message": {}})
        self.assertEqual(response.status_code, 404)

    def test_isi_bukan_json_tetap_dijawab_ok(self):
        # Membalas galat membuat Telegram mengirim ulang terus. Lebih baik
        # mengabaikan isi yang tidak dipahami dan mencatatnya di log.
        response = self.client.post("/telegram/rahasia-uji", data="bukan json",
                                    content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])

    def test_permintaan_sah_diteruskan_ke_handler(self):
        with mock.patch("bot.handler.handle_update") as handle:
            response = self.client.post("/telegram/rahasia-uji", json={"message": {}})
        self.assertEqual(response.status_code, 200)
        handle.assert_called_once()

    def test_kesalahan_di_handler_tetap_dijawab_ok(self):
        from bot import handler
        with mock.patch.object(handler, "_handle_message", side_effect=RuntimeError("rusak")):
            response = self.client.post("/telegram/rahasia-uji", json={"message": {}})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])

    def test_health_menyebut_alat_yang_belum_diisi(self):
        # Nilainya dikosongkan sengaja: di mesin pengembang .env sudah berisi,
        # dan tes tidak boleh bergantung pada isi berkas rahasia.
        with mock.patch.object(config, "RIVER_API_KEY", ""):
            response = self.client.get("/healthz")
        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertIn("RIVER_API_KEY", body["missing"])


class FactoryTest(TempDbCase):

    def test_worker_tidak_jalan_saat_dimatikan(self):
        import app as app_module
        with mock.patch.object(app_module, "Worker") as worker:
            app_module.create_app(start_worker=False)
        worker.assert_not_called()

    def test_worker_jalan_saat_diminta(self):
        import app as app_module
        with mock.patch.object(app_module, "Worker") as worker:
            app_module.create_app(start_worker=True)
        self.assertTrue(worker.return_value.start.called)


if __name__ == "__main__":
    unittest.main()
