"""Uji ujung-ke-ujung tanpa Telegram: PDF -> antrean -> worker -> CSV.

Yang dipakai model sungguhan. Ini membuktikan bagian yang tidak tersentuh tes
tiruan: PDF berhalaman banyak, antrean, dan berkas hasil.

    bash eval/run_live.sh   # untuk skor
    python scripts/coba_pdf.py eval/dataset/pdf_contoh/nota.pdf
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config
import db
from services import exports
from worker import Worker


def main(argv):
    if len(argv) < 2:
        print("pakai: python scripts/coba_pdf.py <berkas.pdf>")
        return 1

    source = Path(argv[1]).resolve()
    chat_id = int(argv[2]) if len(argv) > 2 else 999

    config.ensure_dirs()
    db.init_db()
    db.upsert_chat(chat_id, allowed=1, daily_receipts=100, daily_tokens=1_000_000)
    for row in db.list_jobs(50):
        if row["chat_id"] == chat_id and row["status"] in ("pending", "running"):
            db.set_job_status(row["id"], "cancelled", error="bersih-bersih")

    job_id = db.create_job(chat_id, "telegram", 1)
    slot = config.UPLOAD_DIR / f"job{job_id}" / "src"
    slot.mkdir(parents=True, exist_ok=True)
    target = slot / source.name
    target.write_bytes(source.read_bytes())
    db.add_file(job_id, source.name, str(target))

    started = time.monotonic()
    job = db.claim_next_job()
    if job is None or job["id"] != job_id:
        raise SystemExit("ada pekerjaan lain yang lebih dulu menunggu; bersihkan dulu")
    Worker().run_job(job)
    elapsed = time.monotonic() - started

    job = db.get_job(job_id)
    rows = db.receipts_for_job(job_id)

    print(f"status      : {job['status']}   ({elapsed:.1f} detik)")
    if job["error"]:
        print(f"catatan     : {job['error']}")
    print(f"baris hasil : {len(rows)}")
    for row in rows:
        print("  " + " | ".join(str(row.get(k) or "") for k in
                                ("named_file", "vendor", "tanggal", "nomor_nota",
                                 "total", "mata_uang")))
        if row.get("review_flags"):
            print(f"    perlu dicek: {row['review_flags']}")

    if rows:
        csv_path = exports.to_csv(rows, config.EXPORT_DIR / "contoh.csv")
        print(f"csv         : {csv_path}  ({csv_path.stat().st_size} byte)")
        print(csv_path.read_text(encoding="utf-8-sig"))
        xlsx_path = exports.to_xlsx(rows, config.EXPORT_DIR / "contoh.xlsx")
        print(f"xlsx        : {xlsx_path}  ({xlsx_path.stat().st_size} byte)")

        usage = db.usage_since(chat_id, "1970-01-01")
        print(f"token       : {json.dumps(usage)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
