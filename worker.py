"""Worker: satu thread yang mengambil pekerjaan menunggu, satu per satu.

Kenapa bukan langsung diproses di webhook:
  - model bisa lambat, webhook harus dijawab dalam hitungan detik;
  - kalau container mati, pekerjaan tetap ada di basis data dan lanjut lagi;
  - jumlah panggilan model bisa dibatasi tanpa memblokir user.

Kenapa satu thread, bukan banyak:
  mesin ini punya RAM sekitar 1 GB. Dua panggilan model bersamaan tidak
  menambah kecepatan (modelnya antre juga di sisi penyedia) tapi menaikkan
  risiko container dibunuh kehabisan memori.
"""
import logging
import threading
import time
import traceback
from pathlib import Path

import config
import db
from bot import reply, telegram
from services import convert, extract, limits, sources
from services.schema import normalize

log = logging.getLogger("nota.worker")

POLL_SECONDS = 3.0
# Jeda antar suntingan pesan progres (detik). Telegram membatasi suntingan.
PROGRESS_JEDA = 2.0


class Worker:
    def __init__(self, stop_event=None):
        self.stop_event = stop_event or threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="nota-worker", daemon=True)
        self._thread.start()
        log.info("worker jalan, menunggu pekerjaan")

    def stop(self):
        self.stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                job = db.claim_next_job()
            except Exception:
                log.exception("gagal membaca antrean")
                self.stop_event.wait(POLL_SECONDS)
                continue

            if job is None:
                self.stop_event.wait(POLL_SECONDS)
                continue

            try:
                self.run_job(job)
            except Exception as exc:
                log.exception("pekerjaan %s gagal di luar dugaan", job["id"])
                db.set_job_status(job["id"], "failed", error=str(exc)[:500])
            finally:
                db.close()   # thread ini memakai koneksi sendiri

    def _failed_file_count(self, job_id):
        return sum(1 for row in db.files_for_job(job_id) if row["status"] == "failed")

    def _tampilkan_progres(self, job_id, paksa=False):
        """Sunting pesan progres milik pekerjaan ini.

        Dibatasi satu suntingan tiap PROGRESS_JEDA detik. Telegram membatasi
        jumlah suntingan per chat, dan tanpa jeda satu PDF 20 halaman akan
        memicu penolakan yang tidak perlu.

        Kegagalan menyunting diabaikan: progres itu pelengkap, bukan syarat.
        Hasil akhir tetap dikirim lewat _kabari_selesai.
        """
        try:
            job = db.get_job(job_id)
            if job is None or not job.get("progress_message_id"):
                return
            sekarang = time.time()
            if not paksa and job.get("progress_at") and sekarang - job["progress_at"] < PROGRESS_JEDA:
                return

            db.set_job_progress_at(job_id, sekarang)
            telegram.edit_message(job["chat_id"], job["progress_message_id"],
                                  reply.progress_text(job))
        except Exception as exc:
            log.debug("pekerjaan %s: progres tidak bisa disunting — %s", job_id, exc)

    def run_job(self, job):
        """Selesaikan satu pekerjaan. Kegagalan dicatat di DB, tidak dilempar."""
        job_id = job["id"]
        log.info("pekerjaan %s mulai (chat %s, sumber %s)", job_id, job["chat_id"], job["source"])
        self._tampilkan_progres(job_id, paksa=True)

        try:
            incoming = self._prepare_files(job)
        except sources.SourceError as exc:
            # Unduhan yang tidak berhasil juga harus terhitung, kalau tidak
            # laporan akhirnya berbunyi "0 dari 0 berkas gagal" — menyesatkan.
            gagal = self._failed_file_count(job_id)
            pesan = str(exc)
            # Sumber galat kadang sudah menyebut jumlahnya; jangan diulang.
            if gagal and "gagal diunduh" not in pesan:
                pesan = f"{gagal} berkas gagal diunduh. {pesan}"
            db.set_job_status(job_id, "failed", error=pesan)
            log.warning("pekerjaan %s: %s", job_id, pesan)
            # Tanpa ini user tidak pernah tahu kirimannya gagal dan terus
            # menunggu hasil yang tidak akan datang.
            self._kabari_selesai(job)
            return

        if not incoming:
            db.set_job_status(job_id, "failed", error="tidak ada berkas untuk diproses")
            self._kabari_selesai(job)
            return

        work_dir = config.UPLOAD_DIR / f"job{job_id}"
        failed = 0
        # Kemajuan dihitung dalam satuan halaman, bukan berkas: satu PDF tiga
        # halaman berarti tiga nota yang dibaca satu per satu.
        selesai = 0
        total_halaman = 0

        for item in incoming:
            if self.stop_event.is_set():
                db.set_job_status(job_id, "cancelled", error="dihentikan")
                return
            try:
                limits.check_token_budget(job["chat_id"])
            except limits.QuotaExceeded as exc:
                db.set_job_status(job_id, "cancelled", error=str(exc))
                log.info("pekerjaan %s dihentikan: %s", job_id, exc)
                return

            file_id = item["file_id"]
            # Satu PDF berisi banyak halaman, dan setiap halaman adalah satu
            # nota. Jumlah halaman baru diketahui setelah berkas diunduh, jadi
            # batas atas progres disesuaikan di sini — kalau tidak, hitungannya
            # bisa melewati total ("6 dari 3").
            try:
                pages = convert.convert_file(item["path"], work_dir / "pages", name=item["filename"])
                # Satu PDF bisa berisi banyak nota. Semuanya dibaca, dan tiap
                # halaman menjadi satu baris tersendiri di tabel.
                total_halaman += len(pages)
                db.set_job_progress(job_id, selesai, total_halaman)

                for page in pages:
                    # Dipanggil lewat modul supaya tes bisa mengganti fungsinya.
                    table = extract.read_receipts([page.path])
                    limits.record(job["chat_id"], job_id, table)
                    receipt = normalize(table.payload, item["filename"])
                    db.add_receipt(file_id, item["filename"], receipt.as_dict(),
                                   receipt.review, raw_json=str(table.payload))
                    log.info("pekerjaan %s: %s halaman %s dalam %.1f detik",
                             job_id, item["filename"], page.page_no, table.seconds)
                    selesai += 1
                    db.set_job_progress(job_id, selesai)
                    self._tampilkan_progres(job_id)
                db.set_file_status(file_id, "done")
            except (convert.ConvertError, extract.ModelError, ValueError) as exc:
                failed += 1
                db.set_file_status(file_id, "failed", error=str(exc)[:500])
                selesai += 1
                total_halaman += 1
                db.set_job_progress(job_id, selesai, total_halaman)
                log.warning("pekerjaan %s: %s gagal — %s", job_id, item["filename"], exc)
            except Exception:
                failed += 1
                db.set_file_status(file_id, "failed", error="kesalahan tak terduga")
                log.error("pekerjaan %s: %s\n%s", job_id, item["filename"], traceback.format_exc())

            # Progres dihitung per halaman yang benar-benar dibaca (lihat di
            # atas), bukan per berkas — kalau keduanya dihitung, satu PDF tiga
            # halaman menambah kemajuan dua kali untuk isi yang sama.
            self._tampilkan_progres(job_id)

        total = len(incoming)
        # Berkas yang gagal diunduh tidak ikut masuk daftar `incoming`, jadi
        # harus dihitung terpisah. Yang gagal saat dibaca (model/galat) sudah
        # ada di `failed` — jangan dihitung dua kali.
        unduh_gagal = self._failed_file_count(job_id) - failed
        semua = total + unduh_gagal
        if failed + unduh_gagal >= semua:
            db.set_job_status(job_id, "failed", error=f"semua {semua} berkas gagal")
        else:
            jumlah_gagal = failed + unduh_gagal
            note = None if jumlah_gagal == 0 else f"{jumlah_gagal} dari {semua} berkas gagal"
            db.set_job_status(job_id, "done", error=note)
        log.info("pekerjaan %s selesai: %s/%s berhasil", job_id, semua - unduh_gagal - failed, semua)

        # Kabari user di sini, bukan di webhook: webhook sudah membalas Telegram
        # jauh sebelum pekerjaan selesai, dan tanpa langkah ini user hanya
        # melihat "masuk antrean" lalu tidak tahu hasilnya sudah jadi.
        self._kabari_selesai(job)

    def _kabari_selesai(self, job):
        """Kirim ringkasan hasil ke chat pemilik pekerjaan.

        Kegagalan mengabari dicatat saja — pekerjaannya sendiri sudah selesai
        dan datanya tersimpan, jadi tidak perlu mengulang pemrosesan.
        """
        job_id = job["id"]
        try:
            segar = db.get_job(job_id)
            if segar is None or segar["status"] == "cancelled":
                return

            penerima = db.receipts_for_job(job_id)
            if segar["status"] == "failed":
                telegram.send_message(segar["chat_id"], reply.failed_text(segar))
                return

            berkas = [row["filename"] for row in db.files_for_job(job_id)]
            gagal = self._failed_file_count(job_id)
            telegram.send_message(
                segar["chat_id"],
                reply.done_text(segar, penerima, failed_count=gagal, file_names=berkas),
                reply_markup=reply.exports_keyboard(job_id),
            )
        except Exception:
            log.error("pekerjaan %s: gagal mengabari chat\\n%s", job_id, traceback.format_exc())

    def _prepare_files(self, job):
        """Pastikan semua berkas ada di disk sebelum model dipanggil.

        Unduhan sengaja dilakukan di sini, bukan di webhook: mengunduh 50 berkas
        bisa lebih lama dari batas jawab Telegram, dan kalau pengunduhan gagal di
        tengah jalan, yang dicatat hanyalah berkas yang sudah lengkap.
        """
        job_id = job["id"]
        work_dir = config.UPLOAD_DIR / f"job{job_id}" / "src"
        work_dir.mkdir(parents=True, exist_ok=True)

        if job["source"] == "drive":
            if not job.get("drive_url"):
                raise sources.SourceError("link folder tidak tersimpan di pekerjaan ini")
            entries = sources.list_folder(job["drive_url"])
            db.set_job_total(job_id, len(entries))
            for file_id, name in entries:
                # Baris dibuat lebih dulu supaya jumlah berkas tidak bertambah di
                # tengah jalan — kalau folder berubah, totalnya sudah terkunci.
                db.add_file(job_id, name, remote_id=file_id)

        ready = []
        for row in db.pending_files(job_id):
            path = Path(row["path"]) if row["path"] else None
            if path and path.exists():
                ready.append({"file_id": row["id"], "filename": row["filename"], "path": path})
                continue

            try:
                if job["source"] == "drive":
                    item = sources.download_drive_file(row["remote_id"], row["filename"], work_dir)
                else:
                    item = sources.download_telegram_file(row["remote_id"], row["filename"], work_dir)
            except sources.SourceError as exc:
                db.set_file_status(row["id"], "failed", error=str(exc)[:500])
                db.bump_job_progress(job_id)
                log.warning("pekerjaan %s: %s tidak bisa diunduh — %s", job_id, row["filename"], exc)
                continue

            db.set_file_path(row["id"], item.path)
            ready.append({"file_id": row["id"], "filename": row["filename"], "path": item.path})

        if not ready:
            gagal = self._failed_file_count(job_id)
            pesan = (
                "tidak ada berkas yang berhasil diunduh. Kalau folder Drive, "
                "pastikan aksesnya 'siapa saja yang punya link'."
            )
            if gagal:
                pesan = f"{gagal} berkas gagal diunduh. {pesan}"
            raise sources.SourceError(pesan)
        return ready
