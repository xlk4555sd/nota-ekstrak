"""Tes konversi berkas: gambar dan PDF harus jadi JPEG yang bisa dikirim ke model."""
import tempfile
import unittest
from pathlib import Path

import pymupdf
from PIL import Image

from services import convert

from tests.base import TempDbCase  # noqa: F401  (memasang sys.path)


class ConvertTest(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="nota-conv-"))
        self.out = self.tmp / "out"

    def _make_image(self, name="nota.png", size=(3000, 4000)):
        path = self.tmp / name
        Image.new("RGB", size, "white").save(path)
        return path

    def _make_pdf(self, pages=2):
        path = self.tmp / "nota.pdf"
        doc = pymupdf.open()
        for index in range(pages):
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 72), f"NOTA {index + 1}")
        doc.save(path)
        doc.close()
        return path

    def test_pdf_dipecah_per_halaman(self):
        hasil = convert.convert_file(self._make_pdf(pages=3), self.out)
        self.assertEqual(len(hasil), 3)
        self.assertEqual([p.page_no for p in hasil], [1, 2, 3])
        self.assertTrue(all(p.path.suffix == ".jpg" for p in hasil))
        self.assertTrue(all(p.path.exists() for p in hasil))

    def test_nama_berkas_halaman_tetap_terlacak(self):
        hasil = convert.convert_file(self._make_pdf(pages=1), self.out, name="faktur merek A.pdf")
        self.assertEqual(hasil[0].name, "faktur merek A.pdf")
        self.assertIn("faktur merek A__p001", hasil[0].path.name)

    def test_gambar_besar_dikecilkan(self):
        hasil = convert.convert_file(self._make_image(size=(4000, 5000)), self.out)
        self.assertEqual(len(hasil), 1)
        with Image.open(hasil[0].path) as img:
            self.assertLessEqual(max(img.size), 2000)

    def test_gambar_tetap_satu_halaman_tanpa_nomor(self):
        hasil = convert.convert_file(self._make_image(), self.out)
        self.assertIsNone(hasil[0].page_no)

    def test_format_asing_ditolak_dengan_pesan_jelas(self):
        path = self.tmp / "nota.docx"
        path.write_bytes(b"bukan gambar")
        with self.assertRaises(convert.ConvertError) as ctx:
            convert.convert_file(path, self.out)
        self.assertIn("belum didukung", str(ctx.exception))

    def test_pdf_rusak_tidak_melempar_error_mentah(self):
        path = self.tmp / "rusak.pdf"
        path.write_bytes(b"%PDF-1.4 tapi isinya sampah")
        with self.assertRaises(convert.ConvertError) as ctx:
            convert.convert_file(path, self.out)
        self.assertIn("tidak bisa dibaca", str(ctx.exception))

    def test_gambar_rusak_ditolak(self):
        path = self.tmp / "rusak.jpg"
        path.write_bytes(b"bukan jpeg sungguhan")
        with self.assertRaises(convert.ConvertError):
            convert.convert_file(path, self.out)

    def test_pdf_melebihi_batas_halaman_ditolak(self):
        import config
        asli = config.MAX_PDF_PAGES
        config.MAX_PDF_PAGES = 2
        try:
            with self.assertRaises(convert.ConvertError) as ctx:
                convert.convert_file(self._make_pdf(pages=3), self.out)
            self.assertIn("batasnya", str(ctx.exception))
        finally:
            config.MAX_PDF_PAGES = asli


if __name__ == "__main__":
    unittest.main()
