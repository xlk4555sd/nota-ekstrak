"""Tes kerapian jawaban model: nilai bersih, mata uang, dan penanda periksa."""
import unittest

from tests.base import TempDbCase  # noqa: F401  (memasang sys.path)
from services.schema import normalize


class NormalizeTest(unittest.TestCase):

    def test_merapikan_spasi_berlebih(self):
        hasil = normalize({"vendor": "  Toko   Maju  Jaya "})
        self.assertEqual(hasil.vendor, "Toko Maju Jaya")

    def test_bagian_yang_tidak_ada_menjadi_kosong(self):
        hasil = normalize({"vendor": "Toko A"})
        self.assertEqual(hasil.tanggal, "")
        self.assertEqual(hasil.total, "")

    def test_nilai_none_tidak_menjadi_teks_none(self):
        hasil = normalize({"total": None})
        self.assertEqual(hasil.total, "")

    def test_angka_dari_model_tidak_diformat_ulang(self):
        # 1500.5 harus tetap "1500.5", bukan dibulatkan jadi "1500"
        hasil = normalize({"total": 1500.5})
        self.assertEqual(hasil.total, "1500.5")

    def test_mata_uang_ditebak_dari_total_rupiah(self):
        hasil = normalize({"total": "Rp 1.250.000"})
        self.assertEqual(hasil.mata_uang, "IDR")

    def test_mata_uang_ditebak_dari_ringgit(self):
        hasil = normalize({"total": "RM 60.30"})
        self.assertEqual(hasil.mata_uang, "MYR")

    def test_simbol_dua_huruf_dilengkapi_jadi_kode(self):
        # Uji nyata: model menjawab "RM" padahal diminta kode tiga huruf.
        hasil = normalize({"total": "9.00", "mata_uang": "RM"})
        self.assertEqual(hasil.mata_uang, "MYR")

    def test_mata_uang_yang_sudah_ada_dipertahankan(self):
        hasil = normalize({"total": "1.000", "mata_uang": "sgd"})
        self.assertEqual(hasil.mata_uang, "SGD")

    def test_nomor_nota_selalu_masuk_daftar_periksa(self):
        hasil = normalize({"vendor": "A", "tanggal": "24/10/2026",
                           "nomor_nota": "INV-001", "total": "10", "mata_uang": "IDR"})
        self.assertIn("nomor_nota", hasil.review)

    def test_kolom_kosong_masuk_daftar_periksa(self):
        hasil = normalize({"vendor": "", "tanggal": "", "nomor_nota": "",
                           "total": "", "mata_uang": ""})
        self.assertEqual(sorted(hasil.review), ["nomor_nota", "tanggal", "total", "vendor"])

    def test_tanggal_tidak_diubah_formatnya(self):
        # Mengubah diam-diam bisa menyembunyikan salah baca tahun.
        hasil = normalize({"tanggal": "12-01-19"})
        self.assertEqual(hasil.tanggal, "12-01-19")

    def test_json_yang_dibungkus_penjelasan_tetap_terbaca(self):
        hasil = normalize('Berikut hasilnya: {"vendor": "Toko"}')
        self.assertEqual(hasil.vendor, "Toko")

    def test_teks_bukan_json_ditolak_dengan_pesan_jelas(self):
        with self.assertRaises(ValueError) as ctx:
            normalize("maaf saya tidak bisa membaca gambar ini")
        self.assertIn("JSON", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
