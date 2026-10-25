"""Application factory. Satu tempat untuk merangkai semuanya.

Tidak ada pekerjaan berat di sini: route hanya memvalidasi lalu menyerahkan
ke service. Kalau ada yang ingin ditelusuri, mulai dari file ini dan ikuti
panggilannya.
"""
import logging
import os

from flask import Flask

import config
import db
from routes import webhook
from worker import Worker


def create_app(start_worker=None):
    app = Flask(__name__)
    config.ensure_dirs()
    db.init_db()

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    missing = config.missing_required()
    if missing:
        app.logger.warning(
            "belum diisi: %s — bot tidak akan jalan sampai diisi", ", ".join(missing)
        )

    # Worker hanya dijalankan proses utama. Dengan gunicorn, setiap worker
    # adalah proses terpisah; menjalankan pengantre di semuanya berarti
    # beberapa pengantre berebut pekerjaan yang sama. Karena itu jumlah proses
    # di produksi harus 1 (lihat Dockerfile).
    if start_worker is None:
        start_worker = not missing and os.environ.get("NOTA_NO_WORKER") != "1"
    if start_worker:
        Worker().start()

    webhook.bind(app)
    return app
