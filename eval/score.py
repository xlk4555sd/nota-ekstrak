"""Ukur ketepatan pada nota yang punya kunci jawaban.

Cara pakai:
    python -m eval.score --images eval/dataset/images --truth eval/dataset/truth.json

Kenapa ini dipisah dari tes: tes memakai model tiruan supaya gratis dan
selalu sama. Skrip ini memakai model sungguhan dan butuh biaya. Hasilnya
angka yang ditulis di README — termasuk yang gagal.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config          # noqa: E402
from services import extract   # noqa: E402
from services.schema import FIELDS, normalize   # noqa: E402


def load_truth(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def compare(expected, actual, field, currencies):
    """Bandingkan satu kolom. Angka dibandingkan sebagai angka, teks dinormalkan.

    Mengembalikan None kalau kunci jawaban tidak punya kolom ini. SROIE memang
    tidak menyediakan nomor nota, jadi menilainya kosong hanya menghukum model
    karena membaca lebih lengkap dari kuncinya.
    """
    want = str(expected.get(field, "") or "").strip()
    got = str(actual.get(field, "") or "").strip()
    if field not in expected:
        return None
    if field == "total":
        return _same_amount(want, got, currencies)
    if field == "mata_uang":
        return want.upper() == got.upper()
    if field in ("vendor", "nomor_nota"):
        return _squash(want) == _squash(got)
    return want == got


def _squash(text):
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _same_amount(want, got, currencies):
    def number(text):
        cleaned = "".join(ch for ch in text if ch.isdigit() or ch in ".,")
        for symbol in currencies:
            cleaned = cleaned.replace(symbol, "")
        cleaned = cleaned.replace(",", "")
        try:
            return round(float(cleaned), 2)
        except ValueError:
            return None

    a, b = number(want), number(got)
    if a is None or b is None:
        return _squash(want) == _squash(got)
    return abs(a - b) < 0.01


def main():
    parser = argparse.ArgumentParser(description="Ukur ketepatan ekstraksi nota")
    parser.add_argument("--images", required=True, help="folder gambar nota")
    parser.add_argument("--truth", required=True, help="berkas JSON kunci jawaban")
    parser.add_argument("--limit", type=int, default=0, help="batasi jumlah nota")
    parser.add_argument("--out", default=None, help="simpan hasil rinci ke JSON")
    args = parser.parse_args()

    truth = load_truth(args.truth)
    images = sorted(Path(args.images).glob("*"))
    images = [p for p in images if p.suffix.lower() in (".jpg", ".jpeg", ".png")]

    if args.limit:
        images = images[: args.limit]
    if not images:
        print("tidak ada gambar di folder itu")
        return 1

    currencies = set()
    for item in truth.values():
        if item.get("mata_uang"):
            currencies.add(item["mata_uang"])

    hits = {field: 0 for field in FIELDS}
    judged_per_field = {field: 0 for field in FIELDS}
    details = []
    total_seconds = 0.0
    errors = []

    for image in images:
        key = image.stem
        expected = truth.get(key)
        if expected is None:
            print(f"lewati {image.name}: tidak ada kunci jawaban")
            continue

        started = time.monotonic()
        try:
            answer = extract.read_receipts([image])
        except extract.ModelError as exc:
            errors.append({"file": image.name, "error": str(exc)})
            print(f"{image.name}: GAGAL — {exc}")
            continue

        elapsed = time.monotonic() - started
        total_seconds += elapsed
        receipt = normalize(answer.payload)
        got = receipt.as_dict()

        row = {"file": image.name, "seconds": round(elapsed, 2),
               "prompt_tokens": answer.prompt_tokens, "expected": expected, "got": got}
        for field in FIELDS:
            ok = compare(expected, got, field, currencies)
            row[f"{field}_ok"] = ok
            if ok is None:
                continue
            judged_per_field[field] += 1
            hits[field] += int(ok)
        details.append(row)

        marks = "".join("-" if row[f"{f}_ok"] is None else ("✓" if row[f"{f}_ok"] else "✗")
                        for f in FIELDS)
        print(f"{image.name}: {marks}  {elapsed:.1f}s")

    judged = len(details)
    print()
    print(f"Nota dinilai: {judged}   gagal total: {len(errors)}")
    if judged:
        for field in FIELDS:
            total_field = judged_per_field[field]
            if not total_field:
                print(f"  {field:12s}   -  (tidak ada kunci jawaban)")
                continue
            percent = 100 * hits[field] / total_field
            print(f"  {field:12s} {hits[field]:3d}/{total_field}  {percent:5.1f}%")
        print(f"  waktu rata-rata {total_seconds / judged:.1f} detik per nota")
        avg_tokens = sum(r["prompt_tokens"] for r in details) / judged
        print(f"  token masuk rata-rata {avg_tokens:.0f}")

    if args.out:
        Path(args.out).write_text(json.dumps(
            {"summary": {"judged": judged, "hits": hits, "errors": errors},
             "details": details}, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nhasil rinci: {args.out}")

    return 0 if judged else 1


if __name__ == "__main__":
    raise SystemExit(main())
