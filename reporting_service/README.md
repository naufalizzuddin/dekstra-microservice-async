# reporting_service

Reporting Service memegang read model dashboard dan notifikasi.

Service ini akan memegang:

- `profile_read_model`
- `dashboard_summary`
- `dashboard_chart_daily`
- `notifikasi`

Prinsip:

- `/profil/`, `/dashboard/`, dan `/notifikasi/` membaca dari database sendiri.
- Data diperbarui oleh event consumer, bukan cross-database join.
- Consumer harus idempotent dengan tabel `processed_event`.
