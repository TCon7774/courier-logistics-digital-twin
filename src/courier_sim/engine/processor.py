"""Atomic command processing for all simulation state changes."""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from courier_sim.domain.enums import (
    DriverStatus,
    InboundShipmentStatus,
    ParcelStatus,
    RouteStatus,
    VehicleOperationalStatus,
)
from courier_sim.domain.models import (
    Driver,
    InboundShipment,
    LogisticsScenario,
    Parcel,
    Route,
    RouteOutcomeSummary,
    Vehicle,
)
from courier_sim.domain.transitions import (
    validate_parcel_transition,
    validate_route_transition,
    validate_shipment_transition,
)
from courier_sim.engine.clock import SimulationClock, as_bucharest_datetime, format_datetime
from courier_sim.engine.commands import (
    AdvanceTimeCommand,
    AdvanceToCommand,
    AssignRouteCommand,
    CompleteRouteCommand,
    InitializeSimulationCommand,
    NextScheduledActionCommand,
    ParcelTransitionCommand,
    ShipmentTransitionCommand,
    SimulationCommand,
    StartRouteCommand,
)
from courier_sim.engine.events import EventRecorder
from courier_sim.engine.models import (
    CommandResult,
    EntityType,
    EventType,
    ScheduledAction,
    ScheduledActionType,
    WorldState,
)


class CommandError(ValueError):
    """A normal user command could not be applied."""


class EntityNotFoundError(CommandError):
    """A requested entity ID does not exist."""


ROUTE_RESOLVED_STATUSES = frozenset(
    {
        ParcelStatus.DELIVERED_TO_HOME,
        ParcelStatus.DELIVERED_TO_LOCKER,
        ParcelStatus.COLLECTED_BY_CUSTOMER,
        ParcelStatus.DELIVERY_FAILED,
        ParcelStatus.RETURNED_TO_WAREHOUSE,
        ParcelStatus.DAMAGE_REVIEW,
        ParcelStatus.RETURNED_TO_SENDER,
        ParcelStatus.CANCELLED,
    }
)


class CommandProcessor:
    """Validate and atomically apply typed commands to an in-memory state."""

    def __init__(self, state: WorldState) -> None:
        self._state = state.model_copy(deep=True)

    @property
    def state(self) -> WorldState:
        return self._state.model_copy(deep=True)

    def execute(self, command: SimulationCommand) -> CommandResult:
        working = self._state.model_copy(deep=True)
        recorder = EventRecorder(working)

        if isinstance(command, InitializeSimulationCommand):
            self._initialize(working, recorder)
        elif isinstance(command, AdvanceTimeCommand):
            target = SimulationClock(working.current_datetime).advance_by(command.amount)
            self._advance_to(working, recorder, target, "advance")
        elif isinstance(command, AdvanceToCommand):
            target = SimulationClock(working.current_datetime).advance_to(command.target)
            self._advance_to(working, recorder, target, "run-until")
        elif isinstance(command, NextScheduledActionCommand):
            self._next_scheduled_action(working, recorder)
        elif isinstance(command, ParcelTransitionCommand):
            self._parcel_transition(
                working,
                recorder,
                command.parcel_id,
                command.status,
                "parcel-transition",
            )
        elif isinstance(command, ShipmentTransitionCommand):
            self._shipment_transition(
                working,
                recorder,
                command.shipment_id,
                command.status,
                "shipment-transition",
            )
        elif isinstance(command, AssignRouteCommand):
            self._assign_route(working, recorder, command)
        elif isinstance(command, StartRouteCommand):
            self._start_route(working, recorder, command.route_id)
        elif isinstance(command, CompleteRouteCommand):
            self._complete_route(working, recorder, command.route_id)
        else:
            raise TypeError(f"unsupported command type: {type(command).__name__}")

        validated = WorldState.model_validate(working.model_dump(mode="python"))
        self._state = validated
        return CommandResult(state=validated.model_copy(deep=True), events=recorder.events)

    @staticmethod
    def _initialize(state: WorldState, recorder: EventRecorder) -> None:
        if state.next_event_sequence != 1:
            raise CommandError("simulation initialization is valid only for a fresh state")
        recorder.record(
            event_type=EventType.SIMULATION_INITIALIZED,
            occurred_at=state.current_datetime,
            primary_entity_type=EntityType.SIMULATION,
            primary_entity_id=state.simulation_run_id,
            summary=(
                f"Simulation {state.simulation_run_id} initialized with seed {state.scenario_seed}"
            ),
            data={"seed": state.scenario_seed},
            originating_command="init",
        )

    def _advance_to(
        self,
        state: WorldState,
        recorder: EventRecorder,
        target: datetime,
        command_name: str,
    ) -> None:
        started_at = state.current_datetime
        target = as_bucharest_datetime(target)
        due_actions = sorted(
            (action for action in state.scheduled_actions if action.execute_at <= target),
            key=lambda action: (action.execute_at, action.creation_sequence, action.action_id),
        )
        for action in due_actions:
            state.current_datetime = as_bucharest_datetime(action.execute_at)
            self._process_scheduled_action(state, recorder, action)
            state.scheduled_actions = [
                pending
                for pending in state.scheduled_actions
                if pending.action_id != action.action_id
            ]
        state.current_datetime = target
        recorder.record(
            event_type=EventType.TIME_ADVANCED,
            occurred_at=target,
            primary_entity_type=EntityType.SIMULATION,
            primary_entity_id=state.simulation_run_id,
            summary=(
                f"Simulation time advanced from {format_datetime(started_at)} "
                f"to {format_datetime(target)}"
            ),
            data={
                "from": started_at.isoformat(),
                "to": target.isoformat(),
                "processed_action_ids": [action.action_id for action in due_actions],
            },
            originating_command=command_name,
        )

    def _next_scheduled_action(
        self,
        state: WorldState,
        recorder: EventRecorder,
    ) -> None:
        if not state.scheduled_actions:
            return
        action = min(
            state.scheduled_actions,
            key=lambda item: (item.execute_at, item.creation_sequence, item.action_id),
        )
        target = SimulationClock(state.current_datetime).advance_to(
            action.execute_at,
            allow_equal=True,
        )
        self._advance_to(state, recorder, target, "next-event")

    def _process_scheduled_action(
        self,
        state: WorldState,
        recorder: EventRecorder,
        action: ScheduledAction,
    ) -> None:
        if action.action_type is ScheduledActionType.SHIPMENT_ARRIVAL:
            self._shipment_transition(
                state,
                recorder,
                action.entity_id,
                InboundShipmentStatus.ARRIVED,
                "scheduled-shipment-arrival",
            )
            return
        raise CommandError(f"unsupported scheduled action type: {action.action_type}")

    @staticmethod
    def _parcel_transition(
        state: WorldState,
        recorder: EventRecorder,
        parcel_id: str,
        requested: ParcelStatus,
        command_name: str,
    ) -> None:
        parcel = _find(state.scenario.parcels, "parcel_id", parcel_id, "parcel")
        validate_parcel_transition(state.scenario, parcel, requested)
        previous = parcel.status
        data = parcel.model_dump(mode="python")
        data["status"] = requested
        if requested in {
            ParcelStatus.DELIVERED_TO_HOME,
            ParcelStatus.DELIVERED_TO_LOCKER,
        }:
            data["delivery_confirmation_sent"] = True
            data["delivery_confirmation_sent_at"] = state.current_datetime
        if requested is ParcelStatus.COLLECTED_BY_CUSTOMER:
            deposit_time = parcel.delivery_confirmation_sent_at
            if deposit_time is None or state.current_datetime < deposit_time:
                raise CommandError(
                    f"parcel {parcel_id}: collection time cannot precede locker deposit"
                )
            data["collected_at"] = state.current_datetime
        updated = Parcel.model_validate(data)
        _replace(state.scenario.parcels, "parcel_id", updated)
        recorder.record(
            event_type=EventType.PARCEL_STATUS_CHANGED,
            occurred_at=state.current_datetime,
            primary_entity_type=EntityType.PARCEL,
            primary_entity_id=parcel_id,
            summary=f"Parcel {parcel_id} changed from {previous} to {requested}",
            data={"previous_status": previous, "new_status": requested},
            originating_command=command_name,
        )

    @staticmethod
    def _shipment_transition(
        state: WorldState,
        recorder: EventRecorder,
        shipment_id: str,
        requested: InboundShipmentStatus,
        command_name: str,
    ) -> None:
        shipment = _find(
            state.scenario.inbound_shipments,
            "shipment_id",
            shipment_id,
            "shipment",
        )
        validate_shipment_transition(shipment_id, shipment.status, requested)
        previous = shipment.status
        data = shipment.model_dump(mode="python")
        data["status"] = requested
        consumed_action_ids: list[str] = []
        if requested is InboundShipmentStatus.ARRIVED:
            data["actual_arrival_at"] = state.current_datetime
        if requested in {
            InboundShipmentStatus.ARRIVED,
            InboundShipmentStatus.MISSING,
        }:
            # A terminal missing outcome makes a future arrival impossible just as a
            # manual early arrival makes the scheduled arrival redundant.
            consumed_action_ids = [
                action.action_id
                for action in state.scheduled_actions
                if action.action_type is ScheduledActionType.SHIPMENT_ARRIVAL
                and action.entity_id == shipment_id
            ]
            state.scheduled_actions = [
                action
                for action in state.scheduled_actions
                if action.action_id not in consumed_action_ids
            ]
        if requested is InboundShipmentStatus.RECEIVING and shipment.received_at is None:
            data["received_at"] = state.current_datetime
        updated = InboundShipment.model_validate(data)
        _replace(state.scenario.inbound_shipments, "shipment_id", updated)
        recorder.record(
            event_type=EventType.SHIPMENT_STATUS_CHANGED,
            occurred_at=state.current_datetime,
            primary_entity_type=EntityType.SHIPMENT,
            primary_entity_id=shipment_id,
            summary=f"Shipment {shipment_id} changed from {previous} to {requested}",
            data={
                "previous_status": previous,
                "new_status": requested,
                "consumed_scheduled_action_ids": consumed_action_ids,
            },
            originating_command=command_name,
        )

    @staticmethod
    def _assign_route(
        state: WorldState,
        recorder: EventRecorder,
        command: AssignRouteCommand,
    ) -> None:
        route = _find(state.scenario.routes, "route_id", command.route_id, "route")
        driver = _find(state.scenario.drivers, "driver_id", command.driver_id, "driver")
        vehicle = _find(state.scenario.vehicles, "vehicle_id", command.vehicle_id, "vehicle")
        validate_route_transition(route.route_id, route.status, RouteStatus.ASSIGNED)
        if route.driver_id is not None or route.vehicle_id is not None:
            raise CommandError(f"route {route.route_id} already has current assignments")
        if (
            driver.status is not DriverStatus.AVAILABLE
            or driver.current_route_id is not None
            or driver.current_vehicle_id is not None
        ):
            raise CommandError(f"driver {driver.driver_id} is not available for assignment")
        if not (driver.shift_start <= state.current_datetime < driver.shift_end):
            raise CommandError(
                f"driver {driver.driver_id} is outside the active shift at "
                f"{format_datetime(state.current_datetime)}"
            )
        if (
            vehicle.operational_status is not VehicleOperationalStatus.AVAILABLE
            or vehicle.current_route_id is not None
            or vehicle.current_driver_id is not None
        ):
            raise CommandError(f"vehicle {vehicle.vehicle_id} is not available for assignment")

        parcel_ids = [parcel_id for stop in route.stops for parcel_id in stop.parcel_ids]
        parcels = [
            _find(state.scenario.parcels, "parcel_id", parcel_id, "parcel")
            for parcel_id in parcel_ids
        ]
        parcel_weight = sum(parcel.weight_kg for parcel in parcels)
        if len(route.stops) > driver.maximum_stops or len(parcel_ids) > driver.maximum_parcels:
            raise CommandError(f"route {route.route_id} exceeds driver {driver.driver_id} workload")
        if (
            len(parcel_ids) > vehicle.parcel_count_capacity
            or parcel_weight > vehicle.weight_capacity_kg
        ):
            raise CommandError(
                f"route {route.route_id} exceeds vehicle {vehicle.vehicle_id} capacity"
            )

        route_data = route.model_dump(mode="python")
        route_data.update(
            {
                "status": RouteStatus.ASSIGNED,
                "driver_id": driver.driver_id,
                "vehicle_id": vehicle.vehicle_id,
                "historical_driver_id": driver.driver_id,
                "historical_vehicle_id": vehicle.vehicle_id,
            }
        )
        driver_data = driver.model_dump(mode="python")
        driver_data.update(
            {
                "status": DriverStatus.ASSIGNED,
                "current_vehicle_id": vehicle.vehicle_id,
                "current_route_id": route.route_id,
            }
        )
        vehicle_data = vehicle.model_dump(mode="python")
        vehicle_data.update(
            {
                "operational_status": VehicleOperationalStatus.ASSIGNED,
                "current_driver_id": driver.driver_id,
                "current_route_id": route.route_id,
            }
        )
        _replace(state.scenario.routes, "route_id", Route.model_validate(route_data))
        _replace(state.scenario.drivers, "driver_id", Driver.model_validate(driver_data))
        _replace(state.scenario.vehicles, "vehicle_id", Vehicle.model_validate(vehicle_data))
        recorder.record(
            event_type=EventType.ROUTE_ASSIGNED,
            occurred_at=state.current_datetime,
            primary_entity_type=EntityType.ROUTE,
            primary_entity_id=route.route_id,
            related_entity_ids=(driver.driver_id, vehicle.vehicle_id),
            summary=(
                f"Route {route.route_id} assigned to driver {driver.driver_id} "
                f"and vehicle {vehicle.vehicle_id}"
            ),
            data={"driver_id": driver.driver_id, "vehicle_id": vehicle.vehicle_id},
            originating_command="assign-route",
        )

    @staticmethod
    def _start_route(
        state: WorldState,
        recorder: EventRecorder,
        route_id: str,
    ) -> None:
        route = _find(state.scenario.routes, "route_id", route_id, "route")
        validate_route_transition(route.route_id, route.status, RouteStatus.IN_PROGRESS)
        if route.started_at is not None:
            raise CommandError(f"route {route_id} has already been started")
        if route.driver_id is None or route.vehicle_id is None:
            raise CommandError(f"route {route_id} requires driver and vehicle assignments")
        driver = _find(state.scenario.drivers, "driver_id", route.driver_id, "driver")
        vehicle = _find(state.scenario.vehicles, "vehicle_id", route.vehicle_id, "vehicle")
        if (
            driver.current_route_id != route_id
            or driver.current_vehicle_id != vehicle.vehicle_id
            or vehicle.current_route_id != route_id
            or vehicle.current_driver_id != driver.driver_id
        ):
            raise CommandError(f"route {route_id} assignments are inconsistent")
        if driver.status is not DriverStatus.ASSIGNED:
            raise CommandError(f"driver {driver.driver_id} is not in ASSIGNED status")
        if vehicle.operational_status is not VehicleOperationalStatus.ASSIGNED:
            raise CommandError(f"vehicle {vehicle.vehicle_id} is not in ASSIGNED status")
        if not (driver.shift_start <= state.current_datetime < driver.shift_end):
            raise CommandError(
                f"driver {driver.driver_id} cannot start route {route_id} outside the active "
                f"shift at {format_datetime(state.current_datetime)}"
            )

        route_data = route.model_dump(mode="python")
        route_data.update(
            {
                "status": RouteStatus.IN_PROGRESS,
                "started_at": state.current_datetime,
            }
        )
        vehicle_data = vehicle.model_dump(mode="python")
        vehicle_data["operational_status"] = VehicleOperationalStatus.IN_SERVICE
        _replace(state.scenario.routes, "route_id", Route.model_validate(route_data))
        _replace(state.scenario.vehicles, "vehicle_id", Vehicle.model_validate(vehicle_data))
        recorder.record(
            event_type=EventType.ROUTE_STARTED,
            occurred_at=state.current_datetime,
            primary_entity_type=EntityType.ROUTE,
            primary_entity_id=route_id,
            related_entity_ids=(driver.driver_id, vehicle.vehicle_id),
            summary=f"Route {route_id} started",
            data={"driver_id": driver.driver_id, "vehicle_id": vehicle.vehicle_id},
            originating_command="start-route",
        )

    @staticmethod
    def _complete_route(
        state: WorldState,
        recorder: EventRecorder,
        route_id: str,
    ) -> None:
        route = _find(state.scenario.routes, "route_id", route_id, "route")
        validate_route_transition(route.route_id, route.status, RouteStatus.COMPLETED)
        if route.started_at is None:
            raise CommandError(f"route {route_id} cannot complete before it starts")
        if state.current_datetime <= route.started_at:
            raise CommandError(f"route {route_id} completion must occur after its start time")
        if route.driver_id is None or route.vehicle_id is None:
            raise CommandError(f"route {route_id} has no active driver and vehicle")

        parcel_ids = [parcel_id for stop in route.stops for parcel_id in stop.parcel_ids]
        parcels = {
            parcel_id: _find(state.scenario.parcels, "parcel_id", parcel_id, "parcel")
            for parcel_id in parcel_ids
        }
        unresolved = [
            parcel_id
            for parcel_id, parcel in parcels.items()
            if parcel.status not in ROUTE_RESOLVED_STATUSES
        ]
        if unresolved:
            raise CommandError(
                f"route {route_id} has unresolved parcels: {', '.join(sorted(unresolved))}"
            )

        completed_stops = sum(
            all(
                parcels[parcel_id].status in ROUTE_RESOLVED_STATUSES
                for parcel_id in stop.parcel_ids
            )
            for stop in route.stops
        )
        status_counts = Counter(parcel.status for parcel in parcels.values())
        summary = RouteOutcomeSummary(
            planned_stop_count=len(route.stops),
            completed_stop_count=completed_stops,
            parcel_count=len(parcels),
            delivered_to_home_count=status_counts[ParcelStatus.DELIVERED_TO_HOME],
            delivered_to_locker_count=(
                status_counts[ParcelStatus.DELIVERED_TO_LOCKER]
                + status_counts[ParcelStatus.COLLECTED_BY_CUSTOMER]
            ),
            delivery_failed_count=status_counts[ParcelStatus.DELIVERY_FAILED],
            returned_to_warehouse_count=status_counts[ParcelStatus.RETURNED_TO_WAREHOUSE],
            damage_review_count=status_counts[ParcelStatus.DAMAGE_REVIEW],
            cancelled_count=status_counts[ParcelStatus.CANCELLED],
            returned_to_sender_count=status_counts[ParcelStatus.RETURNED_TO_SENDER],
            unresolved_count=0,
        )

        driver = _find(state.scenario.drivers, "driver_id", route.driver_id, "driver")
        vehicle = _find(state.scenario.vehicles, "vehicle_id", route.vehicle_id, "vehicle")
        route_data = route.model_dump(mode="python")
        route_data.update(
            {
                "status": RouteStatus.COMPLETED,
                "driver_id": None,
                "vehicle_id": None,
                "completed_at": state.current_datetime,
                "outcome_summary": summary,
            }
        )
        driver_data = driver.model_dump(mode="python")
        driver_data.update(
            {
                "status": (
                    DriverStatus.AVAILABLE
                    if driver.shift_start <= state.current_datetime < driver.shift_end
                    else DriverStatus.OFF_DUTY
                ),
                "current_vehicle_id": None,
                "current_route_id": None,
            }
        )
        vehicle_data = vehicle.model_dump(mode="python")
        vehicle_data.update(
            {
                "operational_status": VehicleOperationalStatus.AVAILABLE,
                "current_driver_id": None,
                "current_route_id": None,
            }
        )
        _replace(state.scenario.routes, "route_id", Route.model_validate(route_data))
        _replace(state.scenario.drivers, "driver_id", Driver.model_validate(driver_data))
        _replace(state.scenario.vehicles, "vehicle_id", Vehicle.model_validate(vehicle_data))
        recorder.record(
            event_type=EventType.ROUTE_COMPLETED,
            occurred_at=state.current_datetime,
            primary_entity_type=EntityType.ROUTE,
            primary_entity_id=route_id,
            related_entity_ids=(driver.driver_id, vehicle.vehicle_id, *parcel_ids),
            summary=(f"Route {route_id} completed with {summary.parcel_count} parcel outcomes"),
            data={"outcome_summary": summary.model_dump(mode="json")},
            originating_command="complete-route",
        )


def _find(items: list[object], id_field: str, entity_id: str, label: str):
    for item in items:
        if getattr(item, id_field) == entity_id:
            return item
    raise EntityNotFoundError(f"{label} {entity_id} was not found")


def _replace(items: list[object], id_field: str, updated: object) -> None:
    entity_id = getattr(updated, id_field)
    for index, item in enumerate(items):
        if getattr(item, id_field) == entity_id:
            items[index] = updated
            return
    raise EntityNotFoundError(f"entity {entity_id} was not found for replacement")


def validate_world_state(state: WorldState) -> LogisticsScenario:
    """Force cross-entity validation and return the validated scenario."""
    return LogisticsScenario.model_validate(state.scenario.model_dump(mode="python"))
