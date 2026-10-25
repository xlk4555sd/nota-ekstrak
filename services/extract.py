"""Panggilan ke model bahasa.

Dua hal yang dijaga di modul ini:

1. Batas waktu. Panggilan model bisa menggantung; tanpa batas waktu seluruh
   pekerjaan user ikut macet. Satu percobaan ulang saja, bukan tanpa henti.
2. Biaya. Setiap panggilan mengembalikan jumlah token yang dipakai, supaya
   pemanggil bisa mencatat dan menghentikan pekerjaan kalau melewati jatah.

Pola gagal-sopan ini dipakai supaya kegagalan pihak ketiga
tidak boleh membuat fitur utama ikut mati.
"""
import base64
import json
import time
from dataclasses import dataclass

import config
from services.jsonutil import extract_json


class ModelError(Exception):
    """Panggilan model gagal. Pesannya untuk log, bukan untuk user."""


class ModelRefused(ModelError):
    """Model menjawab tapi isinya tidak bisa dipakai."""


@dataclass
class Answer:
    payload: dict
    prompt_tokens: int
    completion_tokens: int
    model: str
    seconds: float


# Perbaikan yang lahir dari uji nyata, bukan dugaan:
#  - versi pertama tanpa penjelasan membuat model mengisi "vendor" dengan nama
#    kasir ("tan woon yann"), bukan nama toko;
#  - tanggal kembali sebagai angka telepon (tahun 2016) kalau tidak diperingatkan.
PROMPT = (
    "Baca nota/faktur pada gambar. Balas HANYA JSON dengan kunci tepat ini: "
    '{"vendor": "", "tanggal": "", "nomor_nota": "", "total": "", "mata_uang": ""}. '
    "vendor: nama toko atau perusahaan pemilik nota, biasanya di kop nota. Kalau ada "
    "beberapa nama, pilih yang berbentuk nama badan usaha (mengandung SDN BHD, PT, CV, "
    "TOKO, UD), bukan nama orang. Bukan nama kasir, bukan nama pelanggan, bukan alamat. "
    "tanggal: tanggal transaksi, salin seperti tertulis di nota (contoh 25/12/2018). "
    "Jangan mengubahnya menjadi format telepon. "
    "total: jumlah akhir yang dibayar, angka saja tanpa pemisah ribuan dan tanpa simbol. "
    "nomor_nota: nomor struk/invoice kalau ada. "
    "mata_uang: kode tiga huruf (IDR, MYR, USD), lihat simbol di nota. "
    "Salin apa yang tertulis, jangan menerjemahkan dan jangan menghitung ulang. "
    "Kalau kolom tidak ada di nota, isi string kosong. Jangan menambah kunci lain."
)


def read_receipts(image_paths, model=None, api_key=None):
    """Baca satu sampai lima gambar nota sekaligus.

    Menumpuk beberapa nota dalam satu gambar terbukti menurunkan ketepatan,
    jadi kirim tiap nota sebagai gambar sendiri di dalam satu panggilan.
    """
    paths = list(image_paths)
    if not paths:
        raise ValueError("tidak ada gambar untuk dibaca")
    if len(paths) > config.MAX_IMAGES_PER_CALL:
        raise ValueError(f"maksimal {config.MAX_IMAGES_PER_CALL} gambar per panggilan")

    key = api_key or config.RIVER_API_KEY
    if not key:
        raise ModelError("RIVER_API_KEY belum diisi")

    model_name = model or config.MODEL_NAME
    parts = [{"type": "text", "text": PROMPT}]
    for path in paths:
        parts.append({
            "type": "image_url",
            "image_url": {"url": _data_url(path)},
        })

    body = {
        "model": model_name,
        "messages": [{"role": "user", "content": parts}],
        "temperature": 0,
        "max_tokens": 700,
    }

    last_error = None
    for attempt in range(config.MODEL_MAX_RETRY + 1):
        started = time.monotonic()
        try:
            response = _post(key, body)
        except ModelError as exc:
            last_error = exc
            if attempt < config.MODEL_MAX_RETRY:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
        elapsed = time.monotonic() - started
        payload, prompt_tokens, completion_tokens = _parse(response, len(paths))
        return Answer(payload, prompt_tokens, completion_tokens, model_name, elapsed)

    raise last_error  # hanya tercapai kalau loop di atas berubah


def _post(api_key, body):
    import urllib.error
    import urllib.request

    data = json.dumps(body).encode()
    request = urllib.request.Request(
        f"{config.RIVER_BASE_URL}/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.MODEL_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise ModelError(f"model menolak permintaan (HTTP {exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise ModelError(f"tidak bisa menghubungi model: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ModelError("model tidak menjawab dalam batas waktu") from exc


def _parse(response, image_count):
    try:
        choice = response["choices"][0]
        text = choice["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelError("bentuk jawaban model tidak dikenal") from exc

    if isinstance(text, list):   # sebagian penyedia mengirim bagian, bukan teks
        text = "".join(part.get("text", "") for part in text if isinstance(part, dict))

    usage = response.get("usage") or {}
    prompt_tokens = usage.get("prompt_tokens") or (image_count * 1024)
    completion_tokens = usage.get("completion_tokens") or 0

    payload = extract_json(text)
    if payload is None:
        finish = choice.get("finish_reason")
        raise ModelRefused(
            f"jawaban model kosong atau bukan JSON (finish_reason={finish}, "
            f"panjang={len(text or '')})"
        )
    return payload, prompt_tokens, completion_tokens


def _data_url(path):
    raw = open(path, "rb").read()
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode()
