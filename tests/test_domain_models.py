from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from courier_sim.domain.enums import (
    DeliveryGroupingPolicy,
    DeliveryMethod,
    DriverStatus,
    InboundShipmentStatus,
    ParcelStatus,
    VehicleOperationalStatus,
    VehicleType,
)
from courier_sim.domain.models import (
    CustomerOrder,
    Driver,
    GeographicCoordinates,
    InboundShipment,
    Parcel,
    Vehicle,
)

BUCHAREST = ZoneInfo("Europe/Bucharest")


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, 16, hour, minute, tzinfo=BUCHAREST)


def parcel_data() -> dict[str, object]:
    return {
        "parcel_id": "P-TEST",
        "order_id": "O-TEST",
        "merchant_id": "M-TEST",
        "delivery_group_id": "DG-TEST",
        "delivery_grouping_policy": DeliveryGroupingPolicy.INDEPENDENT,
        "delivery_method": DeliveryMethod.HOME,
        "home_destination_id": "HOME-TEST",
        "status": ParcelStatus.EXPECTED,
        "weight_kg": 1.0,
        "delivery_due_at": at(20),
    }


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(90.01, 20), (-90.01, 20), (44, 180.01), (44, -180.01)],
)
def test_invalid_coordinate_ranges_are_rejected(latitude: float, longitude: float) -> None:
    with pytest.raises(ValidationError):
        GeographicCoordinates(latitude=latitude, longitude=longitude)


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        Driver(
            driver_id="D-TEST",
            display_name="Test Driver",
            shift_start=datetime(2026, 3, 16, 8),
            shift_end=at(17),
            required_break_minutes=30,
            maximum_parcels=20,
            maximum_stops=10,
            status=DriverStatus.AVAILABLE,
        )


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (at(10), None),
        (None, at(11)),
        (at(11), at(10)),
        (at(10), at(10)),
    ],
)
def test_malformed_delivery_windows_are_rejected(
    start: datetime | None,
    end: datetime | None,
) -> None:
    data = parcel_data()
    data["customer_window_start"] = start
    data["customer_window_end"] = end

    with pytest.raises(ValidationError, match="customer window"):
        Parcel.model_validate(data)


def test_home_parcel_cannot_reference_a_locker() -> None:
    data = parcel_data()
    data["home_destination_id"] = None
    data["parcel_locker_id"] = "LOCKER-TEST"

    with pytest.raises(ValidationError, match="home delivery"):
        Parcel.model_validate(data)


def test_locker_parcel_cannot_reference_a_home() -> None:
    data = parcel_data()
    data["delivery_method"] = DeliveryMethod.PARCEL_LOCKER

    with pytest.raises(ValidationError, match="locker delivery"):
        Parcel.model_validate(data)


def test_locker_collection_status_cannot_be_used_for_home_delivery() -> None:
    data = parcel_data()
    data["status"] = ParcelStatus.COLLECTED_BY_CUSTOMER

    with pytest.raises(ValidationError, match="locker completion"):
        Parcel.model_validate(data)


def test_completed_delivery_requires_confirmation() -> None:
    data = parcel_data()
    data["status"] = ParcelStatus.DELIVERED_TO_HOME

    with pytest.raises(ValidationError, match="completed delivery"):
        Parcel.model_validate(data)


def test_delivery_confirmation_requires_a_timestamp() -> None:
    data = parcel_data()
    data["status"] = ParcelStatus.DELIVERED_TO_HOME
    data["delivery_confirmation_sent"] = True

    with pytest.raises(ValidationError, match="confirmation time is required"):
        Parcel.model_validate(data)


def test_confirmation_timestamp_is_absent_when_not_sent() -> None:
    data = parcel_data()
    data["delivery_confirmation_sent_at"] = at(12)

    with pytest.raises(ValidationError, match="confirmation time must be absent"):
        Parcel.model_validate(data)


def test_order_must_have_at_least_one_parcel() -> None:
    with pytest.raises(ValidationError):
        CustomerOrder(
            order_id="O-EMPTY",
            merchant_id="M-TEST",
            customer_id="C-TEST",
            parcel_ids=[],
            delivery_group_id="DG-EMPTY",
            delivery_grouping_policy=DeliveryGroupingPolicy.INDEPENDENT,
            created_at=at(1),
        )


def test_shipment_parcel_count_must_match_ids() -> None:
    with pytest.raises(ValidationError, match="parcel_count"):
        InboundShipment(
            shipment_id="SHIP-TEST",
            merchant_id="M-TEST",
            origin="Fictional origin",
            expected_arrival_at=at(6),
            parcel_ids=["P-1", "P-2"],
            parcel_count=1,
            status=InboundShipmentStatus.SCHEDULED,
            created_at=at(1),
        )


def test_early_shipment_arrival_is_valid() -> None:
    shipment = InboundShipment(
        shipment_id="SHIP-EARLY",
        merchant_id="M-TEST",
        origin="Fictional origin",
        expected_arrival_at=at(7),
        actual_arrival_at=at(6, 45),
        parcel_ids=["P-1"],
        parcel_count=1,
        status=InboundShipmentStatus.ARRIVED,
        created_at=at(1),
    )

    assert shipment.actual_arrival_at < shipment.expected_arrival_at


def test_invalid_driver_shift_is_rejected() -> None:
    with pytest.raises(ValidationError, match="shift start"):
        Driver(
            driver_id="D-TEST",
            display_name="Test Driver",
            shift_start=at(17),
            shift_end=at(8),
            required_break_minutes=30,
            maximum_parcels=20,
            maximum_stops=10,
            status=DriverStatus.AVAILABLE,
        )


@pytest.mark.parametrize(
    ("weight_capacity", "parcel_capacity"),
    [(0, 10), (-1, 10), (100, 0), (100, -1)],
)
def test_non_positive_vehicle_capacity_is_rejected(
    weight_capacity: float,
    parcel_capacity: int,
) -> None:
    with pytest.raises(ValidationError):
        Vehicle(
            vehicle_id="V-TEST",
            vehicle_type=VehicleType.VAN,
            weight_capacity_kg=weight_capacity,
            parcel_count_capacity=parcel_capacity,
            operational_status=VehicleOperationalStatus.AVAILABLE,
        )
