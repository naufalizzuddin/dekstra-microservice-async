from dekstra_shared.events import EventEnvelope
from celery import current_app
from django.utils import timezone

from .models import OutboxEvent


SOURCE = "document_service"


def save_outbox_event(event_type: str, data: dict) -> dict:
    envelope = EventEnvelope.create(event_type=event_type, source=SOURCE, data=data)
    payload = envelope.as_dict()
    outbox = OutboxEvent.objects.create(
        event_id=payload["event_id"],
        event_type=payload["event_type"],
        source=payload["source"],
        payload=payload,
    )
    try:
        current_app.send_task("dashboard.tasks.project_event", args=[payload], queue="projection")
        current_app.send_task("dashboard.tasks.create_notification_from_event", args=[payload], queue="notification")
        outbox.published_at = timezone.now()
        outbox.save(update_fields=["published_at"])
    except Exception:
        # The row remains in outbox_event so a later publisher can retry it.
        pass
    return payload
