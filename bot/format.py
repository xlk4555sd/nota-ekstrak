"""Kemasan teks yang dikirim ke Telegram.

Teks user selalu di-escape lebih dulu, karena Telegram membuang seluruh pesan
kalau ada tag HTML yang tidak seimbang. Lebih baik sebagian kalimat rusak
daripada pesannya tidak sampai sama sekali.
"""


def plain(value):
    if value is None:
        return ""
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def cut(text, limit=28):
    text = plain(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def rupiah_friendly(number):
    """Tampilkan angka dengan titik ribuan. Hanya untuk kenyamanan membaca."""
    try:
        return f"{int(float(number)):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(number)
