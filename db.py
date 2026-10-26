"""Basis data: koneksi, skema, dan semua penulisan data.

Aturan proyek: tidak ada modul lain yang menulis SQL. Kalau route atau service
butuh data, tambahkan fungsi di paket ini. Alasannya bukan kerapian belakangan,
tapi supaya tes bisa memakai basis data sementara tanpa menyentuh data asli.

Paket ini dipecah per domain sejak lama; berkas ini sendiri hanya mengurus
empat hal yang dipakai semua domain:

- `connect()` / `close()` — satu koneksi per thread
- `SCHEMA` — bentuk tabel
- `init_db()` / `_migrate()` — menyiapkan dan memperbarui basis data lama
- `_now()` — cap waktu yang seragam

Domain lain (`chats`, `jobs`, `files`, `receipts`, `usage`, `maintenance`) ada
di modul sebelah. Semuanya diekspor di sini, jadi pemanggil tetap menulis
`db.get_job(...)` seperti sebelumnya.
"""
import sqlite3
import threading
from datetime import datetime, timezone

import config

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id      INTEGER NOT NULL,
    source       TEXT NOT NULL,              -- telegram | drive
    status       TEXT NOT NULL DEFAULT 'pending',
                                             -- pending | running | done | failed | cancelled
    total_files  INTEGER NOT NULL DEFAULT 0,
    done_files   INTEGER NOT NULL DEFAULT 0,
    drive_url    TEXT,
    error        TEXT,
    progress_message_id INTEGER,          -- pesan yang disunting jadi progres
    progress_at  REAL,                    -- kapan terakhir disunting (detik)
    created_at   TEXT NOT NULL,
    started_at   TEXT,
    finished_at  TEXT
);

CREATE TABLE IF NOT EXISTS files (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id    INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    filename  TEXT NOT NULL,
    path      TEXT NOT NULL DEFAULT '',      -- kosong sampai worker selesai mengunduh
    remote_id TEXT,                          -- file_id Telegram / id berkas Google Drive
    kind      TEXT NOT NULL DEFAULT 'image', -- image | pdf_page
    page_no   INTEGER,
    status    TEXT NOT NULL DEFAULT 'pending',  -- pending | done | failed
    error     TEXT
);

CREATE TABLE IF NOT EXISTS receipts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id       INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    named_file    TEXT NOT NULL,
    vendor        TEXT NOT NULL DEFAULT '',
    tanggal       TEXT NOT NULL DEFAULT '',
    nomor_nota    TEXT NOT NULL DEFAULT '',
    total         TEXT NOT NULL DEFAULT '',   -- disimpan sebagai teks: sumbernya bisa kosong
    mata_uang     TEXT NOT NULL DEFAULT '',
    review_flags  TEXT NOT NULL DEFAULT '[]', -- JSON: kolom yang perlu diperiksa manusia
    raw_json      TEXT NOT NULL DEFAULT '',
    corrected     INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS corrections (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id   INTEGER NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
    field        TEXT NOT NULL,
    value_before TEXT NOT NULL DEFAULT '',
    value_after  TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usage (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id           INTEGER NOT NULL,
    job_id            INTEGER,
    model             TEXT NOT NULL,
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_limits (
    chat_id         INTEGER PRIMARY KEY,
    allowed         INTEGER NOT NULL DEFAULT 0,
    daily_receipts  INTEGER NOT NULL DEFAULT 0,
    daily_tokens    INTEGER NOT NULL DEFAULT 0,
    note            TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_chat   ON jobs(chat_id, created_at);
CREATE INDEX IF NOT EXISTS idx_files_job   ON files(job_id);
CREATE INDEX IF NOT EXISTS idx_usage_chat  ON usage(chat_id, created_at);
"""

# Kolom yang ditambahkan setelah tabel pertama kali dibuat. Dipisah dari SCHEMA
# supaya basis data lama di mesin yang sudah berjalan ikut menyusul.
LATE_COLUMNS = {
    "jobs": {"drive_url": "TEXT", "error": "TEXT",
             "progress_message_id": "INTEGER", "progress_at": "REAL"},
    "files": {"page_no": "INTEGER", "error": "TEXT", "remote_id": "TEXT"},
    "receipts": {"review_flags": "TEXT NOT NULL DEFAULT '[]'",
                 "raw_json": "TEXT NOT NULL DEFAULT ''",
                 "corrected": "INTEGER NOT NULL DEFAULT 0"},
}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect():
    """Koneksi untuk thread ini. Baris dikembalikan sebagai dict-like.

    Kunci pada path: kalau DB_PATH diganti (dipakai tes), koneksi lama yang
    menunjuk berkas lain harus dibuang, bukan dipakai ulang.
    """
    conn = getattr(_local, "conn", None)
    # Dibaca dari modul config, bukan disalin saat import, supaya perubahan
    # DATA_DIR (dipakai tes) benar-benar berpindah berkas.
    current = str(config.DB_PATH)
    if conn is not None and getattr(_local, "path", None) != current:
        conn.close()
        conn = None
    if conn is None:
        conn = sqlite3.connect(current, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        _local.conn = conn
        _local.path = current
    return conn


def close():
    """Tutup koneksi thread ini. Dipakai saat worker berhenti dan di tes."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


def init_db():
    conn = connect()
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()


def reset_connection():
    """Untuk tes: buang koneksi lama supaya DB_PATH yang baru dipakai."""
    close()


def _migrate(conn):
    """Tambahkan kolom yang belum ada di basis data lama.

    SQLite tidak punya ALTER TABLE yang lengkap, jadi kita bandingkan daftar
    kolom nyata dengan yang diharapkan lalu menambah yang kurang. Cara ini
    sudah diuji dan aman untuk data yang sudah berjalan.
    """
    for table, columns in LATE_COLUMNS.items():
        have = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, kind in columns.items():
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")


# --- ekspor seluruh domain -------------------------------------------------
# Diimpor di bawah supaya modul domain bisa `from db_core import connect`
# tanpa jerat impor melingkar.

from storage.chats import (  # noqa: E402
    delete_chat, get_chat, list_chats, upsert_chat,
)
from storage.jobs import (  # noqa: E402
    active_job_for, bump_job_progress, claim_next_job, count_jobs_by_status,
    create_job, get_job, list_jobs, list_jobs_for_chat, set_job_progress,
    set_job_progress_at, set_job_progress_message, set_job_status,
    set_job_total, selesai_sebelum,
)
from storage.files import (  # noqa: E402
    add_file, files_for_job, pending_files, set_file_path, set_file_status,
)
from storage.receipts import (  # noqa: E402
    add_receipt, corrections_for_job, receipts_for_job, update_receipt,
)
from storage.usage import add_usage, receipts_done_since, usage_since  # noqa: E402
from storage.deletes import (  # noqa: E402
    DeleteRefused, hapus_pekerjaan, hapus_semua, rincian,
)
