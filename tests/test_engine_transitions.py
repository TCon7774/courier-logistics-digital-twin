from datetime import timedelta

import pytest
from conftest import make_state
from pydantic import ValidationError

from courier_sim.domain.enums import InboundShipmentStatus, ParcelStatus, RouteStatus
from courier_sim.domain.models import Parcel
from courier_sim.domain.transitions import TransitionError
from courier_sim.engine.commands import (
    AdvanceTimeCommand,
    AssignRouteCommand,
    CompleteRouteCommand,
    ParcelTransitionCommand,
    ShipmentTransitionCommand,
    StartRouteCommand,
)
from courier_sim.engine.models import EventType
from courier_sim.engine.processor import CommandError, CommandProcessor


def parcel(state, parcel_id: str):
    return next(item for item in state.scenario.parcels if item.parcel_id == parcel_id)


def shipment(state, shipment_id: str):
    return next(
        item for item in state.scenario.inbound_shipments if item.shipment_id == shipment_id
    )


def route(state, route_id: str):
    return next(item for item in state.scenario.routes if item.route_id == route_id)


def test_full_home_parcel_progression_uses_route_rules_and_confirmation() -> None:
    processor = CommandProcessor(make_state())
    for status in (
        ParcelStatus.RECEIVED,
        ParcelStatus.SCANNED,
        ParcelStatus.SORTED,
        ParcelStatus.STAGED_FOR_ROUTE,
    ):
        processor.execute(ParcelTransitionCommand("P-1005-A", status))
    processor.execute(AssignRouteCommand("ROUTE-03", "D-03", "VAN-03"))
    processor.execute(ParcelTransitionCommand("P-1005-A", ParcelStatus.LOADED))
    processor.execute(StartRouteCommand("ROUTE-03"))
    processor.execute(ParcelTransitionCommand("P-1005-A", ParcelStatus.OUT_FOR_DELIVERY))
    result = processor.execute(ParcelTransitionCommand("P-1005-A", ParcelStatus.DELIVERED_TO_HOME))

    updated = parcel(result.state, "P-1005-A")
    assert updated.delivery_confirmation_sent
    assert updated.delivery_confirmation_sent_at == result.state.current_datetime
    assert result.events[0].event_type is EventType.PARCEL_STATUS_CHANGED


def test_locker_delivery_and_collection_do_not_send_second_confirmation() -> None:
    processor = CommandProcessor(make_state())
    processor.execute(ParcelTransitionCommand("P-1008-A", ParcelStatus.LOADED))
    processor.execute(StartRouteCommand("ROUTE-02"))
    processor.execute(ParcelTransitionCommand("P-1008-A", ParcelStatus.OUT_FOR_DELIVERY))
    deposited = processor.execute(
        ParcelTransitionCommand("P-1008-A", ParcelStatus.DELIVERED_TO_LOCKER)
    )
    deposit_time = parcel(deposited.state, "P-1008-A").delivery_confirmation_sent_at
    processor.execute(AdvanceTimeCommand(timedelta(minutes=5)))
    collected = processor.execute(
        ParcelTransitionCommand("P-1008-A", ParcelStatus.COLLECTED_BY_CUSTOMER)
    )
    updated = parcel(collected.state, "P-1008-A")

    assert updated.delivery_confirmation_sent_at == deposit_time
    assert updated.collected_at == collected.state.current_datetime
    assert len(collected.events) == 1


def test_collection_fields_reject_time_before_deposit() -> None:
    data = parcel(make_state(), "P-1002-A").model_dump(mode="python")
    data["status"] = ParcelStatus.COLLECTED_BY_CUSTOMER
    data["collected_at"] = data["delivery_confirmation_sent_at"] - timedelta(minutes=1)

    with pytest.raises(ValidationError, match="cannot precede"):
        Parcel.model_validate(data)


def test_home_parcel_cannot_use_locker_completion() -> None:
    processor = CommandProcessor(make_state())
    processor.execute(StartRouteCommand("ROUTE-02"))
    processor.execute(ParcelTransitionCommand("P-1009-A", ParcelStatus.OUT_FOR_DELIVERY))

    with pytest.raises(TransitionError, match="PARCEL_LOCKER"):
        processor.execute(ParcelTransitionCommand("P-1009-A", ParcelStatus.DELIVERED_TO_LOCKER))


def test_home_parcel_cannot_be_collected_from_locker() -> None:
    data = parcel(make_state(), "P-1009-A").model_dump(mode="python")
    data.update(
        {
            "status": ParcelStatus.DELIVERED_TO_LOCKER,
            "delivery_confirmation_sent": True,
            "delivery_confirmation_sent_at": make_state().current_datetime,
        }
    )
    with pytest.raises(ValidationError, match="locker completion"):
        Parcel.model_validate(data)


def test_illegal_skipped_transition_is_atomic_and_creates_no_event() -> None:
    processor = CommandProcessor(make_state())
    before = processor.state

    with pytest.raises(TransitionError, match="allowed next states"):
        processor.execute(ParcelTransitionCommand("P-1005-A", ParcelStatus.OUT_FOR_DELIVERY))

    assert processor.state == before
    assert processor.state.next_event_sequence == before.next_event_sequence


def test_damage_review_return_and_reprocessing_branch() -> None:
    processor = CommandProcessor(make_state())
    processor.execute(ParcelTransitionCommand("P-1006-A", ParcelStatus.DAMAGE_REVIEW))
    processor.execute(ParcelTransitionCommand("P-1006-A", ParcelStatus.RETURNED_TO_WAREHOUSE))
    result = processor.execute(ParcelTransitionCommand("P-1006-A", ParcelStatus.STAGED_FOR_ROUTE))

    assert parcel(result.state, "P-1006-A").status is ParcelStatus.STAGED_FOR_ROUTE


@pytest.mark.parametrize(
    "outcome",
    [ParcelStatus.RETURNED_TO_SENDER, ParcelStatus.CANCELLED],
)
def test_damage_review_approved_terminal_outcomes(outcome: ParcelStatus) -> None:
    processor = CommandProcessor(make_state())
    result = processor.execute(ParcelTransitionCommand("P-1004-A", outcome))

    assert parcel(result.state, "P-1004-A").status is outcome


def test_failed_delivery_return_and_retry_branch() -> None:
    processor = CommandProcessor(make_state())
    processor.execute(StartRouteCommand("ROUTE-02"))
    processor.execute(ParcelTransitionCommand("P-1009-A", ParcelStatus.OUT_FOR_DELIVERY))
    processor.execute(ParcelTransitionCommand("P-1009-A", ParcelStatus.DELIVERY_FAILED))
    processor.execute(ParcelTransitionCommand("P-1009-A", ParcelStatus.RETURNED_TO_WAREHOUSE))
    result = processor.execute(ParcelTransitionCommand("P-1009-A", ParcelStatus.STAGED_FOR_ROUTE))

    assert parcel(result.state, "P-1009-A").status is ParcelStatus.STAGED_FOR_ROUTE


def test_loading_requires_an_assigned_route() -> None:
    processor = CommandProcessor(make_state())
    processor.execute(ParcelTransitionCommand("P-1006-A", ParcelStatus.SCANNED))
    processor.execute(ParcelTransitionCommand("P-1006-A", ParcelStatus.SORTED))
    processor.execute(ParcelTransitionCommand("P-1006-A", ParcelStatus.STAGED_FOR_ROUTE))

    with pytest.raises(TransitionError, match="assigned active route"):
        processor.execute(ParcelTransitionCommand("P-1006-A", ParcelStatus.LOADED))


@pytest.mark.parametrize(
    ("start", "progression"),
    [
        (
            "SHIP-002",
            [
                InboundShipmentStatus.ARRIVED,
                InboundShipmentStatus.RECEIVING,
                InboundShipmentStatus.PROCESSED,
            ],
        ),
        (
            "SHIP-002",
            [
                InboundShipmentStatus.ARRIVED,
                InboundShipmentStatus.RECEIVING,
                InboundShipmentStatus.PARTIALLY_RECEIVED,
                InboundShipmentStatus.PROCESSED,
            ],
        ),
    ],
)
def test_shipment_progressions(
    start: str,
    progression: list[InboundShipmentStatus],
) -> None:
    processor = CommandProcessor(make_state())
    for status in progression:
        result = processor.execute(ShipmentTransitionCommand(start, status))

    assert shipment(result.state, start).status is progression[-1]


def test_shipment_delay_branch_then_arrival() -> None:
    state = make_state()
    data = shipment(state, "SHIP-002").model_dump(mode="python")
    data["status"] = InboundShipmentStatus.IN_TRANSIT
    updated = type(shipment(state, "SHIP-002")).model_validate(data)
    state.scenario.inbound_shipments[1] = updated
    state = type(state).model_validate(state.model_dump(mode="python"))
    processor = CommandProcessor(state)
    processor.execute(ShipmentTransitionCommand("SHIP-002", InboundShipmentStatus.DELAYED))
    result = processor.execute(ShipmentTransitionCommand("SHIP-002", InboundShipmentStatus.ARRIVED))

    assert shipment(result.state, "SHIP-002").actual_arrival_at == result.state.current_datetime


def test_early_actual_arrival_is_valid() -> None:
    state = make_state()
    state.current_datetime = shipment(state, "SHIP-002").expected_arrival_at - timedelta(minutes=5)
    state.scheduled_actions = []
    processor = CommandProcessor(type(state).model_validate(state.model_dump(mode="python")))
    result = processor.execute(ShipmentTransitionCommand("SHIP-002", InboundShipmentStatus.ARRIVED))

    arrived = shipment(result.state, "SHIP-002")
    assert arrived.actual_arrival_at < arrived.expected_arrival_at


def test_manual_arrival_consumes_the_pending_scheduled_arrival() -> None:
    processor = CommandProcessor(make_state())
    arrived = processor.execute(
        ShipmentTransitionCommand("SHIP-002", InboundShipmentStatus.ARRIVED)
    )
    advanced = processor.execute(AdvanceTimeCommand(timedelta(hours=1)))

    assert not arrived.state.scheduled_actions
    assert arrived.events[0].data["consumed_scheduled_action_ids"] == ("ACT-000001",)
    assert len(advanced.events) == 1


def test_missing_shipment_cancels_obsolete_arrival_and_does_not_block_time() -> None:
    processor = CommandProcessor(make_state())

    missing = processor.execute(
        ShipmentTransitionCommand("SHIP-002", InboundShipmentStatus.MISSING)
    )
    advanced = processor.execute(AdvanceTimeCommand(timedelta(hours=1)))

    assert not missing.state.scheduled_actions
    assert missing.events[0].data["consumed_scheduled_action_ids"] == ("ACT-000001",)
    assert advanced.state.current_datetime.hour == 12


def test_invalid_shipment_transition_is_atomic() -> None:
    processor = CommandProcessor(make_state())
    before = processor.state

    with pytest.raises(TransitionError):
        processor.execute(ShipmentTransitionCommand("SHIP-001", InboundShipmentStatus.ARRIVED))

    assert processor.state == before


def test_valid_route_assignment_updates_all_directions() -> None:
    result = CommandProcessor(make_state()).execute(
        AssignRouteCommand("ROUTE-03", "D-03", "VAN-03")
    )
    assigned = route(result.state, "ROUTE-03")
    driver = next(item for item in result.state.scenario.drivers if item.driver_id == "D-03")
    vehicle = next(item for item in result.state.scenario.vehicles if item.vehicle_id == "VAN-03")

    assert assigned.status is RouteStatus.ASSIGNED
    assert assigned.historical_driver_id == "D-03"
    assert driver.current_vehicle_id == vehicle.vehicle_id
    assert vehicle.current_driver_id == driver.driver_id


@pytest.mark.parametrize(
    ("driver_id", "vehicle_id", "error"),
    [
        ("D-01", "VAN-03", "driver D-01 is not available"),
        ("D-03", "VAN-01", "vehicle VAN-01 is not available"),
    ],
)
def test_route_assignment_conflicts_are_rejected(
    driver_id: str,
    vehicle_id: str,
    error: str,
) -> None:
    with pytest.raises(CommandError, match=error):
        CommandProcessor(make_state()).execute(
            AssignRouteCommand("ROUTE-03", driver_id, vehicle_id)
        )


def test_route_assignment_rejects_driver_outside_shift() -> None:
    processor = CommandProcessor(make_state())
    processor.execute(AdvanceTimeCommand(timedelta(hours=8)))

    with pytest.raises(CommandError, match="outside the active shift"):
        processor.execute(AssignRouteCommand("ROUTE-03", "D-03", "VAN-03"))


def test_route_start_records_full_datetime_and_cannot_repeat() -> None:
    processor = CommandProcessor(make_state())
    first = processor.execute(StartRouteCommand("ROUTE-02"))

    assert route(first.state, "ROUTE-02").started_at == first.state.current_datetime
    with pytest.raises(TransitionError):
        processor.execute(StartRouteCommand("ROUTE-02"))


def test_route_start_rechecks_driver_shift() -> None:
    processor = CommandProcessor(make_state())
    processor.execute(AdvanceTimeCommand(timedelta(hours=8)))

    with pytest.raises(CommandError, match="outside the active shift"):
        processor.execute(StartRouteCommand("ROUTE-02"))


def test_route_cannot_complete_before_start_or_with_unresolved_parcels() -> None:
    processor = CommandProcessor(make_state())
    with pytest.raises(TransitionError):
        processor.execute(CompleteRouteCommand("ROUTE-02"))
    processor.execute(StartRouteCommand("ROUTE-02"))
    processor.execute(AdvanceTimeCommand(timedelta(minutes=1)))
    with pytest.raises(CommandError, match="unresolved parcels"):
        processor.execute(CompleteRouteCommand("ROUTE-02"))


def test_route_completion_derives_summary_and_releases_assignments() -> None:
    processor = CommandProcessor(make_state())
    result = processor.execute(CompleteRouteCommand("ROUTE-01"))
    completed = route(result.state, "ROUTE-01")
    driver = next(item for item in result.state.scenario.drivers if item.driver_id == "D-01")
    vehicle = next(item for item in result.state.scenario.vehicles if item.vehicle_id == "VAN-01")

    assert completed.status is RouteStatus.COMPLETED
    assert completed.completed_at == result.state.current_datetime
    assert completed.outcome_summary.planned_stop_count == 3
    assert completed.outcome_summary.completed_stop_count == 3
    assert completed.outcome_summary.parcel_count == 4
    assert completed.outcome_summary.delivered_to_home_count == 2
    assert completed.outcome_summary.delivered_to_locker_count == 2
    assert completed.historical_driver_id == "D-01"
    assert completed.driver_id is None
    assert driver.current_route_id is None
    assert vehicle.current_driver_id is None


def test_route_may_complete_with_a_recorded_failed_delivery() -> None:
    processor = CommandProcessor(make_state())
    processor.execute(ParcelTransitionCommand("P-1008-A", ParcelStatus.LOADED))
    processor.execute(StartRouteCommand("ROUTE-02"))
    processor.execute(ParcelTransitionCommand("P-1009-A", ParcelStatus.OUT_FOR_DELIVERY))
    processor.execute(ParcelTransitionCommand("P-1008-A", ParcelStatus.OUT_FOR_DELIVERY))
    processor.execute(ParcelTransitionCommand("P-1009-A", ParcelStatus.DELIVERY_FAILED))
    processor.execute(ParcelTransitionCommand("P-1008-A", ParcelStatus.DELIVERED_TO_LOCKER))
    processor.execute(AdvanceTimeCommand(timedelta(minutes=1)))
    result = processor.execute(CompleteRouteCommand("ROUTE-02"))
    summary = route(result.state, "ROUTE-02").outcome_summary

    assert summary.delivery_failed_count == 1
    assert summary.delivered_to_locker_count == 1
    assert summary.unresolved_count == 0


def test_driver_becomes_off_duty_when_route_finishes_after_shift() -> None:
    processor = CommandProcessor(make_state())
    processor.execute(AdvanceTimeCommand(timedelta(hours=8)))
    result = processor.execute(CompleteRouteCommand("ROUTE-01"))
    driver = next(item for item in result.state.scenario.drivers if item.driver_id == "D-01")

    assert driver.status.value == "OFF_DUTY"


def test_route_completion_requires_time_after_start() -> None:
    processor = CommandProcessor(make_state())
    processor.execute(StartRouteCommand("ROUTE-02"))
    with pytest.raises(CommandError, match="after its start"):
        processor.execute(CompleteRouteCommand("ROUTE-02"))
