# CashFlow V4 — Deploy Ready

Versi ini mempertahankan fitur CashFlow V4 dan menambahkan konfigurasi agar bisa dijalankan di hosting Python seperti Render.

## Menjalankan di laptop

Windows Command Prompt:

```bat
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python app.py
```

Buka `http://127.0.0.1:5001`.

## File tambahan untuk deploy

- `requirements.txt` — termasuk Gunicorn.
- `Procfile` — perintah start untuk hosting.
- `render.yaml` — konfigurasi Render Blueprint.
- `.gitignore` — mencegah `.venv`, database lokal, dan file rahasia ikut ke GitHub.
- `/health` — endpoint health check.

## Environment variables

- `CASHFLOW_SECRET` — wajib menggunakan nilai rahasia saat online. `render.yaml` dapat membuatnya otomatis.
- `DATABASE_PATH` — opsional. Jika hosting menyediakan persistent disk, arahkan ke lokasi database di disk tersebut, contoh `/var/data/cashflow_v4.db`.
- `PORT` — biasanya diberikan otomatis oleh hosting.

## Deploy ke Render

1. Upload isi folder ini ke repository GitHub. Jangan upload `.venv` atau `cashflow_v4.db`.
2. Di Render, buat Web Service dari repository tersebut, atau gunakan Blueprint jika `render.yaml` terdeteksi.
3. Build command: `pip install -r requirements.txt`.
4. Start command: `gunicorn app:app`.
5. Pastikan `CASHFLOW_SECRET` tersedia sebagai environment variable.
6. Setelah deployment selesai, Render memberikan URL publik HTTPS.

## Penting tentang database SQLite

Aplikasi tetap menggunakan SQLite agar fitur dan struktur V4 tidak berubah. Pada hosting dengan filesystem sementara, database bisa hilang saat instance dibuat ulang. Untuk penggunaan jangka panjang, gunakan persistent disk lalu set `DATABASE_PATH` ke file di disk tersebut. Jangan commit database berisi akun atau transaksi pengguna ke GitHub.
