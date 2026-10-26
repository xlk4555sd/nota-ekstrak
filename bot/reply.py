"""Semua kalimat yang dilihat user, dan tombol-tombolnya.

Dikumpulkan di satu tempat supaya nada bicaranya konsisten dan mudah diperbaiki
tanpa menyentuh logika. Yang dijaga:
  - tidak ada istilah teknis ("webhook", "token", "API");
  - batas disebut apa adanya, bukan disembunyikan;
  - tidak menjanjikan ketepatan yang belum terbukti.
"""
import config
from bot.format import cut, plain, rupiah_friendly
from services.schema import FIELDS

FIELD_LABEL = {
    "vendor": "nama toko",
    "tanggal": "tanggal",
    "nomor_nota": "nomor nota",
    "total": "total",
    "mata_uang": "mata uang",
}

SUPPORTED = "PDF, JPG, PNG, atau WebP"


def start_text():
    return (
        "<b>nota.ekstrak</b>\n"
        "Kirim foto nota atau PDF, saya susun jadi tabel.\n\n"
        f"• Satu berkas maksimal {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB\n"
        f"• Satu PDF maksimal {config.MAX_PDF_PAGES} halaman\n"
        f"• Satu kiriman maksimal {config.MAX_FILES_PER_JOB} berkas\n\n"
        "Banyak nota sekaligus? Unggah ke satu folder Google Drive, atur akses "
        "menjadi <i>siapa saja yang punya link</i>, lalu kirim link foldernya "
        "ke sini.\n\n"
        "Hasilnya bisa diunduh sebagai CSV atau Excel.\n\n"
        "Ketik /help kalau ingin penjelasan lengkap."
    )


def help_text():
    """Penjelasan cara pakai, bukan sekadar daftar perintah.

    Yang dijawab berurutan sesuai pertanyaan yang paling sering muncul:
    bagaimana mengirim, apa yang terjadi setelah dikirim, apa yang harus
    diperiksa, dan bagaimana menghapus. Istilah teknis dihindari.
    """
    return (
        "<b>Cara pakai</b>\n\n"
        "<b>1. Mengirim nota</b>\n"
        f"Kirim foto atau berkas {SUPPORTED} langsung ke chat ini.\n"
        "Boleh beberapa sekaligus — semuanya masuk ke satu tabel.\n\n"
        "<b>2. Banyak nota dari Drive</b>\n"
        "Unggah ke satu folder Google Drive, atur akses menjadi "
        "<i>siapa saja yang punya link</i>, lalu tempel link foldernya ke sini. "
        "Link ke satu berkas tidak bisa dipakai.\n\n"
        "<b>3. Yang terjadi setelah dikirim</b>\n"
        "Nota masuk antrean dan diproses satu per satu. Satu pesan akan "
        "berubah sendiri dari <i>menunggu</i> menjadi <i>memproses</i> lalu "
        "<i>selesai</i>. Boleh ditinggal, hasilnya tetap dikirim.\n\n"
        "<b>4. Mengambil hasil</b>\n"
        "Setelah selesai, ambil lewat tombol <b>Unduh CSV</b> atau "
        "<b>Unduh Excel</b>.\n\n"
        "<b>5. Yang perlu diperiksa</b>\n"
        "Kolom yang diisi: " + ", ".join(FIELD_LABEL[f] for f in FIELDS) + ".\n"
        "Kalau ada nota yang ditandai, artinya kolom itu belum terbaca yakin. "
        "Periksa dulu sebelum dipakai.\n\n"
        "<b>6. Batas yang perlu diketahui</b>\n"
        f"• Satu berkas maksimal {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB\n"
        f"• Satu PDF maksimal {config.MAX_PDF_PAGES} halaman\n"
        f"• Satu kiriman maksimal {config.MAX_FILES_PER_JOB} berkas\n"
        "• Hanya satu kiriman berjalan per chat, supaya hasil tidak tertukar\n\n"
        "<b>Perintah</b>\n"
        "/help — penjelasan ini\n"
        "/status — kiriman yang berjalan dan sisa jatah hari ini\n"
        "/batal — hentikan kiriman yang sedang berjalan\n"
        "/delete — hapus kiriman yang sudah selesai"
    )


def delete_help_text(jobs):
    """Daftar kiriman yang bisa dihapus, beserta cara menghapusnya."""
    bisa = [j for j in jobs if j["status"] in ("done", "failed", "cancelled")]
    if not bisa:
        return (
            "<b>Belum ada yang bisa dihapus</b>\n\n"
            "Hanya kiriman yang sudah selesai, gagal, atau dihentikan yang bisa "
            "dihapus. Kiriman yang masih berjalan hentikan dulu dengan /batal."
        )

    lines = ["<b>Hapus kiriman</b>", ""]
    for job in bisa[:15]:
        lines.append(
            f"#{job['id']} — {_status_indonesia(job['status'])}, "
            f"{job['total_files']} berkas"
        )
    if len(bisa) > 15:
        lines.append(f"dan {len(bisa) - 15} kiriman lain lebih lama")

    lines += [
        "",
        "Ketik <code>/delete NOMOR</code> untuk menghapus satu kiriman.",
        "Ketik <code>/delete semua</code> untuk menghapus semuanya.",
        "Yang dihapus: berkas asli, hasil tabel, dan berkas CSV/Excel-nya.",
    ]
    return "\n".join(lines)


def delete_confirm_all_text(jumlah):
    return (
        f"<b>Hapus semua kiriman?</b>\n\n"
        f"{jumlah} kiriman yang sudah selesai akan dihapus beserta berkas dan "
        f"hasilnya. Ini tidak bisa dibatalkan.\n\n"
        f"Ketik <code>/delete ya</code> kalau yakin."
    )


def delete_done_text(job_id, info):
    """Kabar setelah satu kiriman terhapus."""
    return (
        f"<b>Terhapus</b> #{job_id}\n"
        f"{info['berkas']} berkas dan {info['hasil']} baris hasil dihapus "
        f"({_ukuran(info['byte'])})."
    )


def delete_done_all_text(hasil):
    teks = (
        f"<b>{len(hasil['dihapus'])} kiriman terhapus</b>\n"
        f"{hasil['hasil']} baris hasil dibuang ({_ukuran(hasil['byte'])})."
    )
    if hasil["dilewati"]:
        nomor = ", ".join(f"#{i}" for i in hasil["dilewati"])
        teks += f"\nMasih berjalan, tidak dihapus: {nomor}."
    return teks


def delete_refused_text(reason):
    return plain(reason)


def delete_not_found_text(job_id):
    return f"Kiriman #{job_id} tidak ada, atau bukan milikmu."


def delete_usage_text():
    return (
        "Formatnya belum saya mengerti.\n"
        "Ketik /delete untuk melihat daftar, atau /delete NOMOR."
    )


def _status_indonesia(status):
    return {
        "done": "selesai",
        "failed": "gagal",
        "cancelled": "dihentikan",
        "pending": "menunggu",
        "running": "berjalan",
    }.get(status, status)


def _ukuran(byte):
    if byte < 1024:
        return f"{byte} byte"
    if byte < 1024 * 1024:
        return f"{byte / 1024:.0f} KB"
    return f"{byte / (1024 * 1024):.1f} MB"


def not_allowed_text(chat_id):
    return (
        "Nomor chat ini belum terdaftar.\n"
        "Minta pemilik bot menambahkan ID di bawah ini:\n\n"
        f"<code>{chat_id}</code>"
    )


def rejected_text(reason):
    return f"Belum bisa diproses: {plain(reason)}"


def single_file_text():
    return (
        "Itu link ke satu berkas, bukan folder.\n"
        "Kalau berkasnya ada di perangkat ini: kirim berkasnya langsung ke chat ini.\n"
        "Kalau di Drive: unggah ke satu folder, atur akses <i>siapa saja yang "
        "punya link</i>, lalu kirim link foldernya."
    )


def unsupported_text():
    return f"Formatnya belum didukung. Kirim {SUPPORTED}."


def queued_text(job_id, file_count):
    return (
        f"<b>Diterima.</b> {file_count} berkas masuk antrean.\n"
        "Saya kabari di sini begitu selesai. Prosesnya satu per satu, jadi "
        "kalau ada kiriman lain, ini menunggu dulu."
    )


def antre_text(job):
    """Pesan pertama, dikirim sebelum worker menyentuh berkas.

    Sengaja menyebut "menunggu" dengan jujur: pekerjaan bisa duduk di antrean
    kalau ada kiriman lain di depan. Pesan ini nanti disunting jadi
    `progress_text`, jadi user hanya punya satu pesan yang berubah — bukan
    rentetan pesan baru.
    """
    total = job.get("total_files") or 0
    return (
        f"<b>Menunggu antrean</b> #{job['id']}\n"
        f"{_bar(0, total)} 0 dari {total}\n"
        "Berkas sedang saya ambil, sebentar lagi mulai dibaca."
    )


def busy_text(job_id):
    return (
        f"Masih ada kiriman yang berjalan (#{job_id}).\n"
        "Kirim lagi setelah yang itu selesai, supaya hasilnya tidak tertukar."
    )


def progress_text(job):
    total = job["total_files"] or 0
    done = job["done_files"] or 0
    status = job.get("status") or "running"

    if done >= total and total:
        kepala = f"<b>Merapikan hasil</b> #{job['id']}"
        catatan = "Semua berkas sudah terbaca. Tabelnya sedang disusun."
    elif done > 0:
        # Sudah ada berkas terbaca, jadi apa pun status catatannya pekerjaan
        # ini nyata-nyata berjalan. Status di DB bisa masih "pending" sesaat
        # karena baru ditandai saat worker mengambil pekerjaan.
        kepala = f"<b>Memproses</b> #{job['id']}"
        catatan = f"Sedang membaca berkas {done + 1} dari {total}."
    elif status == "pending":
        kepala = f"<b>Menunggu antrean</b> #{job['id']}"
        catatan = "Berkas sudah saya terima, tinggal menunggu giliran."
    else:
        kepala = f"<b>Memproses</b> #{job['id']}"
        catatan = f"Sedang membaca berkas {done + 1} dari {total}."

    return (
        f"{kepala}\n"
        f"{_bar(done, total)} {done} dari {total}\n"
        f"{catatan}\n"
        "Boleh ditinggal, nanti saya kirim sendiri hasilnya."
    )


def done_text(job, receipts=None, failed_count=0, file_names=None):
    receipts = receipts or []
    file_names = file_names or []
    lines = [f"<b>Selesai</b> #{job['id']}"]

    if failed_count:
        lines.append(f"{len(receipts)} nota terbaca, {failed_count} gagal.")

    if not receipts:
        lines.append("Tidak ada nota yang berhasil dibaca.")
        return "\n".join(lines)

    # Nama berkas selalu disebut, sekalipun tidak ada yang perlu dicek: satu
    # PDF kerap berisi banyak nota, dan user perlu tahu baris mana berasal
    # dari halaman mana.
    lines.append("")
    names = file_names or [r["named_file"] for r in receipts]
    for name in names[:8]:
        lines.append(f"• {cut(name)}")
    if len(names) > 8:
        lines.append(f"• dan {len(names) - 8} berkas lain")

    attention = [r for r in receipts if r.get("review_flags")]
    if attention:
        lines.append("")
        lines.append(f"{len(attention)} nota perlu dicek dulu:")
        for item in attention[:5]:
            fields = ", ".join(FIELD_LABEL.get(f, f) for f in item["review_flags"])
            lines.append(f"  {cut(item['named_file'])} — {fields}")
        if len(attention) > 5:
            lines.append(f"  dan {len(attention) - 5} lainnya")
    else:
        lines.append("")
        lines.append("Semua kolom terbaca, tapi tetap periksa sebelum dipakai.")

    lines.append("")
    lines.append("Ambil berkasnya lewat tombol di bawah.")
    return "\n".join(lines)


def failed_text(job):
    reason = job.get("error") or "penyebabnya tidak tercatat"
    return (
        f"<b>Gagal</b> #{job['id']}\n"
        f"{plain(reason)}\n\n"
        "Coba kirim ulang. Kalau PDF-nya besar, pecah jadi beberapa berkas."
    )


def quota_text(reason):
    return (
        f"<b>Jatah hari ini habis</b>\n{plain(reason)}\n\n"
        "Jatah dihitung per hari dan kembali besok."
    )


def status_text(job, quota):
    lines = ["<b>Status</b>"]
    if job:
        lines.append(
            f"Kiriman #{job['id']}: {job['status']} "
            f"({job['done_files']} dari {job['total_files']})"
        )
    else:
        lines.append("Tidak ada kiriman yang berjalan.")

    lines.append(
        f"Hari ini: {quota['receipts']} dari {quota['receipts_limit']} nota, "
        f"{rupiah_friendly(quota['tokens'])} dari "
        f"{rupiah_friendly(quota['tokens_limit'])} token."
    )
    return "\n".join(lines)


def cancelled_text(job_id):
    return f"Kiriman #{job_id} dihentikan."


def no_active_text():
    return "Tidak ada kiriman yang sedang berjalan."


def empty_result_text():
    return "Tidak ada hasil untuk diunduh dari kiriman itu."


def exports_keyboard(job_id):
    return {"inline_keyboard": [[
        {"text": "Unduh CSV", "callback_data": f"csv:{job_id}"},
        {"text": "Unduh Excel", "callback_data": f"xlsx:{job_id}"},
    ]]}


def cancel_keyboard(job_id):
    return {"inline_keyboard": [[
        {"text": "Hentikan", "callback_data": f"cancel:{job_id}"},
    ]]}


def _bar(done, total, width=10):
    if total <= 0:
        return "░" * width
    done = min(done, total)          # data sesaat bisa saja belum sinkron
    filled = min(width, round(width * done / total))
    return "█" * filled + "░" * (width - filled)
