"""Simulation-state, scheduled-action, and immutable event models."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Literal, Self
from zoneinfo import ZoneInfo

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from courier_sim.domain.models import LogisticsScenario

AwareDateTime = Annotated[datetime, AwareDatetime]
PERSISTENCE_VERSION = "2.0"
BUCHAREST = ZoneInfo("Europe/Bucharest")


def _freeze_json_value(value: object) -> object:
    """Recursively freeze JSON-like event metadata."""
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_json_value(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_json_value(item) for item in value)
    return value


def _thaw_json_value(value: object) -> object:
    """Convert frozen metadata back into ordinary JSON-compatible containers."""
    if isinstance(value, Mapping):
        return {str(key): _thaw_json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [_thaw_json_value(item) for item in value]
    return value


class EventType(StrEnum):
    SIMULATION_INITIALIZED = "SIMULATION_INITIALIZED"
    TIME_ADVANCED = "TIME_ADVANCED"
    PARCEL_STATUS_CHANGED = "PARCEL_STATUS_CHANGED"
    SHIPMENT_STATUS_CHANGED = "SHIPMENT_STATUS_CHANGED"
    ROUTE_ASSIGNED = "ROUTE_ASSIGNED"
    ROUTE_STARTED = "ROUTE_STARTED"
    ROUTE_COMPLETED = "ROUTE_COMPLETED"


class EntityType(StrEnum):
    SIMULATION = "SIMULATION"
    PARCEL = "PARCEL"
    SHIPMENT = "SHIPMENT"
    ROUTE = "ROUTE"


class ScheduledActionType(StrEnum):
    SHIPMENT_ARRIVAL = "SHIPMENT_ARRIVAL"


class ScheduledAction(BaseModel):
    """A deterministic future action that has not happened yet."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    action_id: str
    action_type: ScheduledActionType
    execute_at: AwareDateTime
    creation_sequence: Annotated[int, Field(gt=0)]
    entity_id: str
    data: dict[str, object] = Field(default_factory=dict)

    @field_validator("execute_at", mode="after")
    @classmethod
    def execute_at_uses_bucharest_zone(cls, value: datetime) -> datetime:
        return value.astimezone(BUCHAREST)


class LogisticsEvent(BaseModel):
    """An immutable fact appended to one simulation run's history."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    simulation_run_id: str
    event_type: EventType
    occurred_at: AwareDateTime
    primary_entity_type: EntityType
    primary_entity_id: str
    related_entity_ids: tuple[str, ...] = ()
    summary: str
    data: Mapping[str, object] = Field(default_factory=dict)
    originating_command: str

    @field_validator("data", mode="after")
    @classmethod
    def data_is_deeply_immutable(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        frozen = _freeze_json_value(value)
        if not isinstance(frozen, Mapping):  # pragma: no cover - field type guarantees this
            raise TypeError("event data must be a mapping")
        return frozen

    @field_serializer("data")
    def serialize_data(self, value: Mapping[str, object]) -> object:
        return _thaw_json_value(value)


class WorldState(BaseModel):
    """Everything required to resume the active simulation exactly."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    persistence_version: Literal["2.0"] = PERSISTENCE_VERSION
    simulation_run_id: str
    scenario_seed: int
    current_datetime: AwareDateTime
    scenario: LogisticsScenario
    scheduled_actions: list[ScheduledAction] = Field(default_factory=list)
    next_event_sequence: Annotated[int, Field(gt=0)] = 1
    next_scheduled_action_sequence: Annotated[int, Field(gt=0)] = 1

    @field_validator("current_datetime", mode="after")
    @classmethod
    def current_datetime_uses_bucharest_zone(cls, value: datetime) -> datetime:
        return value.astimezone(BUCHAREST)

    @model_validator(mode="after")
    def simulation_state_is_consistent(self) -> Self:
        if self.scenario.timezone != "Europe/Bucharest":
            raise ValueError("simulation scenario timezone must be Europe/Bucharest")
        action_ids = [action.action_id for action in self.scheduled_actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("scheduled action IDs must be unique")
        creation_sequences = [action.creation_sequence for action in self.scheduled_actions]
        if len(creation_sequences) != len(set(creation_sequences)):
            raise ValueError("scheduled action creation sequences must be unique")
        for action in self.scheduled_actions:
            if action.execute_at < self.current_datetime:
                raise ValueError(
                    f"pending scheduled action {action.action_id} is earlier than simulation time"
                )
        return self


class CommandResult(BaseModel):
    """The atomically produced state and new events from one valid command."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    state: WorldState
    events: tuple[LogisticsEvent, ...] = ()
