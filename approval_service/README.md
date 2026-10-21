# approval_service

Service ini menangani workflow persetujuan surat.

Service ini akan memegang proses:

- daftar task persetujuan
- detail task persetujuan
- approve dan reject pengajuan
- perubahan tahap pengajuan
- event `surat.approved_by_*`, `surat.rejected`, dan `surat.completed`

Prinsip migrasi:

- Jangan query database `user_service`.
- Data approval masih memakai `document_db` karena tahap dan status melekat pada `PermohonanSurat`.
- Render dokumen final tetap dijalankan oleh `document_generation_worker` melalui queue `document`.
