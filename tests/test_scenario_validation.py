from copy import deepcopy

import pytest
from pydantic import ValidationError

from courier_sim.domain.enums import DriverStatus, VehicleOperationalStatus
from courier_sim.domain.models import LogisticsScenario
from courier_sim.sample_data.bucharest import build_sample_bucharest_scenario


def sample_data() -> dict[str, object]:
    return build_sample_bucharest_scenario().model_dump(mode="python")


def test_parcel_referencing_missing_order_is_rejected() -> None:
    data = sample_data()
    orphan = deepcopy(data["parcels"][0])
    orphan["parcel_id"] = "P-MISSING-ORDER"
    orphan["order_id"] = "O-NOT-THERE"
    data["parcels"].append(orphan)

    with pytest.raises(ValidationError, match="parcel order references missing"):
        LogisticsScenario.model_validate(data)


def test_duplicate_parcel_ids_are_rejected() -> None:
    data = sample_data()
    data["parcels"].append(deepcopy(data["parcels"][0]))

    with pytest.raises(ValidationError, match="duplicate parcel ID"):
        LogisticsScenario.model_validate(data)


def test_parcel_in_multiple_inbound_shipments_is_rejected() -> None:
    data = sample_data()
    duplicate_id = data["inbound_shipments"][0]["parcel_ids"][0]
    data["inbound_shipments"][1]["parcel_ids"].append(duplicate_id)
    data["inbound_shipments"][1]["parcel_count"] += 1

    with pytest.raises(ValidationError, match="appears in shipments"):
        LogisticsScenario.model_validate(data)


def test_inconsistent_driver_vehicle_assignment_is_rejected() -> None:
    data = sample_data()
    data["drivers"][0]["current_vehicle_id"] = "VAN-03"

    with pytest.raises(ValidationError, match="assignments disagree"):
        LogisticsScenario.model_validate(data)


def test_scenario_with_more_than_one_warehouse_is_rejected() -> None:
    data = sample_data()
    second_warehouse = deepcopy(data["warehouses"][0])
    second_warehouse["warehouse_id"] = "WH-B-02"
    second_warehouse["name"] = "Second Fictional Warehouse"
    data["warehouses"].append(second_warehouse)

    with pytest.raises(ValidationError, match="exactly one warehouse"):
        LogisticsScenario.model_validate(data)


def test_order_parcel_back_references_must_agree() -> None:
    data = sample_data()
    data["orders"][0]["parcel_ids"].remove("P-1001-B")

    with pytest.raises(ValidationError, match="must exactly match"):
        LogisticsScenario.model_validate(data)


def test_missing_parcel_destination_is_rejected_at_scenario_level() -> None:
    data = sample_data()
    data["parcels"][0]["home_destination_id"] = "HOME-NOT-THERE"

    with pytest.raises(ValidationError, match="parcel home destination references missing"):
        LogisticsScenario.model_validate(data)


def test_route_stop_destination_must_match_its_parcel() -> None:
    data = sample_data()
    data["routes"][0]["stops"][0]["home_destination_id"] = "HOME-002"

    with pytest.raises(ValidationError, match="route-stop destination"):
        LogisticsScenario.model_validate(data)


def test_route_stop_ids_must_be_unique_across_scenario() -> None:
    data = sample_data()
    data["routes"][1]["stops"][0]["route_stop_id"] = "R1-S1"

    with pytest.raises(ValidationError, match="duplicate route stop ID"):
        LogisticsScenario.model_validate(data)


def test_parcel_cannot_appear_on_multiple_active_routes() -> None:
    data = sample_data()
    data["routes"][1]["stops"].append(
        {
            "route_stop_id": "R2-S3",
            "sequence": 3,
            "parcel_ids": ["P-1002-A"],
            "parcel_locker_id": "LOCKER-CENTRAL",
        }
    )

    with pytest.raises(ValidationError, match="appears on active routes"):
        LogisticsScenario.model_validate(data)


def test_home_destination_must_belong_to_order_customer() -> None:
    data = sample_data()
    parcel = next(item for item in data["parcels"] if item["parcel_id"] == "P-1005-A")
    parcel["home_destination_id"] = "HOME-002"

    with pytest.raises(ValidationError, match="must belong to its order customer"):
        LogisticsScenario.model_validate(data)


def test_driver_status_must_match_active_assignment() -> None:
    data = sample_data()
    data["drivers"][0]["status"] = DriverStatus.AVAILABLE

    with pytest.raises(ValidationError, match="current assignment must be ASSIGNED"):
        LogisticsScenario.model_validate(data)


def test_vehicle_status_must_match_in_progress_route() -> None:
    data = sample_data()
    data["vehicles"][0]["operational_status"] = VehicleOperationalStatus.AVAILABLE

    with pytest.raises(ValidationError, match="must be IN_SERVICE"):
        LogisticsScenario.model_validate(data)
