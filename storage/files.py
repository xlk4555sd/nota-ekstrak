"""Berkas milik satu pekerjaan: yang diunggah user maupun hasil rasterisasi."""


def add_file(job_id, filename, path="", kind="image", page_no=None, remote_id=None):
    from db import connect
    conn = connect()
    cur = conn.execute(
        "INSERT INTO files (job_id, filename, path, remote_id, kind, page_no) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (job_id, filename, path, remote_id, kind, page_no),
    )
    conn.commit()
    return cur.lastrowid


def set_file_path(file_id, path):
    from db import connect
    conn = connect()
    conn.execute("UPDATE files SET path = ? WHERE id = ?", (str(path), file_id))
    conn.commit()


def pending_files(job_id):
    from db import connect
    return [dict(r) for r in connect().execute(
        "SELECT * FROM files WHERE job_id = ? AND status = 'pending' ORDER BY id", (job_id,)
    )]


def files_for_job(job_id):
    from db import connect
    return [dict(r) for r in connect().execute(
        "SELECT * FROM files WHERE job_id = ? ORDER BY id", (job_id,)
    )]


def set_file_status(file_id, status, error=None):
    from db import connect
    conn = connect()
    conn.execute("UPDATE files SET status = ?, error = ? WHERE id = ?", (status, error, file_id))
    conn.commit()


def set_job_files_status(job_id, status, error=None):
    """Ubah status semua berkas satu pekerjaan sekaligus.

    Dipakai pembersih: berkas yang datanya sudah dihapus tidak boleh tetap
    berstatus 'done', karena laporan akan mengaku masih ada.
    """
    from db import connect
    conn = connect()
    conn.execute("UPDATE files SET status = ?, error = ? WHERE job_id = ?",
                 (status, error, job_id))
    conn.commit()
