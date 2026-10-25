"""Titik masuk untuk menjalankan bot sebagai layanan.

Dipakai oleh `bin/jalankan.py`? Tidak — berkas ini adalah yang dijalankan
langsung: `python serve.py`.

Kenapa tidak memakai `flask run`: perintah itu untuk pengembangan. Di sini ada
dua hal yang harus hidup berdampingan dalam satu proses — penerima pesan
Telegram (webhook) dan pengolah antrean (worker). Menjalankannya terpisah
membuat keduanya berebut database yang sama tanpa alasan.
"""
import os
import sys

import config
from app import create_app


def _secret_webhook():
    """Pastikan alamat webhook tidak kosong.

    Alamat ini satu-satunya pintu masuk dari Telegram. Kalau kosong, siapa pun
    yang tahu bentuk alamatnya bisa menyuruh bot memproses apa saja.
    """
    if config.TELEGRAM_WEBHOOK_SECRET:
        return
    secret = os.urandom(24).hex()
    config.TELEGRAM_WEBHOOK_SECRET = secret
    print(
        "TELEGRAM_WEBHOOK_SECRET belum diisi; memakai nilai acak untuk sesi ini.\n"
        "Tempel ini ke .env supaya alamatnya tidak berubah tiap kali start:\n"
        f"TELEGRAM_WEBHOOK_SECRET={secret}",
        file=sys.stderr,
    )


def _daftarkan_webhook():
    """Daftarkan alamat publik ke Telegram kalau PUBLIC_URL diisi.

    Tanpa ini, setiap kali tunnel sementara dinyalakan ulang alamatnya
    berganti, webhook lama menunjuk ke tempat mati, dan bot tampak diam
    padahal prosesnya sehat. Kegagalan di sini tidak boleh mematikan layanan:
    webhook bisa didaftarkan manual kapan saja.
    """
    if not config.PUBLIC_URL:
        return
    alamat = f"{config.PUBLIC_URL.rstrip('/')}/telegram/{config.TELEGRAM_WEBHOOK_SECRET}"
    try:
        from bot import telegram
        telegram.set_webhook(alamat)
        print(f"[webhook] terdaftar: {alamat}", flush=True)
    except Exception as exc:
        print(f"[webhook] gagal mendaftar ({exc}); daftarkan manual dengan setWebhook",
              file=sys.stderr)


def main():
    _secret_webhook()
    _daftarkan_webhook()

    port = int(os.environ.get("PORT", "2785"))
    app = create_app()

    # Pembersih berkas lama ikut hidup bersama layanan. Kalau dibiarkan
    # terpisah, ia akan terlupa dan folder unggahan terus membesar.
    import cleanup
    cleanup.mulai()

    # Werkzeug cukup di sini: satu proses, sedikit permintaan (hanya Telegram).
    # Gunicorn akan menggandakan proses dan menjalankan dua pengantre.
    app.run(host="127.0.0.1", port=port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
