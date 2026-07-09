from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class TraceEvent(BaseModel):
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class TraceRecorder:
    """Append-only trace recorder for agent execution."""

    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def record(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.append(TraceEvent(event_type=event_type, payload=payload))

    def dump(self) -> list[dict[str, Any]]:
        return [event.model_dump() for event in self.events]
