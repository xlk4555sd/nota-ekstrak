"""Hasil pembacaan nota, dan koreksi manusia atasnya."""

import json


def add_receipt(file_id, named_file, fields, review_flags=None, raw_json=""):
    from db import _now, connect
    conn = connect()
    cur = conn.execute(
        "INSERT INTO receipts (file_id, named_file, vendor, tanggal, nomor_nota, total, "
        "mata_uang, review_flags, raw_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            file_id,
            named_file,
            fields.get("vendor", ""),
            fields.get("tanggal", ""),
            fields.get("nomor_nota", ""),
            fields.get("total", ""),
            fields.get("mata_uang", ""),
            json.dumps(review_flags or [], ensure_ascii=False),
            raw_json,
            _now(),
        ),
    )
    conn.commit()
    return cur.lastrowid


def receipts_for_job(job_id):
    from db import connect
    rows = connect().execute(
        "SELECT r.* FROM receipts r JOIN files f ON f.id = r.file_id "
        "WHERE f.job_id = ? ORDER BY f.id",
        (job_id,),
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["review_flags"] = json.loads(item["review_flags"] or "[]")
        out.append(item)
    return out


def update_receipt(receipt_id, field, value):
    """Ubah satu kolom hasil, dan catat koreksinya untuk mengukur model.

    Koreksi tidak pernah menimpa bukti: nilai lama disimpan di tabel
    corrections supaya kita bisa membandingkan hasil model dengan hasil akhir.
    """
    from db import _now, connect
    allowed = {"vendor", "tanggal", "nomor_nota", "total", "mata_uang"}
    if field not in allowed:
        raise ValueError(f"kolom tidak boleh diubah: {field}")

    conn = connect()
    row = conn.execute("SELECT * FROM receipts WHERE id = ?", (receipt_id,)).fetchone()
    if row is None:
        raise LookupError(f"hasil {receipt_id} tidak ada")
    before = row[field]
    if before == value:
        return False
    conn.execute(
        "INSERT INTO corrections (receipt_id, field, value_before, value_after, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (receipt_id, field, before, value, _now()),
    )
    conn.execute(f"UPDATE receipts SET {field} = ?, corrected = 1 WHERE id = ?", (value, receipt_id))
    conn.commit()
    return True


def corrections_for_job(job_id):
    from db import connect
    return [dict(r) for r in connect().execute(
        "SELECT c.* FROM corrections c JOIN receipts r ON r.id = c.receipt_id "
        "JOIN files f ON f.id = r.file_id WHERE f.job_id = ? ORDER BY c.id",
        (job_id,),
    )]
