"""Pemakaian model dan jatah harian per chat."""


def add_usage(chat_id, job_id, model, prompt_tokens, completion_tokens):
    from db import _now, connect
    conn = connect()
    conn.execute(
        "INSERT INTO usage (chat_id, job_id, model, prompt_tokens, completion_tokens, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (chat_id, job_id, model, prompt_tokens, completion_tokens, _now()),
    )
    conn.commit()


def usage_since(chat_id, since_iso):
    from db import connect
    row = connect().execute(
        "SELECT COALESCE(SUM(prompt_tokens), 0) AS p, COALESCE(SUM(completion_tokens), 0) AS c, "
        "COUNT(*) AS calls FROM usage WHERE chat_id = ? AND created_at >= ?",
        (chat_id, since_iso),
    ).fetchone()
    return {"prompt": row["p"], "completion": row["c"], "calls": row["calls"],
            "total": row["p"] + row["c"]}


def receipts_done_since(chat_id, since_iso):
    from db import connect
    row = connect().execute(
        "SELECT COUNT(*) AS n FROM receipts r "
        "JOIN files f ON f.id = r.file_id "
        "JOIN jobs j ON j.id = f.job_id "
        "WHERE j.chat_id = ? AND r.created_at >= ?",
        (chat_id, since_iso),
    ).fetchone()
    return row["n"]
