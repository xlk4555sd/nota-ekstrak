"""Hitung pemakaian token dan tolak pekerjaan yang melewati jatah.

Jatah harian ada dua lapis: per chat (supaya satu orang tidak menghabiskan
semua) dan global (pengaman kalau penyalahgunaan). Batas dihitung dari tabel
usage, bukan dari penghitung di memori, supaya tetap benar setelah restart.
"""
from datetime import datetime, timedelta, timezone

import config
import db


class QuotaExceeded(Exception):
    """Pesan di sini sengaja bisa dibaca user langsung."""


def day_start(now=None):
    """Awal hari dalam UTC. Sederhana dan tidak bergantung zona waktu server."""
    now = now or datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")


def check_before_start(chat_id, planned_receipts):
    """Dipanggil sebelum pekerjaan dibuat, supaya user tahu lebih awal."""
    since = day_start()
    limit = db.get_chat(chat_id) or {}

    # Angka 0 berarti "jatah habis", bukan "pakai bawaan" — karena itu `or`
    # akan salah di sini. Baris tanpa pengaturan tetap memakai bawaan.
    max_receipts = limit.get("daily_receipts")
    if max_receipts is None:
        max_receipts = config.DAILY_RECEIPTS_PER_CHAT
    done = db.receipts_done_since(chat_id, since)
    if done + planned_receipts > max_receipts:
        left = max(0, max_receipts - done)
        raise QuotaExceeded(f"jatah harian tersisa {left} nota, tidak cukup untuk {planned_receipts}")


def check_token_budget(chat_id):
    """Dicek di tengah pekerjaan; biaya nyata baru diketahui setelah panggilan.

    Batas dibaca dari modul config setiap kali dipanggil (bukan diimpor di atas),
    supaya perubahan konfigurasi saat program berjalan ikut terpakai.
    """
    since = day_start()
    limit = db.get_chat(chat_id) or {}
    per_chat = limit.get("daily_tokens") or config.DAILY_TOKENS_PER_CHAT

    used = db.usage_since(chat_id, since)["total"]
    if used >= per_chat:
        raise QuotaExceeded(f"jatah token harian chat ini habis ({used:,} dari {per_chat:,})")

    global_used = _global_tokens_since(since)
    if global_used >= config.GLOBAL_DAILY_TOKENS:
        raise QuotaExceeded("jatah token harian sistem habis, coba lagi besok")


def record(chat_id, job_id, answer):
    db.add_usage(
        chat_id, job_id, answer.model,
        answer.prompt_tokens, answer.completion_tokens,
    )


def summary(chat_id):
    since = day_start()
    used = db.usage_since(chat_id, since)
    limit = db.get_chat(chat_id) or {}
    return {
        "receipts": db.receipts_done_since(chat_id, since),
        "receipts_limit": limit.get("daily_receipts") or config.DAILY_RECEIPTS_PER_CHAT,
        "tokens": used["total"],
        "tokens_limit": limit.get("daily_tokens") or config.DAILY_TOKENS_PER_CHAT,
        "calls": used["calls"],
    }


def _global_tokens_since(since):
    row = db.connect().execute(
        "SELECT COALESCE(SUM(prompt_tokens + completion_tokens), 0) AS t "
        "FROM usage WHERE created_at >= ?",
        (since,),
    ).fetchone()
    return row["t"]


def reset_window_hint():
    """Teks bantuan untuk pesan error: kapan jatah kembali."""
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    hours = max(0, int((tomorrow - datetime.now(timezone.utc)).total_seconds() // 3600))
    return f"jatah kembali dalam sekitar {hours} jam"
