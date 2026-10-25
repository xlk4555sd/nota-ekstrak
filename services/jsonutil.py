"""Cari objek JSON di dalam teks jawaban model.

Model kadang menulis "Berikut hasilnya: {...}" atau membungkus dengan pagar
kode. Fungsi ini dipakai bersama oleh services.schema dan services.extract
supaya tidak ada dua versi aturan yang bisa berbeda hasil.
"""
import json


def extract_json(text):
    """Kembalikan dict pertama yang sah, atau None kalau tidak ada."""
    if not text:
        return None

    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass

    depth, start = 0, None
    for index, char in enumerate(text):
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    value = json.loads(text[start:index + 1])
                    if isinstance(value, dict):
                        return value
                except json.JSONDecodeError:
                    start = None
                depth = 0
    return None
