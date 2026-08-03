# Simulation controls

This is the complete Milestone 2 command reference. Commands run locally and use
`.simulation/` unless another directory is selected.

## Common invocation and files

```powershell
uv run courier-sim --help
uv run courier-sim <COMMAND> --help
```

The global option must appear before the command:

```powershell
uv run courier-sim --simulation-dir ".temporary-simulation" status
```

`--simulation-dir PATH` changes the persistence root. The `COURIER_SIM_DIR` environment
variable provides the same default:

```powershell
$env:COURIER_SIM_DIR = ".temporary-simulation"
uv run courier-sim status
```

Normal active-run files are:

- `active/current_state.json`: what is true now;
- `active/events.jsonl`: one immutable historical event per line;
- `active/run_metadata.json`: run identity, seed, lifecycle, and final event ID.

Read-only commands still validate all three files before displaying information. A normal
state-changing command loads all three, appends only new event lines, atomically replaces the
snapshot, and updates metadata. Expected user errors return exit code 2 without a traceback.

## Starting and resetting

### `init`

Purpose: create the first active deterministic Bucharest simulation.

```powershell
uv run courier-sim init [--seed INTEGER]
uv run courier-sim init --seed 42
```

- Options: `--seed` records the deterministic experiment seed; default `42`. Milestone 2's
  sample entities are fixed, so different seed values currently change run identity and
  history separation but not the starting scenario contents.
- Changes state: yes, by creating the active run.
- Creates events: yes, `SIMULATION_INITIALIZED` as `EVT-000001`.
- Files: creates the three active files and `.simulation/history/`.
- Common rejection: an active directory already exists, even if another seed is supplied.
  Use `reset --force`; `init` has no overwrite option.
- Plain language: use this once when no simulation exists yet.

### `reset`

Purpose: archive the complete active run and create an independent new run.

```powershell
uv run courier-sim reset [--seed INTEGER] [--force]
uv run courier-sim reset --seed 42 --force
uv run courier-sim reset --seed 73 --force
```

- Options: `--seed` selects the new seed; `--force` confirms archive-and-reset when a run is
  active.
- Changes state: yes.
- Creates events: the new run gets its own `SIMULATION_INITIALIZED` event. No event is copied
  from the archived run.
- Files: validates and archives all active files under
  `history/<old-simulation-run-id>/`, then creates three fresh active files.
- Archive metadata: same-seed reset records `FORCE_RESET`; a changed seed records `NEW_SEED`.
- Archive timestamp: `archived_at` records the real administrative archive time in UTC, while
  `current_simulation_datetime` records the run's final simulated time.
- Common rejection: omitted `--force`, corrupt active persistence, an existing archive target,
  or any archive/copy/validation failure. A failed archive leaves the active run intact.
- No-active behavior: initializes a run directly and creates no empty archive.
- Plain language: this is the only safe way to start over; old history is preserved.

## Inspecting state

### `status`

Purpose: show the active run, simulation time, pending actions, routes, assignments, parcel
counts, and latest historical event.

```powershell
uv run courier-sim status
```

- Options: none.
- Changes state: no.
- Creates events: no.
- Files: reads and validates all three active files.
- Common errors: no active run or malformed/inconsistent persistence.
- Plain language: this is the best first command for seeing the whole operation at a glance.

### `time`

Purpose: show only the full current simulation datetime.

```powershell
uv run courier-sim time
```

- Options: none.
- Changes state: no.
- Creates events: no.
- Files: reads and validates all three active files.
- Common errors: no active run or invalid persistence.
- Output example: `2026-03-16 11:30 Europe/Bucharest`.
- Plain language: the clock is simulated; this does not show the computer's wall clock.

### `show`

Purpose: display one current entity, including related IDs, statuses, and readable timestamps.

```powershell
uv run courier-sim show <ENTITY-TYPE> <ENTITY-ID>
uv run courier-sim show parcel P-1005-A
uv run courier-sim show shipment SHIP-002
uv run courier-sim show route ROUTE-01
uv run courier-sim show driver D-01
uv run courier-sim show vehicle VAN-01
```

- Arguments: entity type is exactly `parcel`, `shipment`, `route`, `driver`, or `vehicle`;
  entity ID is case-sensitive.
- Changes state: no.
- Creates events: no.
- Files: reads and validates all three active files.
- Common errors: unsupported entity type, unknown ID, no active run, or invalid persistence.
- Plain language: use this when the summary is not detailed enough.

## Controlling time

### `advance`

Purpose: move time forward by a positive duration and process every scheduled action reached.

```powershell
uv run courier-sim advance [--minutes INTEGER] [--hours INTEGER]
uv run courier-sim advance --minutes 30
uv run courier-sim advance --hours 2
uv run courier-sim advance --hours 1 --minutes 15
```

- Options: whole `--minutes` and `--hours`; their combined duration must be positive.
- Changes state: yes, by changing time and possibly shipment state.
- Creates events: one event per processed scheduled arrival and one `TIME_ADVANCED` event.
- Files: reads all active files, appends new events, and writes snapshot and metadata.
- Common rejection: zero/negative total movement, a scheduled transition that is no longer
  legal, no active run, or invalid persistence.
- Plain language: all due future work is executed in deterministic timestamp order. Durations
  represent elapsed time and remain stable across Romanian daylight-saving changes.

### `run-until`

Purpose: advance directly to a specified future datetime.

```powershell
uv run courier-sim run-until --datetime "YYYY-MM-DD HH:MM"
uv run courier-sim run-until --datetime "2026-03-16 17:00"
uv run courier-sim run-until --datetime "2026-03-16T17:00:00+02:00"
```

- Required option: `--datetime`. ISO date/time forms accepted by Python are supported. Input
  without an offset is interpreted as `Europe/Bucharest`; aware input is converted there.
- Changes state: yes.
- Creates events: scheduled-arrival events plus `TIME_ADVANCED`.
- Files: reads all active files, appends events, and writes snapshot and metadata.
- Common rejection: malformed input or a target equal to/earlier than current simulation time.
- Plain language: use this when the destination time matters more than the duration.

### `next-event`

Purpose: advance to and process the earliest pending scheduled action. The name refers to the
next future action; the facts it produces are historical events.

```powershell
uv run courier-sim next-event
```

- Options: none.
- Changes state: yes when an action is pending; no when the queue is empty.
- Creates events: the scheduled shipment transition and `TIME_ADVANCED` when processed.
- Files: reads all active files; writes only when an action is processed.
- Common errors: an invalid scheduled transition or malformed persistence. An empty queue is
  reported as a normal no-op.
- Plain language: this is a one-step way to jump to the next planned occurrence.

## Changing logistics state

### `parcel-transition`

Purpose: request exactly one validated parcel lifecycle edge.

```powershell
uv run courier-sim parcel-transition <PARCEL-ID> <STATUS>
uv run courier-sim parcel-transition P-1005-A RECEIVED
uv run courier-sim parcel-transition P-1005-A SCANNED
```

- Arguments: a case-sensitive parcel ID and one `ParcelStatus` value. Run
  `parcel-transition --help` to see all accepted values.
- Changes state: yes on success.
- Creates events: one `PARCEL_STATUS_CHANGED`.
- Files: reads all active files, appends the event, and writes snapshot and metadata.
- Conditional behavior: delivery method must match the completion state; loading requires an
  assigned route; out-for-delivery requires an in-progress route; locker collection requires a
  prior locker deposit. Home/locker delivery sets confirmation time to current simulation time.
- Common rejection: unknown parcel, skipped lifecycle state, wrong delivery method, absent
  route assignment, route not started, or terminal current state.
- Plain language: the engine never fills skipped parcel steps automatically.

### `shipment-transition`

Purpose: request exactly one validated inbound-shipment lifecycle edge.

```powershell
uv run courier-sim shipment-transition <SHIPMENT-ID> <STATUS>
uv run courier-sim shipment-transition SHIP-002 ARRIVED
uv run courier-sim shipment-transition SHIP-002 RECEIVING
```

- Arguments: a case-sensitive shipment ID and one `InboundShipmentStatus` value.
- Changes state: yes on success.
- Creates events: one `SHIPMENT_STATUS_CHANGED`.
- Files: reads all active files, appends the event, and writes snapshot and metadata.
- Behavior: arrival records current simulation time as actual arrival and consumes a matching
  pending arrival action. Marking the shipment `MISSING` also removes that now-impossible
  arrival. Early actual arrival is valid. Parcel warehouse statuses do not advance
  automatically.
- Common rejection: unknown shipment or a requested state not allowed from its current state.
- Plain language: shipment and parcel processing stay separate and explicit.

## Managing routes

### `assign-route`

Purpose: assign one available driver and vehicle to a planned route.

```powershell
uv run courier-sim assign-route <ROUTE-ID> --driver <DRIVER-ID> --vehicle <VEHICLE-ID>
uv run courier-sim assign-route ROUTE-03 --driver D-03 --vehicle VAN-03
```

- Required arguments/options: route ID, `--driver`, and `--vehicle`.
- Changes state: yes; all driver, vehicle, route, and historical links are set together.
- Creates events: one `ROUTE_ASSIGNED`.
- Files: reads all active files, appends the event, and writes snapshot and metadata.
- Validation: planned route, available unassigned driver and vehicle, active driver shift,
  driver workload limits, and vehicle parcel/weight capacity.
- Common rejection: conflicting assignment, non-planned route, unavailable entity, unknown ID,
  or capacity/workload excess.
- Plain language: assignment is bidirectional, so no entity can silently disagree.

### `start-route`

Purpose: start a correctly assigned route at current simulation time.

```powershell
uv run courier-sim start-route <ROUTE-ID>
uv run courier-sim start-route ROUTE-02
```

- Arguments: route ID.
- Changes state: yes; status becomes `IN_PROGRESS`, `started_at` is set, and the vehicle becomes
  `IN_SERVICE`.
- Creates events: one `ROUTE_STARTED`.
- Files: reads all active files, appends the event, and writes snapshot and metadata.
- Common rejection: route is not assigned, assignments disagree, driver/vehicle is missing,
  or the route was already started.
- Plain language: `started_at` is a full historical datetime, not only a clock time.

### `complete-route`

Purpose: finish an in-progress route after every planned parcel has an explicit outcome.

```powershell
uv run courier-sim complete-route <ROUTE-ID>
uv run courier-sim complete-route ROUTE-01
```

- Arguments: route ID.
- Changes state: yes; records `completed_at`, derives/stores the outcome summary, clears current
  assignments, makes the vehicle available, and makes the driver available or off duty as
  appropriate for the shift.
- Creates events: one `ROUTE_COMPLETED` containing the derived summary.
- Files: reads all active files, appends the event, and writes snapshot and metadata.
- Resolved outcomes: delivered home, delivered locker/collected, failed, returned to warehouse,
  damage review, returned to sender, or cancelled. Success for every parcel is not required.
- Common rejection: route not started, completion time not after start, missing assignment, or
  any unresolved parcel.
- Plain language: current links are released, while historical driver and vehicle IDs remain
  on the completed route.

## Inspecting history

### `events`

Purpose: display append-only historical events without changing them.

```powershell
uv run courier-sim events
uv run courier-sim events --limit 20
uv run courier-sim events --entity-id P-1006-A
uv run courier-sim events --event-type PARCEL_STATUS_CHANGED
uv run courier-sim events --limit 5 --entity-id ROUTE-01
```

- Options: positive `--limit`; `--entity-id` matches primary or related entities;
  `--event-type` accepts one event type shown by `events --help`. Filters may be combined.
- Changes state: no.
- Creates events: no.
- Files: reads and validates all three active files.
- Common errors: non-positive limit, invalid event type, no active run, malformed JSONL,
  duplicate/nonsequential event IDs, or mixed run IDs.
- Plain language: this is operational memory; viewing it never rewrites history.

## Validating files

### `validate`

Purpose: validate the complete active persistence set and its domain relationships.

```powershell
uv run courier-sim validate
```

- Options: none.
- Changes state: no.
- Creates events: no.
- Files: reads `current_state.json`, every JSONL line, and `run_metadata.json`.
- Checks: valid JSON/models, run ID and seed agreement, active metadata, timezone-aware state,
  unique sequential event IDs, chronological order, next sequence, final event ID, scheduled
  actions, and driver/vehicle/route relationships.
- Common errors: missing file, malformed JSON/JSONL, inconsistent metadata, duplicate or
  nonsequential IDs, mixed histories, or invalid domain links.
- Plain language: run this after manual inspection or before trusting a saved simulation.

## Coherent sample route flow

The fixed scenario includes planned `ROUTE-03`, available `D-03`/`VAN-03`, and expected parcel
`P-1005-A`. This sequence exercises the ordinary route path:

```powershell
uv run courier-sim assign-route ROUTE-03 --driver D-03 --vehicle VAN-03
uv run courier-sim parcel-transition P-1005-A RECEIVED
uv run courier-sim parcel-transition P-1005-A SCANNED
uv run courier-sim parcel-transition P-1005-A SORTED
uv run courier-sim parcel-transition P-1005-A STAGED_FOR_ROUTE
uv run courier-sim parcel-transition P-1005-A LOADED
uv run courier-sim start-route ROUTE-03
uv run courier-sim parcel-transition P-1005-A OUT_FOR_DELIVERY
uv run courier-sim parcel-transition P-1005-A DELIVERED_TO_HOME
uv run courier-sim advance --minutes 1
uv run courier-sim complete-route ROUTE-03
uv run courier-sim show route ROUTE-03
```
