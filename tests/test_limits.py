"""Cek perilaku batas token secara langsung."""
import os, tempfile, unittest
os.environ["NOTA_DATA_DIR"] = tempfile.mkdtemp()

from tests.base import TempDbCase
import config, db
from services import limits


class LimitsTest(TempDbCase):

    def test_tolak_saat_biaya_melewati_batas(self):
        db.upsert_chat(1001, allowed=1, daily_receipts=100, daily_tokens=0)
        db.add_usage(1001, 1, "m", 400, 50)
        config.DAILY_TOKENS_PER_CHAT = 100
        try:
            with self.assertRaises(limits.QuotaExceeded):
                limits.check_token_budget(1001)
        finally:
            pass

    def test_lolos_saat_masih_di_bawah_batas(self):
        db.upsert_chat(1001, allowed=1, daily_receipts=100, daily_tokens=100_000)
        db.add_usage(1001, 1, "m", 400, 50)
        limits.check_token_budget(1001)   # tidak melempar

    def test_jatah_nota_menolak_kiriman_terlalu_besar(self):
        db.upsert_chat(1001, allowed=1, daily_receipts=5)
        with self.assertRaises(limits.QuotaExceeded):
            limits.check_before_start(1001, 10)

    def test_ringkasan_memakai_batas_dari_chat(self):
        db.upsert_chat(1001, allowed=1, daily_receipts=7, daily_tokens=1234)
        hasil = limits.summary(1001)
        self.assertEqual(hasil["receipts_limit"], 7)
        self.assertEqual(hasil["tokens_limit"], 1234)


if __name__ == "__main__":
    unittest.main()
