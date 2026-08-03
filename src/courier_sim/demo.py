"""Small demonstration of sample-scenario construction and validation."""

from collections import Counter

from courier_sim.engine.commands import InitializeSimulationCommand, NextScheduledActionCommand
from courier_sim.engine.processor import CommandProcessor
from courier_sim.engine.state import build_initial_state
from courier_sim.sample_data.bucharest import build_sample_bucharest_scenario


def main() -> None:
    scenario = build_sample_bucharest_scenario()

    counts = {
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
    status_counts = Counter(parcel.status.value for parcel in scenario.parcels)

    print(f"Validated scenario: {scenario.scenario_id}")
    print(f"Timezone: {scenario.timezone}")
    print("\nEntity counts")
    for label, count in counts.items():
        print(f"  {label:<12} {count}")

    print("\nParcels by status")
    for status, count in sorted(status_counts.items()):
        print(f"  {status:<24} {count}")

    example_order = scenario.orders[0]
    print("\nExample relationships")
    print(
        f"  Order {example_order.order_id} -> parcels "
        f"{', '.join(example_order.parcel_ids)} "
        f"({example_order.delivery_grouping_policy.value})"
    )
    first_route = scenario.routes[0]
    print(
        f"  Route {first_route.route_id} -> driver {first_route.driver_id}, "
        f"vehicle {first_route.vehicle_id}, {len(first_route.stops)} stops"
    )

    initialized = CommandProcessor(build_initial_state("RUN-DEMO-001", seed=42)).execute(
        InitializeSimulationCommand()
    )
    advanced = CommandProcessor(initialized.state).execute(NextScheduledActionCommand())
    print("\nSimulation engine")
    print(f"  {initialized.events[0].event_id}: {initialized.events[0].event_type.value}")
    print(
        f"  Processed {len(advanced.events)} events; "
        f"next event ID is EVT-{advanced.state.next_event_sequence:06d}"
    )


if __name__ == "__main__":
    main()
