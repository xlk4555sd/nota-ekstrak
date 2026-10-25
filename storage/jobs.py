"""Pekerjaan: satu kiriman = satu pekerjaan, beserta kemajuannya."""


def create_job(chat_id, source, total_files, drive_url=None):
    from db import _now, connect
    conn = connect()
    cur = conn.execute(
        "INSERT INTO jobs (chat_id, source, total_files, drive_url, created_at) VALUES (?, ?, ?, ?, ?)",
        (chat_id, source, total_files, drive_url, _now()),
    )
    conn.commit()
    return cur.lastrowid


def get_job(job_id):
    from db import connect
    row = connect().execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def active_job_for(chat_id):
    """Pekerjaan yang masih menunggu atau berjalan untuk satu chat."""
    from db import connect
    row = connect().execute(
        "SELECT * FROM jobs WHERE chat_id = ? AND status IN ('pending', 'running') "
        "ORDER BY id LIMIT 1",
        (chat_id,),
    ).fetchone()
    return dict(row) if row else None


def count_jobs_by_status():
    """Jumlah pekerjaan per status; dipakai titik kesehatan, bukan laporan."""
    from db import connect
    rows = connect().execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status")
    return {row["status"]: row["n"] for row in rows}


def set_job_progress_message(job_id, message_id):
    """Ingat pesan mana yang menampilkan progres pekerjaan ini.

    Disimpan supaya worker bisa menyunting baris yang sudah ada, bukan
    mengirim baris baru tiap kali kemajuannya berubah.

    Baris lama yang dibuat sebelum kolom ini ada tidak punya id pesan, jadi
    pesan antrean yang baru saja dikirim harus tetap tercatat.
    """
    from db import connect
    if not message_id:
        return
    conn = connect()
    conn.execute("UPDATE jobs SET progress_message_id = ?, progress_at = ? WHERE id = ?",
                 (int(message_id), 0.0, job_id))
    conn.commit()


def set_job_progress_at(job_id, detik):
    """Catat kapan pesan progres terakhir disunting.

    Dipakai worker untuk membatasi jumlah suntingan ke Telegram.
    """
    from db import connect
    conn = connect()
    conn.execute("UPDATE jobs SET progress_at = ? WHERE id = ?", (detik, job_id))
    conn.commit()


def set_job_total(job_id, total):
    """Jumlah berkas dari folder Drive baru pasti setelah folder dibaca."""
    from db import connect
    conn = connect()
    conn.execute("UPDATE jobs SET total_files = ? WHERE id = ?", (total, job_id))
    conn.commit()


def set_job_status(job_id, status, error=None):
    from db import _now, connect
    conn = connect()
    extra, values = "", [status]
    if status == "running":
        extra = ", started_at = ?"
        values.append(_now())
    if status in ("done", "failed", "cancelled"):
        extra += ", finished_at = ?"
        values.append(_now())
    if error is not None:
        extra += ", error = ?"
        values.append(error)
    values.append(job_id)
    conn.execute(f"UPDATE jobs SET status = ?{extra} WHERE id = ?", values)
    conn.commit()


def list_jobs(limit=20):
    """Pekerjaan terbaru, untuk admin_cli jobs."""
    from db import connect
    rows = connect().execute(
        "SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def bump_job_progress(job_id):
    from db import connect
    conn = connect()
    conn.execute("UPDATE jobs SET done_files = done_files + 1 WHERE id = ?", (job_id,))
    conn.commit()


def set_job_progress(job_id, done, total=None):
    """Tetapkan kemajuan pada angka tertentu.

    Dipakai saat jumlah sebenarnya baru diketahui (mis. satu PDF ternyata
    berisi sembilan halaman). Menambah terus lewat bump_job_progress akan
    membuat hitungannya melewati total.
    """
    from db import connect
    conn = connect()
    if total is None:
        conn.execute("UPDATE jobs SET done_files = ? WHERE id = ?", (done, job_id))
    else:
        conn.execute("UPDATE jobs SET done_files = ?, total_files = ? WHERE id = ?",
                     (done, total, job_id))
    conn.commit()


def claim_next_job():
    """Ambil satu pekerjaan tertua yang menunggu, lalu tandai berjalan.

    Dilakukan dalam satu transaksi supaya dua worker tidak mengambil pekerjaan
    yang sama. Saat ini worker hanya satu, tapi ini murah dan mencegah bug
    kalau nanti jumlahnya ditambah.
    """
    from db import _now, connect
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT id FROM jobs WHERE status = 'pending' ORDER BY id LIMIT 1"
        ).fetchone()
        if row is None:
            conn.commit()
            return None
        job_id = row["id"]
        conn.execute(
            "UPDATE jobs SET status = 'running', started_at = ? WHERE id = ?",
            (_now(), job_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return get_job(job_id)


def selesai_sebelum(batas_iso, limit=None):
    """Pekerjaan yang sudah selesai dan lebih tua dari `batas_iso`.

    Dipakai pembersih. Yang disertakan hanya status akhir — pekerjaan yang
    masih antre atau berjalan tidak boleh ikut, sekalipun umurnya sudah lewat.
    """
    from db import connect
    sql = ("SELECT id, chat_id, status, created_at FROM jobs "
           "WHERE status IN ('done', 'failed', 'cancelled') AND created_at < ? "
           "ORDER BY id")
    if limit:
        sql += " LIMIT ?"
        rows = connect().execute(sql, (batas_iso, limit)).fetchall()
    else:
        rows = connect().execute(sql, (batas_iso,)).fetchall()
    return [dict(r) for r in rows]
