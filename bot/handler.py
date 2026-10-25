"""Terima update dari Telegram, putuskan harus berbuat apa.

Aturan yang dipegang di sini: bagian ini tidak pernah memanggil model dan tidak
pernah mengunduh berkas. Tugasnya hanya mencatat pekerjaan ke antrean; worker
yang mengunduh dan mengerjakan. Pemisahan itu yang membuat penerimaan pesan
tetap cepat walau sedang ada 30 nota di antrean.

Semua jawaban keluar lewat `telegram` yang diimpor sebagai modul, supaya tes
bisa mengganti seluruh pengiriman dengan satu baris.
"""
import logging
import time

import config
import db
from bot import reply, telegram
from bot.format import cut
from services import limits, sources

log = logging.getLogger("nota.bot")

DOKUMEN_DIDUKUNG = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
PHOTO_NAME = "foto_{}.jpg"

# Album dikirim Telegram sebagai beberapa update berurutan yang tidak punya
# nomor urut. Jeda ini yang dipakai untuk memutuskan "albumnya sudah lengkap":
# begitu tidak ada foto baru selama sekian detik, kirimannya dianggap selesai.
ALBUM_JEDA = 1.2
_diterima_terakhir = {}   # chat_id -> waktu update foto terakhir


def handle_update(update):
    """Satu update = satu pesan atau satu tombol. Tidak pernah melempar."""
    try:
        if "message" in update:
            _handle_message(update["message"])
        elif "callback_query" in update:
            _handle_callback(update["callback_query"])
    except Exception:
        # Pengirim tidak boleh melihat galat kita, tapi kita harus melihatnya.
        log.exception("update gagal diproses: %r", update)


def _handle_message(message):
    chat_id = (message.get("chat") or {}).get("id")
    if chat_id is None:
        return

    if not _allowed(chat_id, message):
        telegram.send_message(chat_id, reply.not_allowed_text(chat_id))
        return

    if message.get("photo"):
        _handle_photo(chat_id, message["photo"], message.get("media_group_id"))
    elif message.get("document"):
        _handle_document(chat_id, message["document"])
    elif message.get("text"):
        _handle_text(chat_id, message["text"].strip())
    else:
        telegram.send_message(chat_id, reply.unsupported_text())


def _allowed(chat_id, message):
    return db.get_chat(chat_id) is not None


def _handle_text(chat_id, text):
    if text.startswith("/"):
        _handle_command(chat_id, text)
        return

    folder_id = sources.folder_id_from(text)
    if folder_id:
        _handle_drive_folder(chat_id, folder_id)
        return

    if sources.is_drive_file_link(text):
        telegram.send_message(chat_id, reply.single_file_text())
        return

    telegram.send_message(chat_id, reply.start_text())


def _handle_command(chat_id, text):
    command = text.split()[0].split("@")[0].lower()

    if command == "/start":
        telegram.send_message(chat_id, reply.start_text())

    elif command == "/help":
        telegram.send_message(chat_id, reply.help_text())

    elif command == "/status":
        telegram.send_message(chat_id, reply.status_text(db.active_job_for(chat_id), limits.summary(chat_id)))

    elif command == "/batal":
        job = db.active_job_for(chat_id)
        if job:
            db.set_job_status(job["id"], "cancelled", error="dihentikan oleh user")
            telegram.send_message(chat_id, reply.cancelled_text(job["id"]))
        else:
            telegram.send_message(chat_id, reply.no_active_text())

    else:
        telegram.send_message(chat_id, reply.start_text())


def _handle_drive_folder(chat_id, folder_id):
    busy = db.active_job_for(chat_id)
    if busy:
        telegram.send_message(chat_id, reply.busy_text(busy["id"]))
        return

    try:
        entries = sources.list_folder(folder_id)
        limits.check_before_start(chat_id, len(entries))
    except sources.SourceError as exc:
        telegram.send_message(chat_id, reply.rejected_text(str(exc)))
        return
    except limits.QuotaExceeded as exc:
        telegram.send_message(chat_id, reply.quota_text(str(exc)))
        return

    job_id = db.create_job(chat_id, "drive", len(entries), drive_url=folder_id)
    for file_id, name in entries:
        db.add_file(job_id, name, kind="remote", remote_id=file_id)

    telegram.send_message(chat_id, reply.queued_text(job_id, len(entries)),
                          reply_markup=reply.cancel_keyboard(job_id))


def _handle_document(chat_id, document):
    name = document.get("file_name") or "berkas"
    if not _supported(name):
        telegram.send_message(chat_id, reply.unsupported_text())
        return
    if _queue_telegram_files(chat_id, [(document["file_id"], name)]):
        _finish_queue(chat_id)


def _handle_photo(chat_id, photos, group_id):
    # Telegram mengirim beberapa ukuran sekaligus; ambil yang paling besar.
    best = max(photos, key=lambda item: item.get("file_size") or 0)
    name = PHOTO_NAME.format(best.get("file_unique_id", "foto")[-8:])
    if not _queue_telegram_files(chat_id, [(best["file_id"], name)]):
        return

    # Album tiba sebagai beberapa update; tunggu sampai diam dulu supaya user
    # menerima satu kabar, bukan satu per foto.
    if group_id:
        _tunggu_album_selesai(chat_id)
    else:
        _finish_queue(chat_id)


def _tunggu_album_selesai(chat_id):
    """Tunggu sampai tidak ada foto baru, baru kabari user.

    Dipanggil dari dalam penanganan update sehingga menahan balasan webhook.
    Itu disengaja: Telegram mengirim tiap foto album dalam update terpisah,
    dan tanpa jeda ini user menerima lima balasan "Diterima" untuk satu kiriman.
    """
    _diterima_terakhir[chat_id] = time.monotonic()
    while True:
        time.sleep(0.15)
        terakhir = _diterima_terakhir.get(chat_id)
        if time.monotonic() - terakhir >= ALBUM_JEDA:
            break
    _diterima_terakhir.pop(chat_id, None)
    _finish_queue(chat_id)


def _queue_telegram_files(chat_id, items):
    """Tambah berkas ke pekerjaan yang sedang dibuka, atau buat pekerjaan baru.

    Satu kiriman = satu pekerjaan. Selama pekerjaan masih menunggu (worker
    belum mulai), berkas baru dianggap bagian dari kiriman yang sama — itu
    yang membuat album jadi satu tabel, bukan lima. Begitu worker mulai
    mengerjakan, kiriman baru ditolak supaya hasilnya tidak tertukar.

    Mengembalikan nomor pekerjaan, atau None kalau ditolak. Pemanggil yang
    memutuskan kapan user dikabari — bukan fungsi ini.
    """
    job = db.active_job_for(chat_id)
    if job:
        if job["status"] != "pending":
            telegram.send_message(chat_id, reply.busy_text(job["id"]))
            return None
        for file_id, name in items:
            db.add_file(job["id"], name, remote_id=file_id)
        db.set_job_total(job["id"], len(db.files_for_job(job["id"])))
        return job["id"]

    try:
        limits.check_before_start(chat_id, len(items))
    except limits.QuotaExceeded as exc:
        telegram.send_message(chat_id, reply.quota_text(str(exc)))
        return None

    job_id = db.create_job(chat_id, "telegram", len(items))
    for file_id, name in items:
        db.add_file(job_id, name, remote_id=file_id)
    return job_id


def _finish_queue(chat_id):
    """Kirim satu pesan progres untuk kiriman yang baru diterima.

    Pesan ini disimpan nomornya supaya worker bisa menyuntingnya saat mulai
    bekerja. Dengan begitu user melihat satu baris yang bergerak ("menunggu" →
    "memproses" → "merapikan"), bukan tiga pesan terpisah.
    """
    job = db.active_job_for(chat_id)
    if not job:
        return
    total = len(db.files_for_job(job["id"]))
    db.set_job_total(job["id"], total)
    job = db.get_job(job["id"])

    nama = [row["filename"] for row in db.files_for_job(job["id"])]
    teks = reply.antre_text(job)
    if nama:
        teks += "\n\n" + "\n".join(f"• {cut(n)}" for n in nama[:8])
        if len(nama) > 8:
            teks += f"\n• dan {len(nama) - 8} berkas lain"

    try:
        pesan = telegram.send_message(chat_id, teks,
                                      reply_markup=reply.cancel_keyboard(job["id"]))
        db.set_job_progress_message(job["id"], (pesan or {}).get("message_id"))
    except telegram.TelegramError as exc:
        # Progres tidak boleh menggagalkan pekerjaan yang sudah terlanjur
        # masuk antrean; hasilnya tetap akan dikirim saat selesai.
        log.warning("gagal kirim pesan antrean %s: %s", job["id"], exc)


def _supported(name):
    return any(name.lower().endswith(ext) for ext in DOKUMEN_DIDUKUNG)


# --- tombol ---------------------------------------------------------------

def _handle_callback(callback):
    callback_id = callback.get("id")
    data = callback.get("data") or ""
    message = callback.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")

    if chat_id is None or not data:
        telegram.answer_callback(callback_id)
        return

    action, _, raw_id = data.partition(":")
    if not raw_id.isdigit():
        telegram.answer_callback(callback_id)
        return
    job_id = int(raw_id)

    if action == "cancel":
        _cancel_from_button(chat_id, message.get("message_id"), job_id, callback_id)
        return

    if action in ("csv", "xlsx"):
        _send_export(chat_id, job_id, action, callback_id)
        return

    telegram.answer_callback(callback_id)


def _cancel_from_button(chat_id, message_id, job_id, callback_id):
    job = db.get_job(job_id)
    if not job or job["chat_id"] != chat_id:
        telegram.answer_callback(callback_id, "Kiriman ini sudah selesai")
        return
    if job["status"] in ("pending", "running"):
        db.set_job_status(job_id, "cancelled", error="dihentikan oleh user")
        telegram.answer_callback(callback_id, "Dihentikan")
        _update_progress_message(chat_id, message_id, job_id)
    else:
        telegram.answer_callback(callback_id, "Kiriman ini sudah selesai")


def _send_export(chat_id, job_id, kind, callback_id):
    # Nomor pekerjaan tercetak di pesan, jadi siapa pun bisa mengetiknya lewat
    # tombol. Hasil hanya boleh keluar ke chat yang memilikinya.
    job = db.get_job(job_id)
    if not job or job["chat_id"] != chat_id:
        telegram.answer_callback(callback_id, "Kiriman tidak ditemukan")
        telegram.send_message(chat_id, reply.empty_result_text())
        return

    receipts = db.receipts_for_job(job_id)
    if not receipts:
        telegram.answer_callback(callback_id)
        telegram.send_message(chat_id, reply.empty_result_text())
        return

    telegram.answer_callback(callback_id, "Menyiapkan berkas…")
    from services import exports  # diimpor di sini agar openpyxl tidak wajib

    base = config.EXPORT_DIR / f"nota_{job_id}"
    if kind == "csv":
        path = exports.to_csv(receipts, base.with_suffix(".csv"))
    else:
        path = exports.to_xlsx(receipts, base.with_suffix(".xlsx"))

    telegram.send_document(chat_id, path, path.name, caption=f"Hasil #{job_id}")


def _update_progress_message(chat_id, message_id, job_id):
    """Tombol Hentikan tidak boleh tertinggal setelah pekerjaan berhenti."""
    if not message_id:
        return
    job = db.get_job(job_id)
    if not job:
        return
    text = reply.cancelled_text(job_id) if job["status"] == "cancelled" \
        else reply.progress_text(job)
    try:
        telegram.edit_message(chat_id, message_id, text)
    except telegram.TelegramError:
        log.debug("tidak bisa menyunting pesan #%s", message_id, exc_info=True)
