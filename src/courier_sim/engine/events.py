"""Deterministic immutable logistics-event creation."""

from datetime import datetime

from courier_sim.engine.models import EntityType, EventType, LogisticsEvent, WorldState


class EventRecorder:
    """Allocate event IDs from the working state without touching storage."""

    def __init__(self, state: WorldState) -> None:
        self._state = state
        self._events: list[LogisticsEvent] = []

    @property
    def events(self) -> tuple[LogisticsEvent, ...]:
        return tuple(self._events)

    def record(
        self,
        *,
        event_type: EventType,
        occurred_at: datetime,
        primary_entity_type: EntityType,
        primary_entity_id: str,
        summary: str,
        originating_command: str,
        related_entity_ids: tuple[str, ...] = (),
        data: dict[str, object] | None = None,
    ) -> LogisticsEvent:
        event = LogisticsEvent(
            event_id=f"EVT-{self._state.next_event_sequence:06d}",
            simulation_run_id=self._state.simulation_run_id,
            event_type=event_type,
            occurred_at=occurred_at,
            primary_entity_type=primary_entity_type,
            primary_entity_id=primary_entity_id,
            related_entity_ids=related_entity_ids,
            summary=summary,
            data=data or {},
            originating_command=originating_command,
        )
        self._state.next_event_sequence += 1
        self._events.append(event)
        return event
