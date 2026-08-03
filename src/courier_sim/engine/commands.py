"""Typed commands accepted by the simulation command processor."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from courier_sim.domain.enums import InboundShipmentStatus, ParcelStatus


@dataclass(frozen=True)
class InitializeSimulationCommand:
    pass


@dataclass(frozen=True)
class AdvanceTimeCommand:
    amount: timedelta


@dataclass(frozen=True)
class AdvanceToCommand:
    target: datetime


@dataclass(frozen=True)
class NextScheduledActionCommand:
    pass


@dataclass(frozen=True)
class ParcelTransitionCommand:
    parcel_id: str
    status: ParcelStatus


@dataclass(frozen=True)
class ShipmentTransitionCommand:
    shipment_id: str
    status: InboundShipmentStatus


@dataclass(frozen=True)
class AssignRouteCommand:
    route_id: str
    driver_id: str
    vehicle_id: str


@dataclass(frozen=True)
class StartRouteCommand:
    route_id: str


@dataclass(frozen=True)
class CompleteRouteCommand:
    route_id: str


SimulationCommand = (
    InitializeSimulationCommand
    | AdvanceTimeCommand
    | AdvanceToCommand
    | NextScheduledActionCommand
    | ParcelTransitionCommand
    | ShipmentTransitionCommand
    | AssignRouteCommand
    | StartRouteCommand
    | CompleteRouteCommand
)
