"""Pydantic models and validation for the foundational logistics domain."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from courier_sim.domain.enums import (
    CommunicationChannel,
    DeliveryGroupingPolicy,
    DeliveryMethod,
    DriverStatus,
    FailureType,
    InboundShipmentStatus,
    NotificationDeliveryStatus,
    ParcelStatus,
    RouteStatus,
    VehicleOperationalStatus,
    VehicleType,
)

EntityId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
AwareDateTime = Annotated[datetime, AwareDatetime]
PositiveInt = Annotated[int, Field(gt=0)]
PositiveFloat = Annotated[float, Field(gt=0)]


class DomainModel(BaseModel):
    """Shared strict configuration for all domain values and entities."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class GeographicCoordinates(DomainModel):
    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]


class HomeDestination(DomainModel):
    home_destination_id: EntityId
    customer_id: EntityId
    label: EntityId
    address_line: EntityId
    city: EntityId = "Bucharest"
    coordinates: GeographicCoordinates


class ParcelLocker(DomainModel):
    parcel_locker_id: EntityId
    name: EntityId
    address_line: EntityId
    city: EntityId = "Bucharest"
    coordinates: GeographicCoordinates
    parcel_capacity: PositiveInt
    active: bool = True


class Warehouse(DomainModel):
    warehouse_id: EntityId
    name: EntityId
    address_line: EntityId
    city: EntityId = "Bucharest"
    coordinates: GeographicCoordinates


class Merchant(DomainModel):
    merchant_id: EntityId
    name: EntityId
    origin_description: EntityId
    created_at: AwareDateTime


class Customer(DomainModel):
    customer_id: EntityId
    display_name: EntityId
    created_at: AwareDateTime


class CustomerOrder(DomainModel):
    order_id: EntityId
    merchant_id: EntityId
    customer_id: EntityId
    parcel_ids: Annotated[list[EntityId], Field(min_length=1)]
    delivery_group_id: EntityId
    delivery_grouping_policy: DeliveryGroupingPolicy
    created_at: AwareDateTime

    @model_validator(mode="after")
    def parcel_ids_are_unique(self) -> Self:
        if len(self.parcel_ids) != len(set(self.parcel_ids)):
            raise ValueError("an order cannot list the same parcel ID more than once")
        return self


class Parcel(DomainModel):
    parcel_id: EntityId
    order_id: EntityId
    merchant_id: EntityId
    delivery_group_id: EntityId
    delivery_grouping_policy: DeliveryGroupingPolicy
    delivery_method: DeliveryMethod
    home_destination_id: EntityId | None = None
    parcel_locker_id: EntityId | None = None
    status: ParcelStatus
    weight_kg: PositiveFloat
    delivery_due_at: AwareDateTime
    customer_window_start: AwareDateTime | None = None
    customer_window_end: AwareDateTime | None = None
    estimated_arrival_start: AwareDateTime | None = None
    estimated_arrival_end: AwareDateTime | None = None
    internal_target_at: AwareDateTime | None = None
    delivery_confirmation_sent: bool = False
    delivery_confirmation_sent_at: AwareDateTime | None = None
    collected_at: AwareDateTime | None = None

    @model_validator(mode="after")
    def validate_delivery_details(self) -> Self:
        if self.delivery_method is DeliveryMethod.HOME:
            if self.home_destination_id is None or self.parcel_locker_id is not None:
                raise ValueError("home delivery must reference only a home destination")
            if self.status in {
                ParcelStatus.DELIVERED_TO_LOCKER,
                ParcelStatus.COLLECTED_BY_CUSTOMER,
            }:
                raise ValueError("locker completion states require locker delivery")
        else:
            if self.parcel_locker_id is None or self.home_destination_id is not None:
                raise ValueError("locker delivery must reference only a parcel locker")
            if self.status is ParcelStatus.DELIVERED_TO_HOME:
                raise ValueError("DELIVERED_TO_HOME requires home delivery")

        self._validate_window(
            self.customer_window_start,
            self.customer_window_end,
            "customer window",
        )
        self._validate_window(
            self.estimated_arrival_start,
            self.estimated_arrival_end,
            "estimated-arrival window",
        )

        completed_statuses = {
            ParcelStatus.DELIVERED_TO_HOME,
            ParcelStatus.DELIVERED_TO_LOCKER,
            ParcelStatus.COLLECTED_BY_CUSTOMER,
        }
        if self.status in completed_statuses and not self.delivery_confirmation_sent:
            raise ValueError("completed delivery requires a sent confirmation")

        if self.delivery_confirmation_sent and self.delivery_confirmation_sent_at is None:
            raise ValueError("confirmation time is required when confirmation was sent")
        if not self.delivery_confirmation_sent and self.delivery_confirmation_sent_at is not None:
            raise ValueError("confirmation time must be absent when confirmation was not sent")
        if self.status is ParcelStatus.COLLECTED_BY_CUSTOMER:
            if self.collected_at is None:
                raise ValueError("locker collection requires a collection time")
            if self.delivery_confirmation_sent_at is None:
                raise ValueError("locker collection requires a locker-deposit time")
            if self.collected_at < self.delivery_confirmation_sent_at:
                raise ValueError("collection time cannot precede locker-deposit time")
        elif self.collected_at is not None:
            raise ValueError("collection time is valid only after customer collection")
        return self

    @staticmethod
    def _validate_window(
        start: datetime | None,
        end: datetime | None,
        label: str,
    ) -> None:
        if (start is None) != (end is None):
            raise ValueError(f"{label} start and end must both be present or both be absent")
        if start is not None and end is not None and start >= end:
            raise ValueError(f"{label} start must occur before its end")


class InboundShipment(DomainModel):
    shipment_id: EntityId
    merchant_id: EntityId
    origin: EntityId
    expected_arrival_at: AwareDateTime
    actual_arrival_at: AwareDateTime | None = None
    parcel_ids: Annotated[list[EntityId], Field(min_length=1)]
    parcel_count: PositiveInt
    status: InboundShipmentStatus
    created_at: AwareDateTime
    received_at: AwareDateTime | None = None

    @model_validator(mode="after")
    def parcel_count_matches_ids(self) -> Self:
        if len(self.parcel_ids) != len(set(self.parcel_ids)):
            raise ValueError("an inbound shipment cannot list a parcel more than once")
        if self.parcel_count != len(self.parcel_ids):
            raise ValueError("parcel_count must match the number of parcel IDs")
        return self


class Driver(DomainModel):
    driver_id: EntityId
    display_name: EntityId
    shift_start: AwareDateTime
    shift_end: AwareDateTime
    required_break_minutes: PositiveInt
    maximum_parcels: PositiveInt
    maximum_stops: PositiveInt
    status: DriverStatus
    current_vehicle_id: EntityId | None = None
    current_route_id: EntityId | None = None

    @model_validator(mode="after")
    def shift_is_ordered(self) -> Self:
        if self.shift_start >= self.shift_end:
            raise ValueError("shift start must occur before shift end")
        return self


class Vehicle(DomainModel):
    vehicle_id: EntityId
    vehicle_type: VehicleType
    weight_capacity_kg: PositiveFloat
    parcel_count_capacity: PositiveInt
    operational_status: VehicleOperationalStatus
    current_driver_id: EntityId | None = None
    current_route_id: EntityId | None = None


class RouteStop(DomainModel):
    route_stop_id: EntityId
    sequence: PositiveInt
    parcel_ids: Annotated[list[EntityId], Field(min_length=1)]
    home_destination_id: EntityId | None = None
    parcel_locker_id: EntityId | None = None
    estimated_arrival_start: AwareDateTime | None = None
    estimated_arrival_end: AwareDateTime | None = None

    @model_validator(mode="after")
    def validate_stop(self) -> Self:
        if (self.home_destination_id is None) == (self.parcel_locker_id is None):
            raise ValueError("a route stop must reference exactly one destination")
        if len(self.parcel_ids) != len(set(self.parcel_ids)):
            raise ValueError("a route stop cannot list a parcel more than once")
        Parcel._validate_window(
            self.estimated_arrival_start,
            self.estimated_arrival_end,
            "route-stop estimated-arrival window",
        )
        return self


class RouteOutcomeSummary(DomainModel):
    """Derived parcel and stop outcomes retained with a completed route."""

    planned_stop_count: Annotated[int, Field(ge=0)]
    completed_stop_count: Annotated[int, Field(ge=0)]
    parcel_count: Annotated[int, Field(ge=0)]
    delivered_to_home_count: Annotated[int, Field(ge=0)]
    delivered_to_locker_count: Annotated[int, Field(ge=0)]
    delivery_failed_count: Annotated[int, Field(ge=0)]
    returned_to_warehouse_count: Annotated[int, Field(ge=0)]
    damage_review_count: Annotated[int, Field(ge=0)]
    cancelled_count: Annotated[int, Field(ge=0)]
    returned_to_sender_count: Annotated[int, Field(ge=0)] = 0
    unresolved_count: Annotated[int, Field(ge=0)]


class Route(DomainModel):
    route_id: EntityId
    warehouse_id: EntityId
    status: RouteStatus
    stops: list[RouteStop]
    driver_id: EntityId | None = None
    vehicle_id: EntityId | None = None
    historical_driver_id: EntityId | None = None
    historical_vehicle_id: EntityId | None = None
    started_at: AwareDateTime | None = None
    completed_at: AwareDateTime | None = None
    outcome_summary: RouteOutcomeSummary | None = None

    @model_validator(mode="after")
    def stop_identifiers_are_unique(self) -> Self:
        stop_ids = [stop.route_stop_id for stop in self.stops]
        if len(stop_ids) != len(set(stop_ids)):
            raise ValueError("route stop IDs must be unique within a route")
        sequences = [stop.sequence for stop in self.stops]
        if len(sequences) != len(set(sequences)):
            raise ValueError("route stop sequences must be unique within a route")
        parcel_ids = [parcel_id for stop in self.stops for parcel_id in stop.parcel_ids]
        if len(parcel_ids) != len(set(parcel_ids)):
            raise ValueError("a parcel cannot appear at multiple stops on one route")
        if (self.historical_driver_id is None) != (self.historical_vehicle_id is None):
            raise ValueError("historical route assignments must include both driver and vehicle")
        if self.status is RouteStatus.IN_PROGRESS and self.started_at is None:
            raise ValueError("an in-progress route requires started_at")
        if self.status is RouteStatus.COMPLETED:
            if self.started_at is None or self.completed_at is None:
                raise ValueError("a completed route requires start and completion times")
            if self.completed_at <= self.started_at:
                raise ValueError("route completion time must be after its start time")
            if self.outcome_summary is None:
                raise ValueError("a completed route requires an outcome summary")
            if self.driver_id is not None or self.vehicle_id is not None:
                raise ValueError("a completed route cannot retain current assignments")
            if self.historical_driver_id is None:
                raise ValueError("a completed route must retain historical assignments")
        elif self.completed_at is not None or self.outcome_summary is not None:
            raise ValueError("only a completed route may have completion data")
        return self


class CustomerNotification(DomainModel):
    notification_id: EntityId
    order_id: EntityId
    parcel_id: EntityId
    failure_type: FailureType
    message: EntityId
    communication_channel: CommunicationChannel
    created_at: AwareDateTime
    sent_at: AwareDateTime | None = None
    delivery_status: NotificationDeliveryStatus
    response_required: bool = False
    customer_response: str | None = None
    response_deadline: AwareDateTime | None = None


class LogisticsScenario(DomainModel):
    """Complete logistics world shared by the static sample and simulation."""

    scenario_id: EntityId
    timezone: EntityId = "Europe/Bucharest"
    warehouses: list[Warehouse]
    merchants: list[Merchant]
    customers: list[Customer]
    home_destinations: list[HomeDestination]
    parcel_lockers: list[ParcelLocker]
    orders: list[CustomerOrder]
    parcels: list[Parcel]
    inbound_shipments: list[InboundShipment]
    drivers: list[Driver]
    vehicles: list[Vehicle]
    routes: list[Route]
    customer_notifications: list[CustomerNotification]

    @model_validator(mode="after")
    def validate_world_relationships(self) -> Self:
        if len(self.warehouses) != 1:
            raise ValueError("Milestone 1 scenarios must contain exactly one warehouse")

        warehouses = self._unique_index(self.warehouses, "warehouse_id", "warehouse")
        merchants = self._unique_index(self.merchants, "merchant_id", "merchant")
        customers = self._unique_index(self.customers, "customer_id", "customer")
        homes = self._unique_index(
            self.home_destinations,
            "home_destination_id",
            "home destination",
        )
        lockers = self._unique_index(
            self.parcel_lockers,
            "parcel_locker_id",
            "parcel locker",
        )
        orders = self._unique_index(self.orders, "order_id", "order")
        parcels = self._unique_index(self.parcels, "parcel_id", "parcel")
        self._unique_index(self.inbound_shipments, "shipment_id", "inbound shipment")
        drivers = self._unique_index(self.drivers, "driver_id", "driver")
        vehicles = self._unique_index(self.vehicles, "vehicle_id", "vehicle")
        routes = self._unique_index(self.routes, "route_id", "route")
        self._unique_index(
            self.customer_notifications,
            "notification_id",
            "customer notification",
        )

        for home in self.home_destinations:
            self._require(home.customer_id, customers, "home destination customer")

        for order in self.orders:
            self._require(order.merchant_id, merchants, "order merchant")
            self._require(order.customer_id, customers, "order customer")
            pointed_back = {
                parcel.parcel_id for parcel in self.parcels if parcel.order_id == order.order_id
            }
            if set(order.parcel_ids) != pointed_back:
                raise ValueError(
                    f"order {order.order_id} parcel IDs must exactly match parcel back-references"
                )

        for parcel in self.parcels:
            order = self._require(parcel.order_id, orders, "parcel order")
            self._require(parcel.merchant_id, merchants, "parcel merchant")
            if parcel.merchant_id != order.merchant_id:
                raise ValueError(f"parcel {parcel.parcel_id} merchant must match its order")
            if parcel.parcel_id not in order.parcel_ids:
                raise ValueError(f"parcel {parcel.parcel_id} is absent from its order")
            if (
                parcel.delivery_group_id != order.delivery_group_id
                or parcel.delivery_grouping_policy != order.delivery_grouping_policy
            ):
                raise ValueError(f"parcel {parcel.parcel_id} delivery group must match its order")
            if parcel.delivery_method is DeliveryMethod.HOME:
                home = self._require(
                    parcel.home_destination_id,
                    homes,
                    "parcel home destination",
                )
                if home.customer_id != order.customer_id:
                    raise ValueError(
                        f"parcel {parcel.parcel_id} home destination must belong "
                        "to its order customer"
                    )
            else:
                self._require(
                    parcel.parcel_locker_id,
                    lockers,
                    "parcel locker destination",
                )

        parcel_to_shipment: dict[str, str] = {}
        for shipment in self.inbound_shipments:
            self._require(shipment.merchant_id, merchants, "shipment merchant")
            for parcel_id in shipment.parcel_ids:
                parcel = self._require(parcel_id, parcels, "shipment parcel")
                previous_shipment = parcel_to_shipment.get(parcel_id)
                if previous_shipment is not None:
                    raise ValueError(
                        f"parcel {parcel_id} appears in shipments "
                        f"{previous_shipment} and {shipment.shipment_id}"
                    )
                parcel_to_shipment[parcel_id] = shipment.shipment_id
                if parcel.merchant_id != shipment.merchant_id:
                    raise ValueError(f"parcel {parcel_id} merchant must match its inbound shipment")

        for driver in self.drivers:
            if (driver.current_vehicle_id is None) != (driver.current_route_id is None):
                raise ValueError(
                    f"driver {driver.driver_id} must have both current assignments, or neither"
                )
            has_current_assignment = driver.current_route_id is not None
            if has_current_assignment and driver.status is not DriverStatus.ASSIGNED:
                raise ValueError(
                    f"driver {driver.driver_id} with a current assignment must be ASSIGNED"
                )
            if not has_current_assignment and driver.status is DriverStatus.ASSIGNED:
                raise ValueError(
                    f"driver {driver.driver_id} cannot be ASSIGNED without current links"
                )
            if driver.current_vehicle_id is not None:
                vehicle = self._require(
                    driver.current_vehicle_id,
                    vehicles,
                    "driver vehicle",
                )
                if vehicle.current_driver_id != driver.driver_id:
                    raise ValueError(
                        f"driver {driver.driver_id} and vehicle "
                        f"{vehicle.vehicle_id} assignments disagree"
                    )
            if driver.current_route_id is not None:
                route = self._require(driver.current_route_id, routes, "driver route")
                if route.driver_id != driver.driver_id:
                    raise ValueError(
                        f"driver {driver.driver_id} and route {route.route_id} assignments disagree"
                    )

        for vehicle in self.vehicles:
            if (vehicle.current_driver_id is None) != (vehicle.current_route_id is None):
                raise ValueError(
                    f"vehicle {vehicle.vehicle_id} must have both current assignments, or neither"
                )
            has_current_assignment = vehicle.current_route_id is not None
            if not has_current_assignment and vehicle.operational_status in {
                VehicleOperationalStatus.ASSIGNED,
                VehicleOperationalStatus.IN_SERVICE,
            }:
                raise ValueError(
                    f"vehicle {vehicle.vehicle_id} cannot be {vehicle.operational_status} "
                    "without current links"
                )
            if vehicle.current_driver_id is not None:
                driver = self._require(
                    vehicle.current_driver_id,
                    drivers,
                    "vehicle driver",
                )
                if driver.current_vehicle_id != vehicle.vehicle_id:
                    raise ValueError(
                        f"vehicle {vehicle.vehicle_id} and driver "
                        f"{driver.driver_id} assignments disagree"
                    )
            if vehicle.current_route_id is not None:
                route = self._require(vehicle.current_route_id, routes, "vehicle route")
                if route.vehicle_id != vehicle.vehicle_id:
                    raise ValueError(
                        f"vehicle {vehicle.vehicle_id} and route "
                        f"{route.route_id} assignments disagree"
                    )
                expected_status = {
                    RouteStatus.ASSIGNED: VehicleOperationalStatus.ASSIGNED,
                    RouteStatus.IN_PROGRESS: VehicleOperationalStatus.IN_SERVICE,
                }.get(route.status)
                if expected_status is None:
                    raise ValueError(
                        f"vehicle {vehicle.vehicle_id} cannot link to route {route.route_id} "
                        f"in {route.status}"
                    )
                if vehicle.operational_status is not expected_status:
                    raise ValueError(
                        f"vehicle {vehicle.vehicle_id} must be {expected_status} while route "
                        f"{route.route_id} is {route.status}"
                    )

        route_stop_to_route: dict[str, str] = {}

        active_route_statuses = {
            RouteStatus.PLANNED,
            RouteStatus.ASSIGNED,
            RouteStatus.IN_PROGRESS,
        }
        active_parcel_to_route: dict[str, str] = {}

        for route in self.routes:
            self._require(route.warehouse_id, warehouses, "route warehouse")
            if (route.driver_id is None) != (route.vehicle_id is None):
                raise ValueError(
                    f"route {route.route_id} must assign both a driver and vehicle, or neither"
                )
            if route.status in {RouteStatus.ASSIGNED, RouteStatus.IN_PROGRESS}:
                if route.driver_id is None or route.vehicle_id is None:
                    raise ValueError(
                        f"active route {route.route_id} requires current driver and vehicle links"
                    )
            elif route.driver_id is not None or route.vehicle_id is not None:
                raise ValueError(
                    f"route {route.route_id} in {route.status} cannot retain current assignments"
                )
            if route.driver_id is not None and route.vehicle_id is not None:
                driver = self._require(route.driver_id, drivers, "route driver")
                vehicle = self._require(route.vehicle_id, vehicles, "route vehicle")
                if (
                    driver.current_route_id != route.route_id
                    or vehicle.current_route_id != route.route_id
                    or driver.current_vehicle_id != vehicle.vehicle_id
                    or vehicle.current_driver_id != driver.driver_id
                ):
                    raise ValueError(
                        f"route {route.route_id}, driver, and vehicle assignments disagree"
                    )
            if route.historical_driver_id is not None:
                self._require(
                    route.historical_driver_id,
                    drivers,
                    "historical route driver",
                )
                self._require(
                    route.historical_vehicle_id,
                    vehicles,
                    "historical route vehicle",
                )
            if route.status in {RouteStatus.ASSIGNED, RouteStatus.IN_PROGRESS}:
                if (
                    route.driver_id != route.historical_driver_id
                    or route.vehicle_id != route.historical_vehicle_id
                ):
                    raise ValueError(
                        f"active route {route.route_id} current and historical assignments disagree"
                    )
            for stop in route.stops:
                previous_route = route_stop_to_route.get(stop.route_stop_id)
                if previous_route is not None:
                    raise ValueError(
                        f"duplicate route stop ID {stop.route_stop_id} "
                        f"in routes {previous_route} and {route.route_id}"
                    )
                route_stop_to_route[stop.route_stop_id] = route.route_id
                if stop.home_destination_id is not None:
                    self._require(
                        stop.home_destination_id,
                        homes,
                        "route-stop home destination",
                    )
                else:
                    self._require(
                        stop.parcel_locker_id,
                        lockers,
                        "route-stop locker destination",
                    )
                for parcel_id in stop.parcel_ids:
                    parcel = self._require(parcel_id, parcels, "route-stop parcel")
                    if (
                        parcel.home_destination_id != stop.home_destination_id
                        or parcel.parcel_locker_id != stop.parcel_locker_id
                    ):
                        raise ValueError(
                            f"route-stop destination does not match parcel {parcel_id}"
                        )
                    if route.status in active_route_statuses:
                        previous_route = active_parcel_to_route.get(parcel_id)
                        if previous_route is not None:
                            raise ValueError(
                                f"parcel {parcel_id} appears on active routes "
                                f"{previous_route} and {route.route_id}"
                            )
                        active_parcel_to_route[parcel_id] = route.route_id

        for notification in self.customer_notifications:
            order = self._require(notification.order_id, orders, "notification order")
            parcel = self._require(notification.parcel_id, parcels, "notification parcel")
            if parcel.order_id != order.order_id:
                raise ValueError(
                    f"notification {notification.notification_id} order and parcel disagree"
                )
        return self

    @staticmethod
    def _unique_index(items: list[DomainModel], id_field: str, label: str) -> dict[str, object]:
        index: dict[str, object] = {}
        for item in items:
            item_id = getattr(item, id_field)
            if item_id in index:
                raise ValueError(f"duplicate {label} ID: {item_id}")
            index[item_id] = item
        return index

    @staticmethod
    def _require(
        entity_id: str | None,
        index: dict[str, object],
        relationship: str,
    ) -> object:
        if entity_id is None or entity_id not in index:
            raise ValueError(f"{relationship} references missing ID: {entity_id}")
        return index[entity_id]
