# Arsitektur — nota.ekstrak v1

Dokumen ini menjelaskan **kenapa** sistem dibentuk begini. Untuk PRD lihat `PRD.md`.

---

## 1. Gambaran besar

```
 Telegram  ──webhook──>  Flask (gunicorn)  ──>  services/  ──>  model (river.ai)
                            │                     │
                         db.py (SQLite)       worker antrean
                            │                     │
                       data/ (berkas + DB)   eval/ (skor akurasi)
```

Antarmuka = chat. **Tidak ada `templates/`, tidak ada `static/`** — tidak ada halaman web di v1.

## 2. Alur satu pekerjaan

```
1. Pesan masuk (foto | dokumen PDF | link Drive)
2. routes/webhook.py  → validasi chat ID + jatah → buat job  → balas "diterima, 0/N"
3. worker (thread di dalam proses) mengambil job
4. sources.py   → daftar berkas: unduh dari Telegram ATAU Drive
5. convert.py   → PDF di-render jadi JPG per halaman; JPG dikecilkan ke sisi max 2000 px
6. extract.py   → kirim ≤5 gambar ke model, minta JSON ketat, validasi skema
7. simpan ke DB (fields + confidence + usage token)
8. edit pesan progres setiap 5 nota / setiap 10 detik
9. selesai → kirim 1 CSV (dan tombol "kirim Excel")
```

## 3. Enam keputusan dan alasannya

**a. Model tidak dipanggil dari route.**
Route hanya menerima dan membuat job. Kalau model lambat/mati, route tetap cepat menjawab. Ini juga yang membuat webhook tidak timeout dan user tidak mengirim ulang 3 kali.

**b. Pekerjaan = baris di DB, bukan thread yang hidup.**
Kalau container mati, job tetap `pending` dan lanjut setelah hidup. Thread yang hilang = pekerjaan hilang, dan itu tidak boleh terjadi karena user sudah mengirim berkasnya.

**c. Satu worker, berurutan.**
RAM mesin ini ~996 MB tersedia. Dua worker bersamaan tidak menambah kecepatan yang berarti tapi menaikkan risiko kehabisan memori dan memboroskan token saat retry.

**d. Keluaran model dipaksa JSON lalu divalidasi.**
Model tidak boleh menjawab bebas. Bila bentuknya melenceng: **coba ulang 1×** dengan pesan lebih ketat, lalu `GAGAL`. Dua percobaan, bukan tak terbatas — biaya harus bisa diprediksi.

**e. PDF diubah jadi gambar lebih dulu.**
Terbukti dari uji: model **tidak menerima PDF** (menjawab "tidak ada dokumen"). Hanya JPEG/PNG/GIF/WebP. Konversi = `pymupdf` pada 150 DPI.

**f. Batas 5 gambar per panggilan.**
Uji 5 nota dalam satu panggilan = benar semua. Di atas 5 belum diuji, jadi tidak dijanjikan. Menumpuk semua nota jadi satu gambar terbukti **menurunkan** ketepatan nomor — jadi dilarang.

## 4. Bentuk data

**`jobs`** — 1 kiriman
```
id · chat_id · source (telegram|drive) · status (pending|running|done|failed|cancelled)
total_files · done_files · created_at · started_at · finished_at · error
```

**`files`** — 1 berkas di dalam pekerjaan
```
id · job_id · filename · kind (image|pdf_page) · page_no · status · error
```

**`receipts`** — hasil baca per nota
```
id · file_id · vendor · tanggal · nomor_nota · total · mata_uang
confidence_json · review_flags · corrected_by_user (0|1) · raw_json
```

**`corrections`** — apa yang dibetulkan manusia
```
id · receipt_id · field · value_before · value_after · created_at
```

**`usage`** — biaya
```
id · chat_id · job_id · model · prompt_tokens · completion_tokens · created_at
```

**`chat_limits`** — izin & jatah
```
chat_id · allowed (0|1) · daily_receipts · daily_tokens · note
```

Kenapa `corrections` terpisah dari `receipts`: koreksi manusia adalah **data untuk mengukur model**, bukan sekadar edit. Kalau ditimpa, buktinya hilang.

## 5. Struktur folder

```
nota-ekstrak/
├── PRD.md
├── ARSITEKTUR.md
├── README.md
├── requirements.txt
├── .env.example              variabel saja, tanpa nilai
├── .gitignore                .env · data/ · *.db · .venv
├── config.py                 setelan, batas biaya, baca .env
├── app.py                    factory Flask + daftar route
├── db.py                     SATU-SATUNYA penulis SQL + migrasi kolom
├── worker.py                 pengambil job, orkestrasi, pembaruan progres
├── bot/
│   ├── webhook.py            terima update Telegram, verifikasi secret token
│   ├── reply.py              kirim pesan, edit pesan, kirim berkas
│   └── keyboards.py          tombol: CSV · Excel · Batalkan · Periksa
├── services/
│   ├── sources.py            Telegram & Drive → daftar berkas lokal
│   ├── convert.py            PDF→JPG (pymupdf), kecilkan gambar (Pillow)
│   ├── extract.py            panggilan model, skema JSON, validasi, 1× retry
│   ├── export.py             CSV & XLSX (openpyxl)
│   └── limits.py             cek izin chat, jatah harian, catat token
├── routes/
│   ├── webhook.py            POST /telegram/<secret>
│   └── health.py             GET /healthz
├── data/                     unggahan + SQLite — DI LUAR REPO
├── eval/
│   ├── dataset/              nota uji + kunci jawaban (JSON)
│   ├── fetch.py              unduh contoh SROIE via datasets-server
│   └── score.py              akurasi per kolom → tabel di README
└── tests/
    ├── base.py               model DIPALSUKAN, DB sementara
    ├── test_convert.py       PDF 1 halaman & multi halaman → JPG
    ├── test_extract.py       JSON valid, JSON rusak, timeout, HTTP 500
    ├── test_limits.py        ditolak, jatah habis, batas global
    ├── test_queue.py         urutan, batal, lanjut setelah mati
    ├── test_export.py        CSV & XLSX: encoding, angka, tanggal
    └── test_webhook.py       chat tak diizinkan, berkas kebesaran, format salah
```

## 6. Aturan yang tidak boleh dilanggar

- **Rahasia tidak masuk repo.** `.env` berisi `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `RIVER_API_KEY`. `.env.example` hanya nama variabel.
- **`data/` di luar git.** Isinya nota orang — data pribadi.
- **`db.py` satu-satunya penulis SQL.** Tidak ada `execute` di route/service. Ini yang membuat tes bisa memakai DB sementara dengan aman.
- **Semua panggilan ke luar punya timeout.** Model: 60 detik. Drive: 20 detik. Telegram: 30 detik. Tanpa timeout, satu permintaan macet memblokir seluruh antrean.
- **Tidak ada `except: pass`.** Setiap kegagalan tercatat di kolom `error` dan tampil ke user.
- **Format uang & tanggal dinormalkan di satu tempat** (`services/extract.py`), bukan tersebar.

## 7. Isolasi untuk tes

Tes **tidak pernah** memanggil API berbayar:

```python
# tests/base.py
model = FakeModel({
    "invoice_a.jpg": {"vendor": "Toko A", "tanggal": "24/10/2026",
                      "nomor_nota": "A-1", "total": 1250000, "mata_uang": "IDR"},
})
```

Model palsu bisa disuruh **gagal**, **lambat**, atau **mengembalikan JSON rusak** — tiga hal yang paling sering terjadi di dunia nyata dan paling jarang dites orang. Ini yang membuat tes cepat (detik), gratis, dan deterministik.

## 8. Cara menilai diri sendiri

`eval/score.py` membandingkan `receipts` dengan kunci jawaban dataset dan mencetak:

```
vendor       87%   (target 85%)
tanggal      95%   (target 90%)
total        84%   (target 80%)
nomor_nota   72%   (target 70%)
```

Angka ini masuk README. **Yang gagal disebut juga**, karena portofolio yang hanya memuat angka bagus tidak dipercaya senior.

## 9. Biaya & batas (angka nyata dari uji)

- 1 nota ≈ **400 token masuk + 50 token keluar**, ~2 detik.
- 5 nota dalam 1 panggilan ≈ **1.590 token masuk**, ~4,5 detik.
- 100 nota ≈ **40.000 token masuk** (≈20 panggilan).
- Model: `deepseek-ai/DeepSeek-V4.1-Flash-1017` lewat river.ai. **GLM-5.3-Flash tidak dipakai** — pada uji model itu mengembalikan isi kosong dengan token alasan penuh.

## 10. Urutan pengerjaan

| Tahap | Isi | Selesai bila |
|---|---|---|
| 1 | `config.py` · `db.py` · `convert.py` | tes konversi PDF hijau |
| 2 | `extract.py` + model palsu | tes skema/rusak/timeout hijau |
| 3 | `worker.py` + `sources.py` | 1 kiriman ujung ke ujung jalan |
| 4 | `bot/` webhook + tombol | bot menjawab di Telegram |
| 5 | `export.py` CSV & XLSX | unduhan benar di Excel Indonesia |
| 6 | `limits.py` + `chat_limits` | orang tak diizinkan tertolak |
| 7 | `eval/score.py` | tabel akurasi di README |

Tahap 1–2 tidak butuh token Telegram maupun saldo API. Itu sebabnya dikerjakan lebih dulu.
