# Locked domain decisions

This document preserves the business decisions that future milestones must respect.

## Geography and data provenance

- Version 1 has exactly one fictional warehouse serving Bucharest.
- Destinations are homes or parcel lockers.
- Coordinates are geographically plausible within or around Bucharest, but they do not
  represent actual customers, merchants, courier infrastructure, or addresses.
- There are no real roads, real addresses, map integrations, travel-time calculations, or
  routing services yet.
- A later milestone may replace the coordinate-only representation with a more realistic
  routing layer.

## Merchants and inbound shipments

- Multiple fictional online merchants can each send multiple shipments per day.
- Shipments have independent identifiers, merchant and origin references, expected and actual
  arrival times, parcel IDs and counts, status, creation time, and optional received time.
- Several merchants may have overlapping arrival times.
- Early arrival is valid: actual arrival is not required to be later than expected arrival.
- Shipment statuses include scheduled, in transit, delayed, arrived, receiving, processed,
  partially received, and missing.

## Orders, parcels, and delivery grouping

- Customer orders and parcels are separate entities.
- One order may contain multiple independently identifiable and trackable parcels.
- Each order defines a delivery group and grouping policy.
- Ordinary multi-parcel e-commerce orders use `TOGETHER_PREFERRED`: their parcels should use
  the same route and stop when this does not violate deadlines, vehicle capacity, driver
  limits, or other operational constraints.
- `TOGETHER_PREFERRED` is not an absolute co-delivery requirement.
- The extensible grouping-policy enum also contains `TOGETHER_REQUIRED` and `INDEPENDENT`.

## Delivery methods and completion

- Delivery method is explicit: home or parcel locker.
- A home parcel references only a home destination; a locker parcel references only a locker.
- Home delivery completes at `DELIVERED_TO_HOME`.
- The locker lifecycle distinguishes `DELIVERED_TO_LOCKER` from
  `COLLECTED_BY_CUSTOMER`.
- The driver's task ends when the parcel is deposited at the locker. Collection remains in
  parcel history and is valid only for locker delivery.
- At home delivery or locker deposit, the model supports a confirmation Boolean and timestamp.
  A sent confirmation requires a timestamp; an unsent confirmation cannot have one.

## Warehouse parcel lifecycle

The conceptual movement states are expected, received, scanned, sorted, staged for route,
loaded, and out for delivery. Later outcomes include delivered to home, delivered to locker,
collected by customer, delivery failed, returned to warehouse, damage review, returned to
sender, and cancelled.

Exact shelves, conveyors, workers, forklifts, and physical warehouse movement are not modeled.

## Drivers, vehicles, and routes

- Drivers, vehicles, and routes are separate entities.
- A driver does not permanently own a vehicle.
- At shift start, an available driver may be assigned a compatible available vehicle and
  route.
- Driver data includes shift bounds, required break duration, maximum parcel and stop
  workloads, availability status, and optional current assignments.
- Vehicle data includes type, weight and parcel-count capacities, operational status, and
  optional current assignments.
- Driver, vehicle, and route links must be mutually consistent.
- Routes are structured domain objects only. There is no route planning, optimization,
  distance calculation, or execution logic in Milestone 1.

## Timing

- All datetimes are timezone-aware. The sample uses `Europe/Bucharest`.
- `delivery_due_at` is the contractual final deadline.
- `customer_window_start` and `customer_window_end` describe an optional promised or selected
  home-delivery window.
- `estimated_arrival_start` and `estimated_arrival_end` are changeable estimates.
- `internal_target_at` is an operational target.
- Time-window fields are paired, and their starts precede their ends.
- Standard locker delivery normally has only an end-of-working-day contractual deadline and
  no fixed customer-facing delivery window.

## Failures and customer notifications

The domain can represent customer absence, a full locker, vehicle breakdown, general
operational delay, invalid address, impossible deadline, and damaged parcel.

An internal record may identify a vehicle breakdown precisely. A future customer-facing
message will call it an unexpected operational delay.

Notification records are the authoritative history and support notification, order and parcel
IDs, failure type, message, channel, creation and send times, delivery status, whether a
response is required, customer response, and response deadline. Milestone 1 does not send
messages, schedule notifications, or simulate responses. Future customer responses will be
simulated automatically only after their behavior is specified.

## Damaged parcels

The approved future workflow is:

```text
Damage detected
      |
Stop parcel movement
      |
Move parcel to DAMAGE_REVIEW
      |
Record damage evidence
      |
Notify merchant and customer
      |
Merchant chooses:
    replace contents
    repack and resend
    return shipment
    cancel and refund
      |
Assign a new delivery date if applicable
```

Milestone 1 preserves `DAMAGE_REVIEW`, the damaged-parcel failure category, and notification
records. It does not implement this workflow, evidence handling, merchant decisions,
replacement, rescheduling, refunds, or any workflow engine.

## Milestone 2 simulation control

- Illegal parcel, inbound-shipment, and route transitions are rejected. The engine never fills
  skipped states automatically.
- Central transition maps answer whether a state change is generally legal. Conditional
  validators then apply entity-specific delivery-method, route-assignment, and availability
  rules.
- A failed command leaves current state and event history unchanged.
- Simulation time is explicitly controlled, timezone-aware, and displayed as
  `Europe/Bucharest`. It does not advance with wall-clock time.
- Scheduled actions and historical events are separate concepts. Milestone 2 schedules only
  inbound-shipment arrivals.
- Scheduled actions sharing a timestamp execute by datetime, creation sequence, then action ID.
- A manual transition to `ARRIVED` or terminal `MISSING` consumes the corresponding pending
  shipment-arrival action so obsolete work cannot block future time advancement.
- Duration advances represent elapsed time. They use UTC arithmetic and convert back to
  `Europe/Bucharest`, including across daylight-saving boundaries and JSON reloads.

## Route execution and history

- Route history uses full timezone-aware `started_at` and `completed_at` datetimes.
- A route may complete when every planned stop has a recorded parcel outcome; not every
  delivery has to succeed.
- A stop is treated as processed when every parcel at that stop has an explicit route outcome.
  This is derived from parcel statuses rather than stored as a second manually editable flag.
- A structured route outcome summary is derived and retained at completion.
- Current driver, vehicle, and route assignment links are cleared at completion.
- Completed routes retain historical assigned driver and vehicle IDs.
- Driver shift/workload and vehicle parcel-count/weight capacities are checked during
  assignment. No route planning or optimization is performed.
- Driver and vehicle availability statuses must agree with their current assignment links.
- Starting a route rechecks the driver's active shift and both assignment statuses.

## Event identity and persistence

- Event history is append-only. Existing event lines are not edited or removed by normal
  commands.
- Every event has a unique immutable sequence ID within its simulation run.
- Event fields and nested structured metadata are deeply immutable after creation.
- Cross-run event identity is `simulation_run_id + event_id`; event sequences restart for each
  new run.
- Current state uses a human-readable JSON snapshot. Historical events use one JSON object per
  line in an append-only JSONL file.
- Persistence survives separate command executions; each command reloads the previous result.
- Every run has separate `run_metadata.json` containing its seed, lifecycle, simulation
  datetimes, and final event ID.
- Only one simulation run is active at a time under `.simulation/active/`.
- A reset archives the complete old run under
  `.simulation/history/<simulation_run_id>/` before creating a replacement.
- Events from different runs are never mixed.
- `init` never overwrites an existing active run. A subsequent run must use the safe
  reset-and-archive process.
- State, metadata, and history are staged and validated as one complete bundle before a normal
  command is published. Direct snapshot changes without command-generated events are rejected.
- State and run metadata must use the same supported persistence format version.
- `archived_at` is a real administrative UTC timestamp; final simulation time remains in the
  separate `current_simulation_datetime` field.

## Milestone 2 seed scope

The run seed is persisted for experiment identity and future deterministic expansion. The
current Bucharest sample data is deliberately fixed, so different seed values do not yet vary
entities, coordinates, parcels, or routes. Runs still receive independent IDs and histories.
