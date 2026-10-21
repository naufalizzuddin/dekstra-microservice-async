from celery import shared_task


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def generate_document(self, permohonan_id):
    raise RuntimeError(
        "Document rendering is handled by document_generation_worker. "
        "Run document-generation-worker from document_generation_worker."
    )


@shared_task
def publish_surat_outbox():
    return "surat outbox publisher placeholder"
