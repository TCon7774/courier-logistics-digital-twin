from courier_sim.domain.enums import (
    DeliveryGroupingPolicy,
    DeliveryMethod,
    InboundShipmentStatus,
    ParcelStatus,
)
from courier_sim.sample_data.bucharest import build_sample_bucharest_scenario


def test_sample_scenario_constructs_and_has_required_shape() -> None:
    scenario = build_sample_bucharest_scenario()

    assert len(scenario.warehouses) == 1
    assert len(scenario.merchants) == 3
    assert len(scenario.home_destinations) >= 5
    assert len(scenario.parcel_lockers) >= 3
    assert len(scenario.inbound_shipments) >= 3
    assert len(scenario.orders) >= 4
    assert len(scenario.drivers) >= 3
    assert len(scenario.vehicles) >= 3
    assert len(scenario.routes) >= 2


def test_sample_contains_requested_operational_states() -> None:
    scenario = build_sample_bucharest_scenario()
    statuses = {parcel.status for parcel in scenario.parcels}

    assert {
        ParcelStatus.EXPECTED,
        ParcelStatus.RECEIVED,
        ParcelStatus.SORTED,
        ParcelStatus.STAGED_FOR_ROUTE,
        ParcelStatus.LOADED,
        ParcelStatus.DELIVERED_TO_HOME,
        ParcelStatus.DELIVERED_TO_LOCKER,
        ParcelStatus.COLLECTED_BY_CUSTOMER,
        ParcelStatus.DAMAGE_REVIEW,
    } <= statuses
    assert any(
        shipment.status is InboundShipmentStatus.DELAYED for shipment in scenario.inbound_shipments
    )
    assert scenario.customer_notifications


def test_home_and_locker_completion_confirmations_are_present() -> None:
    scenario = build_sample_bucharest_scenario()

    completed_home = next(
        parcel for parcel in scenario.parcels if parcel.status is ParcelStatus.DELIVERED_TO_HOME
    )
    deposited_locker = next(
        parcel for parcel in scenario.parcels if parcel.status is ParcelStatus.DELIVERED_TO_LOCKER
    )

    assert completed_home.delivery_confirmation_sent
    assert completed_home.delivery_confirmation_sent_at is not None
    assert deposited_locker.delivery_confirmation_sent
    assert deposited_locker.delivery_confirmation_sent_at is not None
    assert deposited_locker.delivery_method is DeliveryMethod.PARCEL_LOCKER


def test_sample_has_collected_and_uncollected_locker_parcels() -> None:
    scenario = build_sample_bucharest_scenario()
    locker_statuses = {
        parcel.status
        for parcel in scenario.parcels
        if parcel.delivery_method is DeliveryMethod.PARCEL_LOCKER
    }

    assert ParcelStatus.DELIVERED_TO_LOCKER in locker_statuses
    assert ParcelStatus.COLLECTED_BY_CUSTOMER in locker_statuses


def test_together_preferred_group_is_represented_consistently() -> None:
    scenario = build_sample_bucharest_scenario()
    order = next(order for order in scenario.orders if order.order_id == "O-1001")
    grouped_parcels = [parcel for parcel in scenario.parcels if parcel.order_id == order.order_id]

    assert len(grouped_parcels) > 1
    assert order.delivery_grouping_policy is DeliveryGroupingPolicy.TOGETHER_PREFERRED
    assert {
        (parcel.delivery_group_id, parcel.delivery_grouping_policy) for parcel in grouped_parcels
    } == {("DG-1001", DeliveryGroupingPolicy.TOGETHER_PREFERRED)}


def test_seed_parameter_preserves_deterministic_sample() -> None:
    first = build_sample_bucharest_scenario(seed=1)
    second = build_sample_bucharest_scenario(seed=999)

    assert first == second
