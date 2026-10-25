"""Tes pesan yang dilihat user.

Yang diuji bukan selera bahasa, tapi tiga hal yang mahal kalau salah:
  - teks user yang mengandung <, >, & tidak membuat Telegram menolak pesan;
  - nama berkas yang sangat panjang tidak memotong kalimat lain;
  - pesan gagal selalu menyebut sebabnya, tidak pernah kosong.
"""
import unittest

from tests.base import ROOT  # noqa: F401  (menyiapkan sys.path)
from bot import reply


class TeksTest(unittest.TestCase):
    def test_kurung_siku_dari_user_tidak_merusak_html(self):
        teks = reply.done_text(
            {"id": 7},
            receipts=[{"named_file": "<nota & faktur>.jpg", "review_flags": []}],
        )
        self.assertNotIn("<nota", teks)
        self.assertIn("&lt;nota", teks)
        self.assertIn("&amp;", teks)

    def test_nama_berkas_panjang_dipotong(self):
        nama = "a" * 200 + ".jpg"
        keluaran = reply.done_text({"id": 1}, receipts=[{"named_file": nama, "review_flags": ["total"]}])
        self.assertLess(len(keluaran), 600)
        self.assertIn("…", keluaran)

    def test_nota_perlu_dicek_disebut_terpisah(self):
        teks = reply.done_text(
            {"id": 3},
            receipts=[
                {"named_file": "a.jpg", "review_flags": ["total"]},
                {"named_file": "b.jpg", "review_flags": ["tanggal", "vendor"]},
            ],
        )
        self.assertIn("2 nota perlu dicek", teks)
        self.assertIn("total", teks)
        self.assertIn("tanggal, nama toko", teks)

    def test_tanpa_perlu_dicek_tetap_menyuruh_periksa(self):
        teks = reply.done_text({"id": 3}, receipts=[{"named_file": "a.jpg", "review_flags": []}])
        self.assertIn("tetap periksa", teks)

    def test_kegagalan_tanpa_sebab_tetap_punya_kalimat(self):
        teks = reply.failed_text({"id": 9, "error": None})
        self.assertIn("Gagal", teks)
        self.assertIn("tidak tercatat", teks)

    def test_gagal_sebagian_menyebut_jumlah(self):
        teks = reply.done_text({"id": 4}, receipts=[{"named_file": "a.jpg", "review_flags": []}],
                               failed_count=2)
        self.assertIn("1 nota terbaca, 2 gagal", teks)

    def test_jatah_habis_menyebut_sebab(self):
        teks = reply.quota_text("sudah 50 dari 50 nota")
        self.assertIn("50 dari 50", teks)
        self.assertIn("besok", teks)

    def test_status_memakai_angka_bulat_dari_db(self):
        teks = reply.status_text(None, {"receipts": 3, "receipts_limit": 50,
                                        "tokens": 12000, "tokens_limit": 200000})
        self.assertIn("3 dari 50", teks)
        self.assertIn("12.000", teks)
        self.assertIn("Tidak ada kiriman", teks)

    def test_progres_tidak_pernah_melebihi_total(self):
        teks = reply.progress_text({"id": 1, "done_files": 9, "total_files": 5})
        self.assertIn("9 dari 5", teks)
        self.assertNotIn("█" * 11, teks)


if __name__ == "__main__":
    unittest.main()
