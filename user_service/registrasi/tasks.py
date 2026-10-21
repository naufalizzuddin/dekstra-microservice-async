from celery import shared_task


@shared_task
def publish_registrasi_outbox():
    return "registrasi outbox publisher placeholder"

