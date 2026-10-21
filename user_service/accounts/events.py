from django.utils import timezone

from dekstra_shared.events import EventEnvelope

from .models import OutboxEvent


SOURCE = "user_service"


def save_outbox_event(event_type: str, data: dict) -> dict:
    envelope = EventEnvelope.create(event_type=event_type, source=SOURCE, data=data)
    payload = envelope.as_dict()
    OutboxEvent.objects.create(
        event_id=payload["event_id"],
        event_type=payload["event_type"],
        source=payload["source"],
        payload=payload,
    )
    return payload


def mark_event_published(event_id: str):
    OutboxEvent.objects.filter(event_id=event_id, published_at__isnull=True).update(
        published_at=timezone.now()
    )
