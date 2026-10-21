from celery import shared_task
from django.core.files.base import ContentFile

from .document_generator import generate_final_document
from .events import save_outbox_event


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def generate_document(self, permohonan_id):
    from .models import DokumenSurat, PermohonanSurat

    permohonan = PermohonanSurat.objects.select_related("jenis_surat").get(id=permohonan_id)
    dokumen, _ = DokumenSurat.objects.get_or_create(permohonan=permohonan)
    dokumen.status_generate = DokumenSurat.StatusGenerate.DIPROSES
    dokumen.error_message = None
    dokumen.save(update_fields=["status_generate", "error_message"])

    try:
        content, extension = generate_final_document(permohonan, dokumen)
        if dokumen.file_final:
            dokumen.file_final.delete(save=False)
        dokumen.file_final.save(f"surat_{dokumen.public_token}.{extension}", ContentFile(content), save=False)
        dokumen.status_generate = DokumenSurat.StatusGenerate.SELESAI
        dokumen.error_message = None
        dokumen.save(update_fields=["file_final", "status_generate", "error_message"])

        save_outbox_event(
            "document.generated",
            {
                "permohonan_id": permohonan.id,
                "nomor_permohonan": permohonan.nomor_permohonan,
                "jenis_surat_kode": permohonan.jenis_surat.kode,
                "jenis_surat_nama": permohonan.jenis_surat.nama,
                "pemohon_user_id": permohonan.pemohon_user_id,
                "pemohon_nik": permohonan.pemohon_nik_snapshot,
                "pemohon_nama": permohonan.pemohon_nama_snapshot,
                "rt": permohonan.pemohon_rt_snapshot,
                "rw": permohonan.pemohon_rw_snapshot,
                "public_token": str(dokumen.public_token),
                "download_url": f"/berkas/{dokumen.public_token}",
                "file_extension": extension,
            },
        )
        return str(dokumen.public_token)
    except Exception as exc:
        dokumen.status_generate = DokumenSurat.StatusGenerate.GAGAL
        dokumen.error_message = str(exc)
        dokumen.save(update_fields=["status_generate", "error_message"])
        raise


@shared_task
def publish_surat_outbox():
    return "surat outbox publisher placeholder"
