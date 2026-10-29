# JAMS School Maintenance — MVP v0.1

Aplikasi web Bahasa Melayu untuk pelaporan kerosakan sekolah. **Bukan produk KPM atau integrasi sistem rasmi KPM.** Data Buku Prestij 2026 digunakan sebagai rujukan awal jenis lokasi dan kuantiti, tanpa menukar sumber rasmi.

## Jalankan secara lokal

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
export SECRET_KEY="$(python -c 'import secrets;print(secrets.token_hex(32))')"
export ADMIN_EMAIL="admin@example.com"
export ADMIN_PASSWORD="tukar-kata-laluan-yang-panjang"
python app.py
```

Buka http://127.0.0.1:5000. Akaun admin dicipta hanya semasa pangkalan data kosong. Jika `ADMIN_PASSWORD` tidak ditetapkan, kata laluan rawak dipaparkan dalam terminal semasa pertama kali dijalankan.

## Fungsi tersedia
- Login dan akaun pengguna pelbagai peranan
- 381 unit placeholder lokasi daripada 73 jenis lokasi dalam CSV; **belum disahkan sebagai bilik individu**
- Pelaporan kerosakan dengan gambar yang dilindungi login dan kawalan akses
- Dashboard laporan dan statistik status
- Penugasan pemeriksa, rekod pemeriksaan, status dan jejak tindakan
- Pengesahan nama, blok dan aras lokasi oleh pengurusan

## Had MVP (belum untuk data sebenar/produksi)
Belum tersedia: CSRF protection, rate limiting, reset password, email notifications, real-time updates, pengurusan approval berasaskan state machine ketat, audit untuk semua perubahan lokasi, backup automatik, migrasi schema, antivirus upload, kuota per fail, pemisahan multi-sekolah, pengujian menyeluruh, penyimpanan cloud, deployment production, dan perlindungan data peribadi penuh. **Jangan deploy terbuka di internet atau guna data peribadi sebenar sebelum hardening keselamatan.**

## Ujian manual
1. Login admin, tambah pengguna pelapor dan pemeriksa.
2. Login pelapor, buat laporan dengan gambar, lihat status.
3. Login admin, tugaskan pemeriksa.
4. Login pemeriksa, rekod penemuan dan status.
5. Login admin, luluskan dan tutup kes.
6. Semak pelapor tidak boleh melihat laporan pengguna lain atau foto mereka.

## Struktur
`app.py` backend Flask/SQLite; `templates/` halaman; `static/` CSS; `data/locations.csv` import asal; `uploads/` fail bukti setempat (tidak dikomit).
