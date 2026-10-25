"""Susun tabel hasil menjadi CSV dan Excel.

CSV dibuat tanpa pustaka tambahan. Excel memakai openpyxl supaya angka jadi
angka dan tanggal jadi tanggal — di CSV, Excel berbahasa Indonesia membaca
"1.250.000" sebagai teks dan "24/10/2026" dengan urutan yang bisa keliru.
"""
import csv
import io
from pathlib import Path

COLUMNS = ("vendor", "tanggal", "nomor_nota", "total", "mata_uang", "nama_file", "perlu_dicek")

HEADERS = {
    "vendor": "Vendor",
    "tanggal": "Tanggal",
    "nomor_nota": "Nomor Nota",
    "total": "Total",
    "mata_uang": "Mata Uang",
    "nama_file": "Nama File",
    "perlu_dicek": "Perlu Dicek",
}


def rows(receipts):
    for item in receipts:
        flagged = ",".join(item.get("review_flags") or [])
        yield {
            "vendor": item.get("vendor", ""),
            "tanggal": item.get("tanggal", ""),
            "nomor_nota": item.get("nomor_nota", ""),
            "total": item.get("total", ""),
            "mata_uang": item.get("mata_uang", ""),
            "nama_file": item.get("named_file", ""),
            "perlu_dicek": flagged,
        }


def to_csv(receipts, path=None):
    """Tulis CSV. Selalu pakai UTF-8 dengan BOM supaya Excel tidak mengacak aksen."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=[HEADERS[c] for c in COLUMNS], extrasaction="ignore")
    writer.writeheader()
    for row in rows(receipts):
        writer.writerow({HEADERS[k]: row[k] for k in COLUMNS})

    text = buffer.getvalue()
    if path:
        Path(path).write_text("\ufeff" + text, encoding="utf-8")
        return Path(path)
    return text


def to_xlsx(receipts, path):
    """Tulis Excel. Total diubah jadi angka kalau bisa dibaca sebagai angka."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Nota"
    sheet.append([HEADERS[c] for c in COLUMNS])
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    warning = PatternFill("solid", fgColor="FFF3CD")
    for index, row in enumerate(rows(receipts), start=2):
        sheet.append([row[k] for k in COLUMNS])
        if row["perlu_dicek"]:
            for column in range(1, len(COLUMNS) + 1):
                sheet.cell(row=index, column=column).fill = warning
        numeric = _as_number(row["total"])
        if numeric is not None:
            cell = sheet.cell(row=index, column=COLUMNS.index("total") + 1, value=numeric)
            cell.number_format = "#,##0.00"

    widths = {"Vendor": 32, "Tanggal": 14, "Nomor Nota": 22, "Total": 16,
              "Mata Uang": 10, "Nama File": 30, "Perlu Dicek": 24}
    for column, title in enumerate([HEADERS[c] for c in COLUMNS], start=1):
        sheet.column_dimensions[sheet.cell(row=1, column=column).column_letter].width = widths[title]

    workbook.save(path)
    return Path(path)


def _as_number(value):
    """Kembalikan angka kalau teks ini jelas angka, selain itu None.

    Titik dan koma ambigu antarnegara. Aturan yang dipakai:
      - "1.250" atau "1.250.000" -> titik ribuan (kebiasaan Indonesia)
      - "45,50"                   -> koma desimal
      - "1,234.56"                -> gaya Inggris
    Selain pola yang yakin, nilainya dibiarkan teks. Lebih baik teks daripada
    angka yang salah — angka salah di Excel langsung masuk ke laporan.
    """
    if not value:
        return None
    text = value.replace(" ", "")

    # gaya Inggris: koma ribuan, titik desimal
    if text.count(",") >= 1 and text.count(".") == 1:
        head, tail = text.rsplit(".", 1)
        if tail.isdigit() and len(tail) <= 2 and head.replace(",", "").isdigit():
            return float(head.replace(",", "") + "." + tail)

    # koma desimal tanpa titik
    if text.count(",") == 1 and text.count(".") == 0:
        head, tail = text.split(",")
        if tail.isdigit() and head.isdigit():
            return float(f"{head}.{tail}")

    # titik ribuan: setiap kelompok setelah titik tepat tiga digit
    if text.count(".") >= 1 and text.count(",") == 0:
        groups = text.split(".")
        if all(part.isdigit() for part in groups) and all(len(part) == 3 for part in groups[1:]):
            return int("".join(groups))

    if text.isdigit():
        return int(text)
    return None
