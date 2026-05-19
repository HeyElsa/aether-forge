"""Lightweight structured observability hooks."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ObservabilityEvent:
    """One structured runtime event emitted by the runner or session."""

    kind: str
    artifact_set_id: str | None = None
    environment: str | None = None
    session_id: str | None = None
    tick: int | None = None
    step_id: str | None = None
    capability_id: str | None = None
    severity: str = "info"
    message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: f"evt_{uuid4().hex}")
    recorded_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the JSON shape used by event sinks."""
        return {
            "eventId": self.event_id,
            "kind": self.kind,
            "recordedAt": self.recorded_at,
            "severity": self.severity,
            "artifactSetId": self.artifact_set_id,
            "environment": self.environment,
            "sessionId": self.session_id,
            "tick": self.tick,
            "stepId": self.step_id,
            "capabilityId": self.capability_id,
            "message": self.message,
            "details": self.details,
        }


class EventSink(Protocol):
    """Receives structured observability events.

    The runner and runtime call ``emit`` synchronously, so sink implementations
    should be fast and should never raise for expected transport failures.
    Long-running exports should enqueue and flush out of band.

    Canonical signature: ``emit(event: ObservabilityEvent) -> None``.

    Minimum viable implementation::

        class PrintSink:
            def emit(self, event: ObservabilityEvent) -> None:
                print(event.to_dict())

    Reference implementation: :class:`aether_forge.ListEventSink` for tests
    and :class:`aether_forge.LoggingEventSink` for production JSON logs.
    """

    def emit(self, event: ObservabilityEvent) -> None: ...


@dataclass(slots=True)
class ListEventSink:
    """In-memory event sink for tests and local inspection."""

    events: list[ObservabilityEvent] = field(default_factory=list)

    def emit(self, event: ObservabilityEvent) -> None:
        self.events.append(event)


@dataclass(slots=True)
class CompositeEventSink:
    """Fan out events to multiple sinks."""

    sinks: tuple[EventSink, ...]

    @classmethod
    def from_sinks(cls, *sinks: EventSink | None) -> CompositeEventSink | None:
        active = tuple(sink for sink in sinks if sink is not None)
        return cls(active) if active else None

    def emit(self, event: ObservabilityEvent) -> None:
        for sink in self.sinks:
            emit_observability_event(sink, event)


@dataclass(slots=True)
class LoggingEventSink:
    """Emit observability events through the standard logging system."""

    logger_name: str = "aether_forge.events"

    def emit(self, event: ObservabilityEvent) -> None:
        event_logger = logging.getLogger(self.logger_name)
        event_logger.setLevel(logging.INFO)
        payload = event.to_dict()
        level = event.severity.lower()
        if level == "error":
            event_logger.error("observability event: %s", event.kind, extra={"aether_event": payload})
        elif level in {"warning", "warn"}:
            event_logger.warning("observability event: %s", event.kind, extra={"aether_event": payload})
        else:
            event_logger.info("observability event: %s", event.kind, extra={"aether_event": payload})


@dataclass(slots=True)
class JsonlEventSink:
    """Append observability events directly to a JSONL file."""

    path: str | Path

    def emit(self, event: ObservabilityEvent) -> None:
        path = Path(self.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf8") as handle:
            handle.write(json.dumps(event.to_dict(), default=str) + "\n")


def emit_observability_event(sink: EventSink | None, event: ObservabilityEvent) -> None:
    """Emit an event without letting sink failures affect agent execution."""
    if sink is None:
        return
    try:
        sink.emit(event)
    except Exception as error:
        logger.warning("observability sink failed for %s: %s", event.kind, error)
