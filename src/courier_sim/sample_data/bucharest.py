"""A fixed, fictional logistics scenario using plausible Bucharest coordinates."""

from datetime import datetime
from zoneinfo import ZoneInfo

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
from courier_sim.domain.models import (
    Customer,
    CustomerNotification,
    CustomerOrder,
    Driver,
    GeographicCoordinates,
    HomeDestination,
    InboundShipment,
    LogisticsScenario,
    Merchant,
    Parcel,
    ParcelLocker,
    Route,
    RouteStop,
    Vehicle,
    Warehouse,
)

BUCHAREST = ZoneInfo("Europe/Bucharest")


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, 16, hour, minute, tzinfo=BUCHAREST)


def build_sample_bucharest_scenario(seed: int = 42) -> LogisticsScenario:
    """Build fixed sample data; ``seed`` is reserved for future deterministic expansion."""
    _ = seed

    warehouses = [
        Warehouse(
            warehouse_id="WH-B-01",
            name="Dambovita Regional Parcel Hub",
            address_line="Fictional Logistics Avenue 10",
            coordinates=GeographicCoordinates(latitude=44.4318, longitude=26.0755),
        )
    ]

    merchants = [
        Merchant(
            merchant_id="M-NOVA",
            name="NovaCart Online",
            origin_description="Fictional Ploiesti fulfillment center",
            created_at=_at(0),
        ),
        Merchant(
            merchant_id="M-LUMEN",
            name="Lumen Home Market",
            origin_description="Fictional Brasov fulfillment center",
            created_at=_at(0),
        ),
        Merchant(
            merchant_id="M-ORBIT",
            name="Orbit Tech Bazaar",
            origin_description="Fictional Pitesti fulfillment center",
            created_at=_at(0),
        ),
    ]

    customers = [
        Customer(customer_id="C-001", display_name="Alex D.", created_at=_at(0)),
        Customer(customer_id="C-002", display_name="Mara I.", created_at=_at(0)),
        Customer(customer_id="C-003", display_name="Radu P.", created_at=_at(0)),
        Customer(customer_id="C-004", display_name="Elena S.", created_at=_at(0)),
        Customer(customer_id="C-005", display_name="Victor N.", created_at=_at(0)),
        Customer(customer_id="C-006", display_name="Ioana T.", created_at=_at(0)),
    ]

    home_destinations = [
        HomeDestination(
            home_destination_id="HOME-001",
            customer_id="C-001",
            label="Alex home",
            address_line="Fictional Linden Street 14",
            coordinates=GeographicCoordinates(latitude=44.4474, longitude=26.0979),
        ),
        HomeDestination(
            home_destination_id="HOME-002",
            customer_id="C-002",
            label="Mara home",
            address_line="Fictional Viilor Street 22",
            coordinates=GeographicCoordinates(latitude=44.4156, longitude=26.0815),
        ),
        HomeDestination(
            home_destination_id="HOME-003",
            customer_id="C-003",
            label="Radu home",
            address_line="Fictional Tei Lane 7",
            coordinates=GeographicCoordinates(latitude=44.4687, longitude=26.1138),
        ),
        HomeDestination(
            home_destination_id="HOME-004",
            customer_id="C-004",
            label="Elena home",
            address_line="Fictional Titan Boulevard 31",
            coordinates=GeographicCoordinates(latitude=44.4219, longitude=26.1615),
        ),
        HomeDestination(
            home_destination_id="HOME-005",
            customer_id="C-005",
            label="Victor home",
            address_line="Fictional Drumul Taberei Road 18",
            coordinates=GeographicCoordinates(latitude=44.4207, longitude=26.0365),
        ),
    ]

    parcel_lockers = [
        ParcelLocker(
            parcel_locker_id="LOCKER-CENTRAL",
            name="Central Square Fictional Locker",
            address_line="Fictional Academiei Street 4",
            coordinates=GeographicCoordinates(latitude=44.4355, longitude=26.1012),
            parcel_capacity=80,
        ),
        ParcelLocker(
            parcel_locker_id="LOCKER-NORTH",
            name="North Park Fictional Locker",
            address_line="Fictional Aviatiei Road 16",
            coordinates=GeographicCoordinates(latitude=44.4822, longitude=26.1018),
            parcel_capacity=60,
        ),
        ParcelLocker(
            parcel_locker_id="LOCKER-EAST",
            name="East Gate Fictional Locker",
            address_line="Fictional Basarabia Boulevard 55",
            coordinates=GeographicCoordinates(latitude=44.4372, longitude=26.1691),
            parcel_capacity=72,
        ),
    ]

    orders = [
        CustomerOrder(
            order_id="O-1001",
            merchant_id="M-NOVA",
            customer_id="C-001",
            parcel_ids=["P-1001-A", "P-1001-B"],
            delivery_group_id="DG-1001",
            delivery_grouping_policy=DeliveryGroupingPolicy.TOGETHER_PREFERRED,
            created_at=_at(1),
        ),
        CustomerOrder(
            order_id="O-1002",
            merchant_id="M-NOVA",
            customer_id="C-002",
            parcel_ids=["P-1002-A"],
            delivery_group_id="DG-1002",
            delivery_grouping_policy=DeliveryGroupingPolicy.INDEPENDENT,
            created_at=_at(1, 5),
        ),
        CustomerOrder(
            order_id="O-1003",
            merchant_id="M-NOVA",
            customer_id="C-003",
            parcel_ids=["P-1003-A"],
            delivery_group_id="DG-1003",
            delivery_grouping_policy=DeliveryGroupingPolicy.INDEPENDENT,
            created_at=_at(1, 10),
        ),
        CustomerOrder(
            order_id="O-1004",
            merchant_id="M-ORBIT",
            customer_id="C-004",
            parcel_ids=["P-1004-A"],
            delivery_group_id="DG-1004",
            delivery_grouping_policy=DeliveryGroupingPolicy.INDEPENDENT,
            created_at=_at(1, 15),
        ),
        CustomerOrder(
            order_id="O-1005",
            merchant_id="M-LUMEN",
            customer_id="C-005",
            parcel_ids=["P-1005-A"],
            delivery_group_id="DG-1005",
            delivery_grouping_policy=DeliveryGroupingPolicy.INDEPENDENT,
            created_at=_at(1, 20),
        ),
        CustomerOrder(
            order_id="O-1006",
            merchant_id="M-ORBIT",
            customer_id="C-001",
            parcel_ids=["P-1006-A"],
            delivery_group_id="DG-1006",
            delivery_grouping_policy=DeliveryGroupingPolicy.INDEPENDENT,
            created_at=_at(1, 25),
        ),
        CustomerOrder(
            order_id="O-1007",
            merchant_id="M-LUMEN",
            customer_id="C-002",
            parcel_ids=["P-1007-A"],
            delivery_group_id="DG-1007",
            delivery_grouping_policy=DeliveryGroupingPolicy.INDEPENDENT,
            created_at=_at(1, 30),
        ),
        CustomerOrder(
            order_id="O-1008",
            merchant_id="M-LUMEN",
            customer_id="C-006",
            parcel_ids=["P-1008-A"],
            delivery_group_id="DG-1008",
            delivery_grouping_policy=DeliveryGroupingPolicy.INDEPENDENT,
            created_at=_at(1, 35),
        ),
        CustomerOrder(
            order_id="O-1009",
            merchant_id="M-LUMEN",
            customer_id="C-005",
            parcel_ids=["P-1009-A"],
            delivery_group_id="DG-1009",
            delivery_grouping_policy=DeliveryGroupingPolicy.INDEPENDENT,
            created_at=_at(1, 40),
        ),
    ]

    common_due = _at(20)
    parcels = [
        Parcel(
            parcel_id="P-1001-A",
            order_id="O-1001",
            merchant_id="M-NOVA",
            delivery_group_id="DG-1001",
            delivery_grouping_policy=DeliveryGroupingPolicy.TOGETHER_PREFERRED,
            delivery_method=DeliveryMethod.HOME,
            home_destination_id="HOME-001",
            status=ParcelStatus.DELIVERED_TO_HOME,
            weight_kg=1.4,
            delivery_due_at=common_due,
            customer_window_start=_at(9),
            customer_window_end=_at(11),
            estimated_arrival_start=_at(9, 20),
            estimated_arrival_end=_at(9, 40),
            internal_target_at=_at(10),
            delivery_confirmation_sent=True,
            delivery_confirmation_sent_at=_at(9, 33),
        ),
        Parcel(
            parcel_id="P-1001-B",
            order_id="O-1001",
            merchant_id="M-NOVA",
            delivery_group_id="DG-1001",
            delivery_grouping_policy=DeliveryGroupingPolicy.TOGETHER_PREFERRED,
            delivery_method=DeliveryMethod.HOME,
            home_destination_id="HOME-001",
            status=ParcelStatus.DELIVERED_TO_HOME,
            weight_kg=0.8,
            delivery_due_at=common_due,
            customer_window_start=_at(9),
            customer_window_end=_at(11),
            estimated_arrival_start=_at(9, 20),
            estimated_arrival_end=_at(9, 40),
            internal_target_at=_at(10),
            delivery_confirmation_sent=True,
            delivery_confirmation_sent_at=_at(9, 33),
        ),
        Parcel(
            parcel_id="P-1002-A",
            order_id="O-1002",
            merchant_id="M-NOVA",
            delivery_group_id="DG-1002",
            delivery_grouping_policy=DeliveryGroupingPolicy.INDEPENDENT,
            delivery_method=DeliveryMethod.PARCEL_LOCKER,
            parcel_locker_id="LOCKER-CENTRAL",
            status=ParcelStatus.DELIVERED_TO_LOCKER,
            weight_kg=2.1,
            delivery_due_at=common_due,
            delivery_confirmation_sent=True,
            delivery_confirmation_sent_at=_at(10, 5),
        ),
        Parcel(
            parcel_id="P-1003-A",
            order_id="O-1003",
            merchant_id="M-NOVA",
            delivery_group_id="DG-1003",
            delivery_grouping_policy=DeliveryGroupingPolicy.INDEPENDENT,
            delivery_method=DeliveryMethod.PARCEL_LOCKER,
            parcel_locker_id="LOCKER-NORTH",
            status=ParcelStatus.COLLECTED_BY_CUSTOMER,
            weight_kg=0.6,
            delivery_due_at=common_due,
            delivery_confirmation_sent=True,
            delivery_confirmation_sent_at=_at(10, 25),
            collected_at=_at(10, 40),
        ),
        Parcel(
            parcel_id="P-1004-A",
            order_id="O-1004",
            merchant_id="M-ORBIT",
            delivery_group_id="DG-1004",
            delivery_grouping_policy=DeliveryGroupingPolicy.INDEPENDENT,
            delivery_method=DeliveryMethod.HOME,
            home_destination_id="HOME-004",
            status=ParcelStatus.DAMAGE_REVIEW,
            weight_kg=3.2,
            delivery_due_at=common_due,
        ),
        Parcel(
            parcel_id="P-1005-A",
            order_id="O-1005",
            merchant_id="M-LUMEN",
            delivery_group_id="DG-1005",
            delivery_grouping_policy=DeliveryGroupingPolicy.INDEPENDENT,
            delivery_method=DeliveryMethod.HOME,
            home_destination_id="HOME-005",
            status=ParcelStatus.EXPECTED,
            weight_kg=4.0,
            delivery_due_at=common_due,
        ),
        Parcel(
            parcel_id="P-1006-A",
            order_id="O-1006",
            merchant_id="M-ORBIT",
            delivery_group_id="DG-1006",
            delivery_grouping_policy=DeliveryGroupingPolicy.INDEPENDENT,
            delivery_method=DeliveryMethod.HOME,
            home_destination_id="HOME-001",
            status=ParcelStatus.RECEIVED,
            weight_kg=1.1,
            delivery_due_at=common_due,
        ),
        Parcel(
            parcel_id="P-1007-A",
            order_id="O-1007",
            merchant_id="M-LUMEN",
            delivery_group_id="DG-1007",
            delivery_grouping_policy=DeliveryGroupingPolicy.INDEPENDENT,
            delivery_method=DeliveryMethod.HOME,
            home_destination_id="HOME-002",
            status=ParcelStatus.SORTED,
            weight_kg=1.7,
            delivery_due_at=common_due,
        ),
        Parcel(
            parcel_id="P-1008-A",
            order_id="O-1008",
            merchant_id="M-LUMEN",
            delivery_group_id="DG-1008",
            delivery_grouping_policy=DeliveryGroupingPolicy.INDEPENDENT,
            delivery_method=DeliveryMethod.PARCEL_LOCKER,
            parcel_locker_id="LOCKER-EAST",
            status=ParcelStatus.STAGED_FOR_ROUTE,
            weight_kg=2.3,
            delivery_due_at=common_due,
        ),
        Parcel(
            parcel_id="P-1009-A",
            order_id="O-1009",
            merchant_id="M-LUMEN",
            delivery_group_id="DG-1009",
            delivery_grouping_policy=DeliveryGroupingPolicy.INDEPENDENT,
            delivery_method=DeliveryMethod.HOME,
            home_destination_id="HOME-005",
            status=ParcelStatus.LOADED,
            weight_kg=5.5,
            delivery_due_at=common_due,
            estimated_arrival_start=_at(14),
            estimated_arrival_end=_at(14, 30),
            internal_target_at=_at(15),
        ),
    ]

    inbound_shipments = [
        InboundShipment(
            shipment_id="SHIP-001",
            merchant_id="M-NOVA",
            origin="Fictional Ploiesti fulfillment center",
            expected_arrival_at=_at(6),
            actual_arrival_at=_at(5, 50),
            parcel_ids=["P-1001-A", "P-1001-B", "P-1002-A", "P-1003-A"],
            parcel_count=4,
            status=InboundShipmentStatus.PROCESSED,
            created_at=_at(0, 30),
            received_at=_at(5, 55),
        ),
        InboundShipment(
            shipment_id="SHIP-002",
            merchant_id="M-LUMEN",
            origin="Fictional Brasov fulfillment center",
            expected_arrival_at=_at(7),
            parcel_ids=["P-1005-A"],
            parcel_count=1,
            status=InboundShipmentStatus.DELAYED,
            created_at=_at(0, 35),
        ),
        InboundShipment(
            shipment_id="SHIP-003",
            merchant_id="M-ORBIT",
            origin="Fictional Pitesti fulfillment center",
            expected_arrival_at=_at(7),
            actual_arrival_at=_at(7, 10),
            parcel_ids=["P-1004-A", "P-1006-A"],
            parcel_count=2,
            status=InboundShipmentStatus.RECEIVING,
            created_at=_at(0, 40),
            received_at=_at(7, 15),
        ),
        InboundShipment(
            shipment_id="SHIP-004",
            merchant_id="M-LUMEN",
            origin="Fictional Brasov fulfillment center",
            expected_arrival_at=_at(6, 30),
            actual_arrival_at=_at(6, 25),
            parcel_ids=["P-1007-A", "P-1008-A", "P-1009-A"],
            parcel_count=3,
            status=InboundShipmentStatus.PROCESSED,
            created_at=_at(0, 45),
            received_at=_at(6, 28),
        ),
    ]

    drivers = [
        Driver(
            driver_id="D-01",
            display_name="Andrei V.",
            shift_start=_at(8),
            shift_end=_at(17),
            required_break_minutes=30,
            maximum_parcels=80,
            maximum_stops=45,
            status=DriverStatus.ASSIGNED,
            current_vehicle_id="VAN-01",
            current_route_id="ROUTE-01",
        ),
        Driver(
            driver_id="D-02",
            display_name="Sorina M.",
            shift_start=_at(8),
            shift_end=_at(17),
            required_break_minutes=30,
            maximum_parcels=70,
            maximum_stops=40,
            status=DriverStatus.ASSIGNED,
            current_vehicle_id="VAN-02",
            current_route_id="ROUTE-02",
        ),
        Driver(
            driver_id="D-03",
            display_name="Mihai C.",
            shift_start=_at(9),
            shift_end=_at(18),
            required_break_minutes=30,
            maximum_parcels=60,
            maximum_stops=35,
            status=DriverStatus.AVAILABLE,
        ),
    ]

    vehicles = [
        Vehicle(
            vehicle_id="VAN-01",
            vehicle_type=VehicleType.ELECTRIC_VAN,
            weight_capacity_kg=850,
            parcel_count_capacity=100,
            operational_status=VehicleOperationalStatus.IN_SERVICE,
            current_driver_id="D-01",
            current_route_id="ROUTE-01",
        ),
        Vehicle(
            vehicle_id="VAN-02",
            vehicle_type=VehicleType.CARGO_VAN,
            weight_capacity_kg=1200,
            parcel_count_capacity=130,
            operational_status=VehicleOperationalStatus.ASSIGNED,
            current_driver_id="D-02",
            current_route_id="ROUTE-02",
        ),
        Vehicle(
            vehicle_id="VAN-03",
            vehicle_type=VehicleType.VAN,
            weight_capacity_kg=900,
            parcel_count_capacity=105,
            operational_status=VehicleOperationalStatus.AVAILABLE,
        ),
    ]

    routes = [
        Route(
            route_id="ROUTE-01",
            warehouse_id="WH-B-01",
            status=RouteStatus.IN_PROGRESS,
            driver_id="D-01",
            vehicle_id="VAN-01",
            historical_driver_id="D-01",
            historical_vehicle_id="VAN-01",
            started_at=_at(8, 30),
            stops=[
                RouteStop(
                    route_stop_id="R1-S1",
                    sequence=1,
                    parcel_ids=["P-1001-A", "P-1001-B"],
                    home_destination_id="HOME-001",
                    estimated_arrival_start=_at(9, 20),
                    estimated_arrival_end=_at(9, 40),
                ),
                RouteStop(
                    route_stop_id="R1-S2",
                    sequence=2,
                    parcel_ids=["P-1002-A"],
                    parcel_locker_id="LOCKER-CENTRAL",
                ),
                RouteStop(
                    route_stop_id="R1-S3",
                    sequence=3,
                    parcel_ids=["P-1003-A"],
                    parcel_locker_id="LOCKER-NORTH",
                ),
            ],
        ),
        Route(
            route_id="ROUTE-02",
            warehouse_id="WH-B-01",
            status=RouteStatus.ASSIGNED,
            driver_id="D-02",
            vehicle_id="VAN-02",
            historical_driver_id="D-02",
            historical_vehicle_id="VAN-02",
            stops=[
                RouteStop(
                    route_stop_id="R2-S1",
                    sequence=1,
                    parcel_ids=["P-1009-A"],
                    home_destination_id="HOME-005",
                    estimated_arrival_start=_at(14),
                    estimated_arrival_end=_at(14, 30),
                ),
                RouteStop(
                    route_stop_id="R2-S2",
                    sequence=2,
                    parcel_ids=["P-1008-A"],
                    parcel_locker_id="LOCKER-EAST",
                ),
            ],
        ),
        Route(
            route_id="ROUTE-03",
            warehouse_id="WH-B-01",
            status=RouteStatus.PLANNED,
            stops=[
                RouteStop(
                    route_stop_id="R3-S1",
                    sequence=1,
                    parcel_ids=["P-1005-A"],
                    home_destination_id="HOME-005",
                )
            ],
        ),
    ]

    customer_notifications = [
        CustomerNotification(
            notification_id="N-001",
            order_id="O-1004",
            parcel_id="P-1004-A",
            failure_type=FailureType.DAMAGED_PARCEL,
            message=(
                "Your parcel is under review after damage was detected. "
                "A further update will follow."
            ),
            communication_channel=CommunicationChannel.EMAIL,
            created_at=_at(8, 5),
            sent_at=_at(8, 10),
            delivery_status=NotificationDeliveryStatus.SENT,
        )
    ]

    return LogisticsScenario(
        scenario_id="BUCHAREST-M1-2026-03-16",
        warehouses=warehouses,
        merchants=merchants,
        customers=customers,
        home_destinations=home_destinations,
        parcel_lockers=parcel_lockers,
        orders=orders,
        parcels=parcels,
        inbound_shipments=inbound_shipments,
        drivers=drivers,
        vehicles=vehicles,
        routes=routes,
        customer_notifications=customer_notifications,
    )
