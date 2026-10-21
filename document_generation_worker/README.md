# document_generation_worker

Document Generation Worker adalah worker teknis dalam Document Context untuk render dokumen final.

Tanggung jawab utama:

- Mengambil task `surat.tasks.generate_document` dari queue `document`.
- Render template `.docx` dan `.xlsx`.
- Konversi hasil ke PDF memakai LibreOffice jika tersedia.
- Menambahkan QR/signature sesuai context dokumen.
- Mengirim event `document.generated` setelah file final selesai.

Worker ini tidak menentukan status approval dan tidak memutuskan apakah surat boleh selesai. Keputusan workflow tetap berada di `document_service`.
