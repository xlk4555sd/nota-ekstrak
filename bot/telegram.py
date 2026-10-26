"""Semua pembicaraan dengan Telegram ada di sini.

Tidak ada pustaka bot. Permintaannya cuma beberapa: kirim pesan, sunting pesan,
kirim berkas, ambil berkas. Memakai urllib membuat ketergantungan tetap nol
dan mudah dibaca ulang.
"""
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import config

log = logging.getLogger("nota.telegram")

TIMEOUT = 30


class TelegramError(Exception):
    pass


def set_webhook(url):
    """Daftarkan alamat webhook ke Telegram.

    Dipanggil `serve.py` saat start kalau PUBLIC_URL diisi. Tanpa ini, tunnel
    sementara yang alamatnya berganti akan meninggalkan webhook mati, dan
    gejalanya menyesatkan: prosesnya hidup, tapi bot tidak menerima apa pun.
    """
    return _call("setWebhook", {"url": url, "drop_pending_updates": False})


def webhook_info():
    """Keadaan webhook sekarang. Dipakai saat memeriksa kenapa bot diam."""
    return _call("getWebhookInfo", {})


# Menu perintah yang muncul di tombol "/" aplikasi Telegram. Didaftarkan sekali
# lewat kode, bukan diklik manual di BotFather, supaya perintah baru
# (/delete) ikut muncul tanpa langkah tambahan yang mudah terlupa.
_PERINTAH = [
    {"command": "help", "description": "Cara pakai, langkah demi langkah"},
    {"command": "status", "description": "Kiriman yang berjalan dan sisa jatah"},
    {"command": "batal", "description": "Hentikan kiriman yang sedang berjalan"},
    {"command": "delete", "description": "Hapus kiriman yang sudah selesai"},
    {"command": "start", "description": "Mulai dari awal"},
]


def set_commands():
    """Pasang daftar perintah ke menu Telegram.

    Gagal memasang menu bukan alasan bot berhenti: perintahnya tetap bisa
    diketik. Karena itu kegagalannya hanya dicatat, tidak dilempar.
    """
    try:
        return _call("setMyCommands", {"commands": _PERINTAH})
    except TelegramError:
        return None


def send_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _call("sendMessage", payload)


def edit_message(chat_id, message_id, text):
    """Sunting pesan. Gagal senyap kalau isinya sama — Telegram menolaknya."""
    try:
        return _call("editMessageText", {"chat_id": chat_id, "message_id": message_id,
                                         "text": text, "parse_mode": "HTML"})
    except TelegramError as exc:
        if "message is not modified" in str(exc):
            return None
        raise


def send_document(chat_id, path, filename=None, caption=None):
    return _upload("sendDocument", chat_id, "document", path, filename, caption)


def send_photo(chat_id, path, caption=None):
    return _upload("sendPhoto", chat_id, "photo", path, None, caption)


def answer_callback(callback_id, text=None):
    payload = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text
    return _call("answerCallbackQuery", payload)


def _call(method, payload):
    url = f"{config.TELEGRAM_API}/bot{config.TELEGRAM_BOT_TOKEN}/{method}"
    data = json.dumps(payload).encode()
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            result = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise TelegramError(f"{method} gagal (HTTP {exc.code}): {detail}") from exc
    except Exception as exc:
        raise TelegramError(f"{method} gagal: {exc}") from exc

    if not result.get("ok"):
        raise TelegramError(f"{method}: {result.get('description', 'tanpa keterangan')}")
    return result.get("result")


def _upload(method, chat_id, field, path, filename, caption):
    """Kirim berkas lewat multipart.

    Dibangun manual karena urllib tidak menyediakan multipart. Ukurannya
    kecil dan jelas, jadi tidak perlu pustaka tambahan.

    Setiap isian wajib membawa pembatasnya sendiri. `add_field` mengembalikan
    potongan yang sudah jadi — dulu fungsinya hanya menambahkan ke daftar,
    sehingga semua isian memakai satu pembatas dan Telegram menolak 400.
    """
    boundary = "----notaekstrak" + os.urandom(8).hex()

    def field_chunk(name, value):
        return (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n"
            f"{value}\r\n"
        ).encode()

    parts = [field_chunk("chat_id", chat_id)]

    if caption:
        parts.append(field_chunk("caption", caption))
        parts.append(field_chunk("parse_mode", "HTML"))

    path = Path(path)
    name = filename or path.name
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{name}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n".encode()
    )
    parts.append(Path(path).read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(parts)

    url = f"{config.TELEGRAM_API}/bot{config.TELEGRAM_BOT_TOKEN}/{method}"
    request = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode())
    except Exception as exc:
        raise TelegramError(f"{method} gagal: {exc}") from exc
    if not result.get("ok"):
        raise TelegramError(f"{method}: {result.get('description', 'tanpa keterangan')}")
    return result.get("result")
