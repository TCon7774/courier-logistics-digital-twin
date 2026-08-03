"""PowerShell-friendly local command-line controls for Milestone 2."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from courier_sim.domain.enums import InboundShipmentStatus, ParcelStatus, RouteStatus
from courier_sim.domain.transitions import TransitionError
from courier_sim.engine.clock import ClockError, format_datetime, parse_cli_datetime
from courier_sim.engine.commands import (
    AdvanceTimeCommand,
    AdvanceToCommand,
    AssignRouteCommand,
    CompleteRouteCommand,
    NextScheduledActionCommand,
    ParcelTransitionCommand,
    ShipmentTransitionCommand,
    StartRouteCommand,
)
from courier_sim.engine.models import EventType
from courier_sim.engine.processor import CommandError, CommandProcessor
from courier_sim.persistence.repository import PersistenceError, SimulationRepository

ENTITY_COLLECTIONS = {
    "parcel": ("parcels", "parcel_id"),
    "shipment": ("inbound_shipments", "shipment_id"),
    "route": ("routes", "route_id"),
    "driver": ("drivers", "driver_id"),
    "vehicle": ("vehicles", "vehicle_id"),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="courier-sim",
        description="Control the local Courier Logistics Digital Twin simulation.",
    )
    parser.add_argument(
        "--simulation-dir",
        type=Path,
        default=Path(os.environ.get("COURIER_SIM_DIR", ".simulation")),
        help=(
            "Persistence root (default: .simulation, or COURIER_SIM_DIR). "
            "Place this option before the command."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Initialize the first active simulation.")
    init.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Recorded deterministic seed; Milestone 2 currently uses fixed sample entities.",
    )

    subparsers.add_parser("status", help="Show an operational summary of active state.")
    subparsers.add_parser("time", help="Show the current simulation datetime.")

    advance = subparsers.add_parser("advance", help="Advance simulation time by a duration.")
    advance.add_argument("--minutes", type=int, default=0, help="Whole minutes to advance.")
    advance.add_argument("--hours", type=int, default=0, help="Whole hours to advance.")

    run_until = subparsers.add_parser(
        "run-until",
        help="Advance to a future ISO datetime and process due actions.",
    )
    run_until.add_argument(
        "--datetime",
        required=True,
        dest="target_datetime",
        help="Future ISO datetime; a missing offset means Europe/Bucharest.",
    )

    subparsers.add_parser(
        "next-event",
        help="Advance to and process the earliest scheduled action.",
    )

    events = subparsers.add_parser("events", help="Inspect append-only historical events.")
    events.add_argument("--limit", type=int, help="Show only the newest N matching events.")
    events.add_argument("--entity-id", help="Filter primary or related entity ID.")
    events.add_argument(
        "--event-type",
        choices=[event_type.value for event_type in EventType],
        help="Filter by event type.",
    )

    show = subparsers.add_parser("show", help="Show one current logistics entity.")
    show.add_argument("entity_type", choices=sorted(ENTITY_COLLECTIONS))
    show.add_argument("entity_id")

    parcel = subparsers.add_parser(
        "parcel-transition",
        help="Request one validated parcel lifecycle transition.",
    )
    parcel.add_argument("parcel_id")
    parcel.add_argument("status", choices=[status.value for status in ParcelStatus])

    shipment = subparsers.add_parser(
        "shipment-transition",
        help="Request one validated inbound-shipment transition.",
    )
    shipment.add_argument("shipment_id")
    shipment.add_argument(
        "status",
        choices=[status.value for status in InboundShipmentStatus],
    )

    assign = subparsers.add_parser(
        "assign-route",
        help="Assign an available driver and vehicle to a planned route.",
    )
    assign.add_argument("route_id")
    assign.add_argument("--driver", required=True, dest="driver_id")
    assign.add_argument("--vehicle", required=True, dest="vehicle_id")

    start = subparsers.add_parser("start-route", help="Start an assigned route.")
    start.add_argument("route_id")

    complete = subparsers.add_parser(
        "complete-route",
        help="Complete a route after all stops have recorded parcel outcomes.",
    )
    complete.add_argument("route_id")

    subparsers.add_parser(
        "validate",
        help="Validate snapshot, metadata, JSONL history, and relationships.",
    )

    reset = subparsers.add_parser(
        "reset",
        help="Archive the active run and safely initialize a new run.",
    )
    reset.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Recorded seed for the new run; Milestone 2 sample entities remain fixed.",
    )
    reset.add_argument(
        "--force",
        action="store_true",
        help="Required when an active run exists; confirms archive-and-reset.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repository = SimulationRepository(args.simulation_dir)
    try:
        _dispatch(args, repository)
    except (PersistenceError, CommandError, TransitionError, ClockError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


def _dispatch(args: argparse.Namespace, repository: SimulationRepository) -> None:
    if args.command == "init":
        loaded = repository.initialize(args.seed)
        print(f"Initialized {loaded.state.simulation_run_id} with seed {args.seed}.")
        print(f"Simulation time: {format_datetime(loaded.state.current_datetime)}")
        print(f"Files: {repository.active_directory.resolve()}")
        return
    if args.command == "reset":
        result = repository.reset(args.seed, force=args.force)
        if result.archived_run_id is not None:
            print(f"Archived run: {result.archived_run_id}")
            print(f"Archive directory: {result.archive_directory.resolve()}")
            print(f"Previous seed: {result.previous_seed}")
        else:
            print("No active run existed; no archive was created.")
        print(f"New run: {result.active.state.simulation_run_id}")
        print(f"New seed: {result.active.state.scenario_seed}")
        print(f"Initial simulation time: {format_datetime(result.active.state.current_datetime)}")
        return

    loaded = repository.load()
    if args.command == "status":
        _print_status(loaded)
    elif args.command == "time":
        print(format_datetime(loaded.state.current_datetime))
    elif args.command == "events":
        _print_events(loaded.events, args.limit, args.entity_id, args.event_type)
    elif args.command == "show":
        _show_entity(loaded.state.scenario, args.entity_type, args.entity_id)
    elif args.command == "validate":
        validated = repository.validate()
        print(
            f"Persistence valid: {validated.state.simulation_run_id}, "
            f"{len(validated.events)} events, "
            f"next ID EVT-{validated.state.next_event_sequence:06d}."
        )
    else:
        command = _build_state_command(args)
        pending_before = len(loaded.state.scheduled_actions)
        result = CommandProcessor(loaded.state).execute(command)
        if args.command == "next-event" and not result.events:
            print("No pending scheduled actions; state was not changed.")
            return
        saved = repository.commit(result)
        print(
            f"Applied {args.command}; simulation time is "
            f"{format_datetime(saved.state.current_datetime)}."
        )
        if args.command in {"advance", "run-until", "next-event"}:
            processed = pending_before - len(saved.state.scheduled_actions)
            print(f"Processed scheduled actions: {processed}")
        print(f"New events: {len(result.events)}")
        for event in result.events:
            print(f"  {event.event_id} {event.event_type}: {event.summary}")


def _build_state_command(args: argparse.Namespace):
    if args.command == "advance":
        return AdvanceTimeCommand(timedelta(hours=args.hours, minutes=args.minutes))
    if args.command == "run-until":
        return AdvanceToCommand(parse_cli_datetime(args.target_datetime))
    if args.command == "next-event":
        return NextScheduledActionCommand()
    if args.command == "parcel-transition":
        return ParcelTransitionCommand(args.parcel_id, ParcelStatus(args.status))
    if args.command == "shipment-transition":
        return ShipmentTransitionCommand(
            args.shipment_id,
            InboundShipmentStatus(args.status),
        )
    if args.command == "assign-route":
        return AssignRouteCommand(args.route_id, args.driver_id, args.vehicle_id)
    if args.command == "start-route":
        return StartRouteCommand(args.route_id)
    if args.command == "complete-route":
        return CompleteRouteCommand(args.route_id)
    raise ValueError(f"unsupported command: {args.command}")


def _print_status(loaded) -> None:
    state = loaded.state
    scenario = state.scenario
    print(f"Run: {state.simulation_run_id} (seed {state.scenario_seed})")
    print(f"Simulation time: {format_datetime(state.current_datetime)}")
    print("Entity counts:")
    entity_counts = {
        "warehouses": len(scenario.warehouses),
        "merchants": len(scenario.merchants),
        "shipments": len(scenario.inbound_shipments),
        "orders": len(scenario.orders),
        "parcels": len(scenario.parcels),
        "drivers": len(scenario.drivers),
        "vehicles": len(scenario.vehicles),
        "lockers": len(scenario.parcel_lockers),
        "routes": len(scenario.routes),
    }
    for entity_type, count in entity_counts.items():
        print(f"  {entity_type}: {count}")
    print(f"Pending scheduled actions: {len(state.scheduled_actions)}")
    for action in sorted(
        state.scheduled_actions,
        key=lambda item: (item.execute_at, item.creation_sequence),
    ):
        print(
            f"  {action.action_id} {format_datetime(action.execute_at)} "
            f"{action.action_type} {action.entity_id}"
        )
    active_routes = [
        route
        for route in scenario.routes
        if route.status in {RouteStatus.ASSIGNED, RouteStatus.IN_PROGRESS}
    ]
    print(f"Active routes: {len(active_routes)}")
    for route in active_routes:
        print(
            f"  {route.route_id} {route.status} driver={route.driver_id} vehicle={route.vehicle_id}"
        )
    print("Current assignments:")
    for driver in scenario.drivers:
        print(
            f"  driver {driver.driver_id}: route={driver.current_route_id or '-'} "
            f"vehicle={driver.current_vehicle_id or '-'}"
        )
    for vehicle in scenario.vehicles:
        print(
            f"  vehicle {vehicle.vehicle_id}: route={vehicle.current_route_id or '-'} "
            f"driver={vehicle.current_driver_id or '-'}"
        )
    print("Parcels by status:")
    for status, count in sorted(Counter(parcel.status for parcel in scenario.parcels).items()):
        print(f"  {status}: {count}")
    latest = loaded.events[-1].event_id if loaded.events else "none"
    print(f"Historical events: {len(loaded.events)} (latest {latest})")


def _print_events(
    events,
    limit: int | None,
    entity_id: str | None,
    event_type: str | None,
) -> None:
    if limit is not None and limit <= 0:
        raise ValueError("--limit must be greater than zero")
    selected = [
        event
        for event in events
        if (
            entity_id is None
            or event.primary_entity_id == entity_id
            or entity_id in event.related_entity_ids
        )
        and (event_type is None or event.event_type == event_type)
    ]
    if limit is not None:
        selected = selected[-limit:]
    if not selected:
        print("No matching historical events.")
        return
    for event in selected:
        print(
            f"{event.event_id} | {format_datetime(event.occurred_at)} | "
            f"{event.event_type} | {event.primary_entity_type} "
            f"{event.primary_entity_id} | {event.summary}"
        )


def _show_entity(scenario, entity_type: str, entity_id: str) -> None:
    collection_name, id_field = ENTITY_COLLECTIONS[entity_type]
    entity = next(
        (
            item
            for item in getattr(scenario, collection_name)
            if getattr(item, id_field) == entity_id
        ),
        None,
    )
    if entity is None:
        raise ValueError(f"{entity_type} {entity_id} was not found")
    payload = _readable_payload(entity.model_dump(mode="python"))
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _readable_payload(value: Any) -> Any:
    if isinstance(value, datetime):
        return format_datetime(value)
    if isinstance(value, dict):
        return {key: _readable_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_readable_payload(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
