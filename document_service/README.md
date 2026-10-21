# document_service

Service ini akan memegang:

- `JenisSurat`
- `PermohonanSurat`
- `BerkasPermohonan`
- `RiwayatPersetujuan`
- `DokumenSurat`

Prinsip migrasi:

- Simpan snapshot pemohon saat pengajuan dibuat.
- Jangan query database `user_service`.
- Upload berkas tetap berada di service ini karena bergantung pada `nomor_permohonan`.
- Publish event `surat.created` dan `surat.attachment_uploaded`.
- Render dokumen final dijalankan oleh `document_generation_worker` melalui queue `document`.
- Service ini tetap menjadi sumber kebenaran data pengajuan, berkas, dan metadata dokumen.
