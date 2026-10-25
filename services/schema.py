"""Satu tempat yang tahu bentuk jawaban model.

Yang diuji pada uji 5 nota: kolom vendor, tanggal, total, nomor nota. Model
membaca angka dengan benar, tapi nomor nota pernah salah baca. Karena itu
nomor_faktur selalu masuk daftar periksa sementara kolom lain tidak — ini
keputusan yang didasari hasil uji, bukan perasaan.

Validasi di sini sengaja tidak memakai pustaka skema. Bentuknya cuma enam
kolom, dan kesalahan yang perlu ditangkap bisa dihitung dengan tangan.
"""
import re
from dataclasses import dataclass, field

from services.jsonutil import extract_json

FIELDS = ("vendor", "tanggal", "nomor_nota", "total", "mata_uang")

# Kolom yang selalu perlu dilihat manusia, walaupun nilainya terisi.
# nomor_nota: pernah salah baca pada uji.
ALWAYS_REVIEW = ("nomor_nota",)

# Bulan yang salah tulis ke teks lain biasanya muncul di nota berbahasa lain.
# Kalau mata uang tidak terbaca, tebakan dari simbol lebih jujur daripada kosong.
CURRENCY_HINTS = {
    "rp": "IDR", "idr": "IDR",
    "rm": "MYR", "myr": "MYR",
    "$": "USD", "usd": "USD",
    "€": "EUR", "eur": "EUR",
    "sgd": "SGD", "s$": "SGD",
}


@dataclass
class Receipt:
    vendor: str = ""
    tanggal: str = ""
    nomor_nota: str = ""
    total: str = ""
    mata_uang: str = ""
    review: list = field(default_factory=list)

    def as_dict(self):
        return {name: getattr(self, name) for name in FIELDS}

    def is_empty(self):
        return not any(getattr(self, name).strip() for name in FIELDS)


def normalize(payload, named_file=""):
    """Ubah jawaban mentah model menjadi Receipt yang sudah dirapikan.

    Menerima dict (hasil json.loads) atau teks JSON. Format tanggal dan angka
    dibiarkan seperti yang tertulis, hanya dirapikan spasinya: mengubah
    "24/10/26" jadi "2026-10-24" secara diam-diam bisa menyembunyikan salah
    baca tahun, dan itu justru yang perlu dilihat manusia.
    """
    data = payload
    if isinstance(payload, str):
        data = extract_json(payload)
        if data is None:
            raise ValueError("jawaban model bukan JSON yang sah")
    if not isinstance(data, dict):
        raise ValueError("jawaban model bukan objek JSON")

    receipt = Receipt()
    for name in FIELDS:
        raw = data.get(name, "")
        receipt.__setattr__(name, _clean(raw))

    _fill_currency(receipt, data)
    receipt.review = _review_flags(receipt)
    return receipt


def _clean(value):
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        # Model kadang mengembalikan angka, bukan teks. Jangan diformat ulang:
        # 1500.0 yang jadi "1500" bisa menghapus jejak bahwa nilainya pecahan.
        return str(value)
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()
    return str(value)


CURRENCY_ALIASES = {"RM": "MYR", "RP": "IDR", "S$": "SGD", "US$": "USD", "$": "USD"}


def _normalize_currency(code):
    """Model kadang mengembalikan simbol ("RM") padahal diminta kode tiga huruf."""
    text = (code or "").strip().upper()
    return CURRENCY_ALIASES.get(text, text)


def _fill_currency(receipt, data):
    if receipt.mata_uang:
        receipt.mata_uang = _normalize_currency(receipt.mata_uang)
        return
    blob = " ".join(str(data.get(k, "")) for k in ("total", "mata_uang", "vendor")).lower()
    for hint, code in CURRENCY_HINTS.items():
        if hint in blob:
            receipt.mata_uang = code
            return


def _review_flags(receipt):
    flags = [name for name in ALWAYS_REVIEW if receipt.__getattribute__(name)]
    if not receipt.vendor:
        flags.append("vendor")
    if not receipt.tanggal:
        flags.append("tanggal")
    if not receipt.total:
        flags.append("total")
    if not receipt.nomor_nota and "nomor_nota" not in flags:
        flags.append("nomor_nota")
    return sorted(set(flags))
