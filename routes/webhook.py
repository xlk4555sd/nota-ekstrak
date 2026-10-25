"""Titik kesehatan: dipakai untuk tahu container masih hidup.

Yang dibaca dari sini hanya hal yang aman ditampilkan: jumlah pekerjaan dan
nama variabel yang belum diisi. Isi rahasianya tidak pernah ikut keluar.
"""
import logging

from flask import Blueprint

import config
import db
from bot import handler
from flask import Blueprint, request

log = logging.getLogger("nota.webhook")

bp = Blueprint("webhook", __name__)

# Alamat dibaca dari pengaturan saat permintaan datang, bukan dibekukan saat
# import: tes dan jumlah lingkungan lain mengganti kuncinya.
PATH = "/telegram/<secret>"


@bp.post("/telegram/<secret>")
def telegram_update(secret):
    if not config.TELEGRAM_WEBHOOK_SECRET or secret != config.TELEGRAM_WEBHOOK_SECRET:
        # Sengaja tidak memberi petunjuk apa pun; 404 sama seperti alamat lain.
        return "", 404

    update = request.get_json(silent=True)
    if not isinstance(update, dict):
        log.warning("update bukan objek JSON, diabaikan")
        return {"ok": True}, 200

    handler.handle_update(update)
    return {"ok": True}, 200


@bp.get("/healthz")
def healthz():
    pengantre = db.count_jobs_by_status()
    return {
        "ok": True,
        "model": config.MODEL_NAME,
        "pending": pengantre.get("pending", 0),
        "running": pengantre.get("running", 0),
        "missing": config.missing_required(),
    }


def bind(app):
    app.register_blueprint(bp)
    app.logger.debug("jalur masuk: %s", PATH)
