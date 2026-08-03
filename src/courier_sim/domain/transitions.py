"""Central transition maps and conditional logistics validation."""

from collections.abc import Collection

from courier_sim.domain.enums import (
    DeliveryMethod,
    InboundShipmentStatus,
    ParcelStatus,
    RouteStatus,
)
from courier_sim.domain.models import LogisticsScenario, Parcel


class TransitionError(ValueError):
    """A requested state transition is not legal."""


PARCEL_TRANSITIONS: dict[ParcelStatus, frozenset[ParcelStatus]] = {
    ParcelStatus.EXPECTED: frozenset({ParcelStatus.RECEIVED, ParcelStatus.CANCELLED}),
    ParcelStatus.RECEIVED: frozenset(
        {ParcelStatus.SCANNED, ParcelStatus.DAMAGE_REVIEW, ParcelStatus.CANCELLED}
    ),
    ParcelStatus.SCANNED: frozenset(
        {ParcelStatus.SORTED, ParcelStatus.DAMAGE_REVIEW, ParcelStatus.CANCELLED}
    ),
    ParcelStatus.SORTED: frozenset(
        {
            ParcelStatus.STAGED_FOR_ROUTE,
            ParcelStatus.DAMAGE_REVIEW,
            ParcelStatus.CANCELLED,
        }
    ),
    ParcelStatus.STAGED_FOR_ROUTE: frozenset(
        {ParcelStatus.LOADED, ParcelStatus.DAMAGE_REVIEW, ParcelStatus.CANCELLED}
    ),
    ParcelStatus.LOADED: frozenset(
        {ParcelStatus.OUT_FOR_DELIVERY, ParcelStatus.DAMAGE_REVIEW, ParcelStatus.CANCELLED}
    ),
    ParcelStatus.OUT_FOR_DELIVERY: frozenset(
        {
            ParcelStatus.DELIVERED_TO_HOME,
            ParcelStatus.DELIVERED_TO_LOCKER,
            ParcelStatus.DELIVERY_FAILED,
        }
    ),
    ParcelStatus.DELIVERED_TO_HOME: frozenset(),
    ParcelStatus.DELIVERED_TO_LOCKER: frozenset({ParcelStatus.COLLECTED_BY_CUSTOMER}),
    ParcelStatus.COLLECTED_BY_CUSTOMER: frozenset(),
    ParcelStatus.DELIVERY_FAILED: frozenset({ParcelStatus.RETURNED_TO_WAREHOUSE}),
    ParcelStatus.RETURNED_TO_WAREHOUSE: frozenset(
        {
            ParcelStatus.STAGED_FOR_ROUTE,
            ParcelStatus.DAMAGE_REVIEW,
            ParcelStatus.RETURNED_TO_SENDER,
            ParcelStatus.CANCELLED,
        }
    ),
    ParcelStatus.DAMAGE_REVIEW: frozenset(
        {
            ParcelStatus.RETURNED_TO_WAREHOUSE,
            ParcelStatus.RETURNED_TO_SENDER,
            ParcelStatus.CANCELLED,
        }
    ),
    ParcelStatus.RETURNED_TO_SENDER: frozenset(),
    ParcelStatus.CANCELLED: frozenset(),
}


SHIPMENT_TRANSITIONS: dict[InboundShipmentStatus, frozenset[InboundShipmentStatus]] = {
    InboundShipmentStatus.SCHEDULED: frozenset(
        {
            InboundShipmentStatus.IN_TRANSIT,
            InboundShipmentStatus.DELAYED,
            InboundShipmentStatus.MISSING,
        }
    ),
    InboundShipmentStatus.IN_TRANSIT: frozenset(
        {
            InboundShipmentStatus.ARRIVED,
            InboundShipmentStatus.DELAYED,
            InboundShipmentStatus.MISSING,
        }
    ),
    InboundShipmentStatus.DELAYED: frozenset(
        {
            InboundShipmentStatus.IN_TRANSIT,
            InboundShipmentStatus.ARRIVED,
            InboundShipmentStatus.MISSING,
        }
    ),
    InboundShipmentStatus.ARRIVED: frozenset({InboundShipmentStatus.RECEIVING}),
    InboundShipmentStatus.RECEIVING: frozenset(
        {
            InboundShipmentStatus.PROCESSED,
            InboundShipmentStatus.PARTIALLY_RECEIVED,
        }
    ),
    InboundShipmentStatus.PARTIALLY_RECEIVED: frozenset(
        {
            InboundShipmentStatus.RECEIVING,
            InboundShipmentStatus.PROCESSED,
        }
    ),
    InboundShipmentStatus.PROCESSED: frozenset(),
    InboundShipmentStatus.MISSING: frozenset(),
}


ROUTE_TRANSITIONS: dict[RouteStatus, frozenset[RouteStatus]] = {
    RouteStatus.PLANNED: frozenset({RouteStatus.ASSIGNED, RouteStatus.CANCELLED}),
    RouteStatus.ASSIGNED: frozenset({RouteStatus.IN_PROGRESS, RouteStatus.CANCELLED}),
    RouteStatus.IN_PROGRESS: frozenset({RouteStatus.COMPLETED, RouteStatus.CANCELLED}),
    RouteStatus.COMPLETED: frozenset(),
    RouteStatus.CANCELLED: frozenset(),
}


def validate_transition(
    *,
    entity_kind: str,
    entity_id: str,
    current: object,
    requested: object,
    transition_map: dict[object, Collection[object]],
) -> None:
    """Reject an illegal map-level transition with actionable details."""
    allowed = transition_map.get(current, ())
    if requested in allowed:
        return
    allowed_text = ", ".join(sorted(str(item) for item in allowed)) or "none"
    raise TransitionError(
        f"{entity_kind} {entity_id}: cannot transition from {current} to {requested}; "
        f"allowed next states: {allowed_text}"
    )


def validate_parcel_transition(
    scenario: LogisticsScenario,
    parcel: Parcel,
    requested: ParcelStatus,
) -> None:
    """Apply map-level and parcel-specific transition rules."""
    validate_transition(
        entity_kind="parcel",
        entity_id=parcel.parcel_id,
        current=parcel.status,
        requested=requested,
        transition_map=PARCEL_TRANSITIONS,
    )
    if requested is ParcelStatus.DELIVERED_TO_HOME:
        if parcel.delivery_method is not DeliveryMethod.HOME:
            raise TransitionError(
                f"parcel {parcel.parcel_id}: DELIVERED_TO_HOME requires HOME delivery"
            )
    if requested is ParcelStatus.DELIVERED_TO_LOCKER:
        if parcel.delivery_method is not DeliveryMethod.PARCEL_LOCKER:
            raise TransitionError(
                f"parcel {parcel.parcel_id}: DELIVERED_TO_LOCKER requires PARCEL_LOCKER delivery"
            )
    if requested is ParcelStatus.COLLECTED_BY_CUSTOMER:
        if parcel.delivery_method is not DeliveryMethod.PARCEL_LOCKER:
            raise TransitionError(
                f"parcel {parcel.parcel_id}: customer collection requires locker delivery"
            )
        if parcel.status is not ParcelStatus.DELIVERED_TO_LOCKER:
            raise TransitionError(
                f"parcel {parcel.parcel_id}: customer collection requires DELIVERED_TO_LOCKER first"
            )
    if requested in {ParcelStatus.LOADED, ParcelStatus.OUT_FOR_DELIVERY}:
        route = next(
            (
                route
                for route in scenario.routes
                if any(parcel.parcel_id in stop.parcel_ids for stop in route.stops)
                and route.status in {RouteStatus.ASSIGNED, RouteStatus.IN_PROGRESS}
            ),
            None,
        )
        if route is None or route.driver_id is None or route.vehicle_id is None:
            raise TransitionError(
                f"parcel {parcel.parcel_id}: {requested} requires an assigned active route"
            )
        if (
            requested is ParcelStatus.OUT_FOR_DELIVERY
            and route.status is not RouteStatus.IN_PROGRESS
        ):
            raise TransitionError(
                f"parcel {parcel.parcel_id}: OUT_FOR_DELIVERY requires its route "
                f"{route.route_id} to be IN_PROGRESS"
            )


def validate_shipment_transition(
    shipment_id: str,
    current: InboundShipmentStatus,
    requested: InboundShipmentStatus,
) -> None:
    validate_transition(
        entity_kind="shipment",
        entity_id=shipment_id,
        current=current,
        requested=requested,
        transition_map=SHIPMENT_TRANSITIONS,
    )


def validate_route_transition(
    route_id: str,
    current: RouteStatus,
    requested: RouteStatus,
) -> None:
    validate_transition(
        entity_kind="route",
        entity_id=route_id,
        current=current,
        requested=requested,
        transition_map=ROUTE_TRANSITIONS,
    )
