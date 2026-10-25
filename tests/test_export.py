"""Tes ekspor CSV dan Excel.

Yang diuji bukan tampilan, tapi isi: apakah kolom lengkap, apakah penanda
periksa ikut, dan apakah Excel membaca total sebagai angka.
"""
import csv
import unittest
from pathlib import Path

from tests.base import TempDbCase
from services import exports


def sample():
    return [
        {"vendor": "Toko Maju", "tanggal": "24/10/2026", "nomor_nota": "INV-001",
         "total": "1250000", "mata_uang": "IDR", "named_file": "a.jpg",
         "review_flags": ["nomor_nota"]},
        {"vendor": "Kedai Kopi", "tanggal": "23/10/2026", "nomor_nota": "K-9",
         "total": "45,50", "mata_uang": "MYR", "named_file": "b.jpg",
         "review_flags": []},
    ]


class CsvTest(TempDbCase):

    def test_kolom_lengkap_dan_urutan_tetap(self):
        path = exports.to_csv(sample(), self.data_dir / "hasil.csv")
        with open(path, encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(list(rows[0].keys()),
                         ["Vendor", "Tanggal", "Nomor Nota", "Total", "Mata Uang",
                          "Nama File", "Perlu Dicek"])
        self.assertEqual(len(rows), 2)

    def test_penanda_periksa_ikut_tertulis(self):
        path = exports.to_csv(sample(), self.data_dir / "hasil.csv")
        with open(path, encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(rows[0]["Perlu Dicek"], "nomor_nota")
        self.assertEqual(rows[1]["Perlu Dicek"], "")

    def test_berkas_memakai_bom_supaya_excel_tidak_mengacak_aksen(self):
        path = exports.to_csv(sample(), self.data_dir / "hasil.csv")
        self.assertEqual(path.read_bytes()[:3], b"\xef\xbb\xbf")

    def test_tanpa_hasil_tetap_menghasilkan_header(self):
        hasil = exports.to_csv([], None)
        self.assertIn("Vendor", hasil)
        self.assertEqual(len(hasil.strip().splitlines()), 1)


class XlsxTest(TempDbCase):

    def test_total_jadi_angka_di_excel(self):
        from openpyxl import load_workbook
        path = exports.to_xlsx(sample(), self.data_dir / "hasil.xlsx")
        sheet = load_workbook(path).active
        self.assertEqual(sheet.cell(row=2, column=4).value, 1250000)
        # koma desimal dari nota Malaysia tetap angka
        self.assertAlmostEqual(sheet.cell(row=3, column=4).value, 45.5)

    def test_baris_perlu_dicek_diberi_warna(self):
        from openpyxl import load_workbook
        path = exports.to_xlsx(sample(), self.data_dir / "hasil.xlsx")
        sheet = load_workbook(path).active
        self.assertEqual(sheet.cell(row=2, column=1).fill.fgColor.rgb, "00FFF3CD")
        self.assertNotEqual(sheet.cell(row=3, column=1).fill.fgColor.rgb, "00FFF3CD")

    def test_header_tebal(self):
        from openpyxl import load_workbook
        path = exports.to_xlsx(sample(), self.data_dir / "hasil.xlsx")
        sheet = load_workbook(path).active
        self.assertTrue(sheet.cell(row=1, column=1).font.bold)


class NumberTest(unittest.TestCase):

    def test_titik_ribuan_tidak_diartikan_desimal(self):
        # "1.250" pada nota Indonesia berarti seribu dua ratus lima puluh
        self.assertEqual(exports._as_number("1.250"), 1250)

    def test_koma_desimal_dikenali(self):
        self.assertEqual(exports._as_number("45,50"), 45.5)

    def test_teks_bukan_angka_dibiarkan(self):
        self.assertIsNone(exports._as_number("lihat struk"))

    def test_kosong_tidak_menjadi_nol(self):
        self.assertIsNone(exports._as_number(""))


if __name__ == "__main__":
    unittest.main()
