import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class EventEnvelope:
    event_id: str
    event_type: str
    occurred_at: str
    source: str
    data: dict[str, Any]

    @classmethod
    def create(cls, event_type: str, source: str, data: dict[str, Any]) -> "EventEnvelope":
        return cls(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            occurred_at=datetime.now(timezone.utc).isoformat(),
            source=source,
            data=data,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at,
            "source": self.source,
            "data": self.data,
        }

