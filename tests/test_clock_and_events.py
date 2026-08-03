from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from conftest import make_state
from pydantic import ValidationError

from courier_sim.domain.enums import InboundShipmentStatus
from courier_sim.domain.models import InboundShipment
from courier_sim.engine.clock import BUCHAREST, ClockError, SimulationClock
from courier_sim.engine.commands import (
    AdvanceTimeCommand,
    AdvanceToCommand,
    NextScheduledActionCommand,
)
from courier_sim.engine.models import (
    EventType,
    LogisticsEvent,
    ScheduledAction,
    ScheduledActionType,
    WorldState,
)
from courier_sim.engine.processor import CommandProcessor


def test_initial_clock_is_timezone_aware_bucharest() -> None:
    state = make_state()

    assert state.current_datetime.tzinfo is not None
    assert state.current_datetime.astimezone(BUCHAREST).tzinfo == BUCHAREST


@pytest.mark.parametrize(
    ("amount", "expected"),
    [(timedelta(minutes=30), (11, 30)), (timedelta(hours=2), (13, 0))],
)
def test_advance_by_duration(amount: timedelta, expected: tuple[int, int]) -> None:
    result = CommandProcessor(make_state()).execute(AdvanceTimeCommand(amount))

    assert (result.state.current_datetime.hour, result.state.current_datetime.minute) == expected


def test_advance_to_future_datetime() -> None:
    target = datetime(2026, 3, 16, 12, 45, tzinfo=BUCHAREST)
    result = CommandProcessor(make_state()).execute(AdvanceToCommand(target))

    assert result.state.current_datetime == target


@pytest.mark.parametrize("amount", [timedelta(0), timedelta(minutes=-1)])
def test_zero_or_negative_advance_is_rejected(amount: timedelta) -> None:
    with pytest.raises(ClockError):
        CommandProcessor(make_state()).execute(AdvanceTimeCommand(amount))


def test_backward_advance_to_is_rejected() -> None:
    target = make_state().current_datetime - timedelta(minutes=1)
    with pytest.raises(ClockError):
        CommandProcessor(make_state()).execute(AdvanceToCommand(target))


def test_scheduled_arrival_crossed_during_advance() -> None:
    result = CommandProcessor(make_state()).execute(AdvanceTimeCommand(timedelta(hours=1)))
    shipment = next(
        item for item in result.state.scenario.inbound_shipments if item.shipment_id == "SHIP-002"
    )

    assert shipment.status is InboundShipmentStatus.ARRIVED
    assert not result.state.scheduled_actions
    assert [event.event_type for event in result.events] == [
        EventType.SHIPMENT_STATUS_CHANGED,
        EventType.TIME_ADVANCED,
    ]


def test_same_timestamp_actions_use_creation_sequence_order() -> None:
    state = make_state()
    third = next(
        item for item in state.scenario.inbound_shipments if item.shipment_id == "SHIP-003"
    )
    data = third.model_dump(mode="python")
    data.update(
        {
            "status": InboundShipmentStatus.IN_TRANSIT,
            "actual_arrival_at": None,
            "received_at": None,
        }
    )
    updated = InboundShipment.model_validate(data)
    state.scenario.inbound_shipments[2] = updated
    state.scheduled_actions.append(
        ScheduledAction(
            action_id="ACT-000002",
            action_type=ScheduledActionType.SHIPMENT_ARRIVAL,
            execute_at=state.scheduled_actions[0].execute_at,
            creation_sequence=2,
            entity_id="SHIP-003",
        )
    )
    state.next_scheduled_action_sequence = 3
    state = WorldState.model_validate(state.model_dump(mode="python"))
    result = CommandProcessor(state).execute(AdvanceTimeCommand(timedelta(hours=1)))

    shipment_events = [
        event.primary_entity_id
        for event in result.events
        if event.event_type is EventType.SHIPMENT_STATUS_CHANGED
    ]
    assert shipment_events == ["SHIP-002", "SHIP-003"]


def test_next_scheduled_action_and_empty_queue_behavior() -> None:
    processor = CommandProcessor(make_state())
    first = processor.execute(NextScheduledActionCommand())
    second = processor.execute(NextScheduledActionCommand())

    assert first.state.current_datetime.hour == 11
    assert first.state.current_datetime.minute == 30
    assert len(first.events) == 2
    assert second.events == ()
    assert second.state == first.state


def test_events_same_timestamp_get_unique_sequential_ids() -> None:
    result = CommandProcessor(make_state()).execute(NextScheduledActionCommand())

    assert [event.event_id for event in result.events] == ["EVT-000002", "EVT-000003"]
    assert result.events[0].occurred_at == result.events[1].occurred_at
    assert result.events[0].primary_entity_id == "SHIP-002"


def test_event_model_is_frozen() -> None:
    event = LogisticsEvent(
        event_id="EVT-000001",
        simulation_run_id="RUN-TEST",
        event_type=EventType.TIME_ADVANCED,
        occurred_at=datetime(2026, 3, 16, 11, tzinfo=ZoneInfo("Europe/Bucharest")),
        primary_entity_type="SIMULATION",
        primary_entity_id="RUN-TEST",
        summary="Test",
        originating_command="test",
    )

    with pytest.raises(ValidationError, match="frozen"):
        event.summary = "Changed"


def test_event_metadata_is_deeply_immutable() -> None:
    event = LogisticsEvent(
        event_id="EVT-000001",
        simulation_run_id="RUN-TEST",
        event_type=EventType.TIME_ADVANCED,
        occurred_at=datetime(2026, 3, 16, 11, tzinfo=BUCHAREST),
        primary_entity_type="SIMULATION",
        primary_entity_id="RUN-TEST",
        summary="Test",
        originating_command="test",
        data={"nested": {"action_ids": ["ACT-000001"]}},
    )

    with pytest.raises(TypeError):
        event.data["tampered"] = True
    with pytest.raises(TypeError):
        event.data["nested"]["tampered"] = True
    with pytest.raises(TypeError):
        event.data["nested"]["action_ids"][0] = "CHANGED"


def test_elapsed_advance_is_stable_across_dst_and_json_reload() -> None:
    base = make_state()
    data = base.model_dump(mode="python")
    data["current_datetime"] = datetime(2026, 3, 28, 23, tzinfo=BUCHAREST)
    data["scheduled_actions"] = []
    state = WorldState.model_validate(data)
    reloaded = WorldState.model_validate_json(state.model_dump_json())

    in_memory = CommandProcessor(state).execute(AdvanceTimeCommand(timedelta(hours=5)))
    after_reload = CommandProcessor(reloaded).execute(AdvanceTimeCommand(timedelta(hours=5)))

    assert reloaded.current_datetime.tzinfo == BUCHAREST
    assert in_memory.state.current_datetime == after_reload.state.current_datetime
    assert in_memory.state.current_datetime.isoformat() == "2026-03-29T05:00:00+03:00"


def test_naive_clock_is_rejected() -> None:
    with pytest.raises(ClockError, match="timezone-aware"):
        SimulationClock(datetime(2026, 3, 16, 11))
