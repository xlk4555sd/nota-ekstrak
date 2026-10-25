"""Alat baris perintah untuk mengurus chat yang boleh memakai bot.

    python scripts/admin_cli.py list
    python scripts/admin_cli.py allow 123456789 --catatan "budi kantor"
    python scripts/admin_cli.py block 123456789
    python scripts/admin_cli.py jobs
    python scripts/admin_cli.py bersih              # lihat saja, tidak menghapus
    python scripts/admin_cli.py bersih --hapus      # benar-benar membersihkan

Tanpa argumen "list". Sengaja dipisah dari bot: membuka akses harus lewat
sengaja, bukan lewat percakapan.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
import storage.maintenance as maintenance  # noqa: E402


def ukuran(byte):
    """Ukuran dalam satuan yang mudah dibaca manusia."""
    for satuan in ("B", "KB", "MB", "GB"):
        if byte < 1024 or satuan == "GB":
            return f"{byte:.1f} {satuan}" if satuan != "B" else f"{byte} B"
        byte /= 1024.0


def show_list():
    rows = db.list_chats()
    if not rows:
        print("belum ada chat terdaftar")
        return
    print(f"{'chat_id':>14}  {'izin':5}  {'nota/hari':>9}  {'token/hari':>11}  catatan")
    for row in rows:
        print(f"{row['chat_id']:>14}  {'ya' if row['allowed'] else 'tidak':5}  "
              f"{row['daily_receipts']:>9}  {row['daily_tokens']:>11}  {row['note'] or ''}")


def show_jobs():
    rows = db.list_jobs(20)
    if not rows:
        print("belum ada pekerjaan")
        return
    for row in rows:
        done = len(db.receipts_for_job(row["id"]))
        print(f"#{row['id']:<4} {row['status']:10s} {done:3d}/{row['total_files']:<3d} "
              f"chat {row['chat_id']:<14} {row['created_at']}  {row['error'] or ''}")


def run_bersih(hari, hari_basis_data, hapus):
    """Pembersihan data. Tanpa --hapus hanya menghitung, tidak menyentuh apa pun."""
    kering = not hapus
    print("MODE: " + ("menghitung saja (tidak ada yang dihapus)" if kering else "MENGHAPUS"))
    print()
    for label, info in maintenance.ringkasan().items():
        print(f"  {label:12s} {info['berkas']:5d} berkas  {ukuran(info['byte'])}")
    print()

    hasil = maintenance.bersihkan_semua(hari=hari, hari_basis_data=hari_basis_data, kering=kering)

    ung = hasil["unggahan"]
    print(f"unggahan : {len(ung['dihapus'])} folder, {ukuran(ung['byte'])}")
    if ung["dilewati"]:
        print(f"           dilewati (masih dipakai): {', '.join(ung['dilewati'])}")
    eks = hasil["ekspor"]
    print(f"ekspor   : {len(eks['dihapus'])} berkas, {ukuran(eks['byte'])}")
    bd = hasil["basis_data"]
    print(f"basis data: {len(bd['pekerjaan'])} pekerjaan, {bd['hasil']} hasil")
    if bd["pekerjaan"]:
        print(f"           id: {', '.join('#' + str(i) for i in bd['pekerjaan'])}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list")
    sub.add_parser("jobs")

    allow = sub.add_parser("allow")
    allow.add_argument("chat_id", type=int)
    allow.add_argument("--catatan", default="")
    allow.add_argument("--nota-per-hari", type=int, default=0,
                       help="0 = pakai bawaan config")
    allow.add_argument("--token-per-hari", type=int, default=0)

    block = sub.add_parser("block")
    block.add_argument("chat_id", type=int)

    bersih = sub.add_parser("bersih", help="hapus data lama (folder unggahan, ekspor)")
    bersih.add_argument("--hari", type=int, default=7,
                        help="umur minimal untuk pekerjaan selesai (bawaan 7)")
    bersih.add_argument("--hari-basis-data", type=int, default=30,
                        help="umur minimal untuk menghapus baris basis data (bawaan 30)")
    bersih.add_argument("--hapus", action="store_true",
                        help="benar-benar hapus; tanpa ini hanya menghitung")

    args = parser.parse_args()
    db.init_db()

    if args.command == "list":
        show_list()
    elif args.command == "jobs":
        show_jobs()
    elif args.command == "bersih":
        run_bersih(args.hari, args.hari_basis_data, args.hapus)
    elif args.command == "allow":
        import config
        db.upsert_chat(
            args.chat_id,
            allowed=1,
            note=args.catatan,
            daily_receipts=args.nota_per_hari or config.DAILY_RECEIPTS_PER_CHAT,
            daily_tokens=args.token_per_hari or config.DAILY_TOKENS_PER_CHAT,
        )
        print(f"chat {args.chat_id} diizinkan")
    elif args.command == "block":
        db.upsert_chat(args.chat_id, allowed=0)
        print(f"chat {args.chat_id} diblokir")


if __name__ == "__main__":
    main()

