# PRD — nota.ekstrak v1

Bot Telegram: nota (foto/PDF) → tabel terstruktur → CSV/Excel.

Diperbarui 24 Okt 2026 setelah uji nyata terhadap model (bukan asumsi).

---

## 1. Masalah

Staf admin/finance mengetik ulang nota ke Excel. Lambat, salah ketik, tidak bisa dicari.

## 2. Pengguna

- **Pembuat** (kamu): memakai sendiri, melihat biaya & akurasi.
- **Orang lain**: diizinkan lewat daftar chat ID, dengan jatah harian.

## 3. Satu alur utama

```
kirim foto/PDF  →  bot antre  →  model baca  →  tabel tinjau  →  user betulkan  →  CSV/Excel
kirim link Drive publik  →  ┘
```

Tidak ada fitur lain di v1.

## 4. Keluaran data (6 kolom, sengaja sedikit)

`nama_file` · `vendor` · `tanggal` · `nomor_nota` · `total` · `mata_uang`

Aturan:
- `tanggal` dinormalkan ke `DD/MM/YYYY`, walau sumbernya `12-01-19`.
- `total` = angka tanpa pemisah ribuan (`1250000`, bukan `1.250.000`).
- `mata_uang` = kode 3 huruf (`IDR`, `MYR`, `USD`).
- Kosong = string kosong, **tidak boleh dikarang**.

## 5. Masukan yang diterima

| Jenis | Diterima | Catatan |
|---|---|---|
| JPG / PNG / WebP | Ya | langsung ke model |
| PDF | Ya | **dirender per halaman jadi JPG dulu** — model tidak menerima PDF |
| Link folder Google Drive publik | Ya | "Anyone with the link – Viewer", isi langsung (bukan subfolder) |
| Tulisan tangan | Tidak | ditolak dengan pesan jelas |
| Format lain (DOCX, ZIP, HEIC) | Tidak | ditolak dengan pesan jelas |

## 6. Aturan antrean (jawaban masalah 30 nota)

- **1 kiriman = 1 pekerjaan**, bukan 30 pekerjaan. Satu orang mengantre satu kali.
- Di dalam pekerjaan, nota dikerjakan **berurutan**, maksimal **5 gambar per panggilan model** (batas aman dari uji).
- **Maks 50 berkas** per pekerjaan. Lebih → ditolak sebelum diproses, bukan berhenti di tengah.
- **Maks 1 pekerjaan aktif per orang.** Yang kedua masuk daftar tunggu.
- Kemajuan dilaporkan dengan **satu pesan yang diperbarui** (`12/30`), bukan 30 pesan.
- Tombol **Batalkan** tersedia; jatah yang sudah terpakai tidak dikembalikan.

## 7. Kejujuran hasil (keputusan dari uji nyata)

- Setiap kolom punya **tingkat keyakinan**; kolom ragu ditandai `⚠` di tabel tinjau.
- **`nomor_nota` selalu masuk daftar periksa** — pada uji 5 nota, kolom inilah yang salah baca (1 dari 5).
- Kalau model gagal/keluar dari format: **coba ulang 1×** dengan instruksi lebih ketat, lalu tandai `GAGAL`. Tidak mengarang isi.
- Nota yang gagal **tidak menggagalkan** nota lain dalam pekerjaan yang sama.

## 8. Batas biaya

- Hitung token masuk/keluar per panggilan, simpan di DB.
- **Jatah harian per chat ID** (jumlah nota + token). Habis → berhenti dengan pesan sopan.
- Batas global harian sebagai pengaman kalau ada yang menyalahgunakan.
- Tidak ada pemotongan biaya diam-diam: perintah `biaya` menampilkan pemakaian hari ini.

## 9. Di luar cakupan v1 (jangan dikerjakan)

Web/antarmuka browser · login akun · pembayaran · multi-bahasa UI · rincian barang per baris
· pencarian · grafik · aplikasi HP · Notion/Google Sheets langsung · pelatihan model sendiri.

## 10. Ukuran keberhasilan

Diukur pada data uji berlabel (**`eval/score.py`**, sumber SROIE):
- tepat `vendor` ≥ 85%
- tepat `tanggal` ≥ 90%
- tepat `total` ≥ 80%
- tepat `nomor_nota` ≥ 70%

Angka final ditulis apa adanya di README, termasuk yang gagal.

**Baseline terukur (5 nota, 24 Okt 2026):** vendor 5/5 · tanggal 5/5 · total 5/5 · nomor 4/5.

## 11. Risiko yang sudah diketahui

| Risiko | Kenyataan | Sikap |
|---|---|---|
| Nota rupiah `Rp 1.250.000` | **belum diuji** | uji sebelum klaim akurasi Indonesia |
| Nota bertumpuk dalam 1 gambar | akurasi nomor turun (terbukti) | kirim gambar terpisah, bukan halaman gabungan |
| Kuota Drive | 200 berkas beruntun bisa kena batas | jeda + coba ulang |
| Link Drive bocor | siapa pun bisa lihat | jangan simpan URL di log, peringatan sekali |
| Saldo API | bisa habis oleh orang lain | daftar izin + jatah harian wajib |
