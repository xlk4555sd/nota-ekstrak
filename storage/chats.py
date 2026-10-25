"""Chat yang diizinkan memakai bot, beserta jatah hariannya."""


def upsert_chat(chat_id, allowed=0, daily_receipts=None, daily_tokens=None, note=None):
    from db import connect
    conn = connect()
    row = conn.execute("SELECT chat_id FROM chat_limits WHERE chat_id = ?", (chat_id,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO chat_limits (chat_id, allowed, daily_receipts, daily_tokens, note) "
            "VALUES (?, ?, ?, ?, ?)",
            (chat_id, allowed, daily_receipts or 0, daily_tokens or 0, note),
        )
    else:
        fields, values = [], []
        for name, value in (("allowed", allowed), ("daily_receipts", daily_receipts),
                            ("daily_tokens", daily_tokens), ("note", note)):
            if value is not None:
                fields.append(f"{name} = ?")
                values.append(value)
        values.append(chat_id)
        conn.execute(f"UPDATE chat_limits SET {', '.join(fields)} WHERE chat_id = ?", values)
    conn.commit()


def get_chat(chat_id):
    from db import connect
    row = connect().execute("SELECT * FROM chat_limits WHERE chat_id = ?", (chat_id,)).fetchone()
    return dict(row) if row else None


def delete_chat(chat_id):
    from db import connect
    conn = connect()
    conn.execute("DELETE FROM chat_limits WHERE chat_id = ?", (chat_id,))
    conn.commit()


def list_chats():
    from db import connect
    return [dict(r) for r in connect().execute("SELECT * FROM chat_limits ORDER BY chat_id")]
