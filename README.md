# Courier Logistics Digital Twin

Courier Logistics Digital Twin is a university-level Python project for a fictional regional
parcel courier serving Bucharest, Romania. Milestone 2 provides a deterministic local
simulation foundation for later operational-memory and AI-supervision work.

All sample people, merchants, addresses, lockers, and infrastructure are fictional.
Coordinates are plausible points only and do not identify real customers or courier assets.

## Milestone 2 capabilities

- timezone-aware, forward-only simulation time in `Europe/Bucharest`;
- strict parcel, shipment, and route transition maps with conditional rules;
- one safe command-processing interface for every state change;
- scheduled inbound-shipment arrivals with stable same-time ordering;
- immutable `EVT-000001`-style event records;
- route assignment, start, completion, historical links, and derived outcome summaries;
- reloadable active state in JSON and append-only event history in JSONL;
- separately archived simulation runs and safe seed resets;
- staged whole-bundle persistence publication with rollback before the commit point;
- DST-stable elapsed-time controls and deeply immutable event metadata;
- a PowerShell-friendly `courier-sim` command;
- persistence, corruption, archive, engine, domain, and CLI tests.

Simulation use is entirely local. It needs no paid service, API key, network request, server,
GPU, database, or subscription beyond the development tools already in use.

## Prerequisites and setup

- Python 3.12
- [`uv`](https://docs.astral.sh/uv/)
- Windows PowerShell

From the repository root:

```powershell
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run python -m courier_sim.demo
```

## Start and inspect a simulation

```powershell
uv run courier-sim init --seed 42
uv run courier-sim status
uv run courier-sim time
```

The default files are:

```text
.simulation/
|-- active/
|   |-- current_state.json
|   |-- events.jsonl
|   `-- run_metadata.json
`-- history/
```

Use `--simulation-dir <PATH>` before the command, or set `COURIER_SIM_DIR`, to use a separate
test directory.

## Control time and inspect history

```powershell
uv run courier-sim advance --minutes 30
uv run courier-sim run-until --datetime "2026-03-16 17:00"
uv run courier-sim next-event
uv run courier-sim events --limit 20
uv run courier-sim validate
```

Naive CLI datetimes are interpreted in `Europe/Bucharest`; timezone-aware ISO input is
converted to Bucharest time. Every later PowerShell command reloads the state written by the
previous command.

## Safe reset

`init` refuses to overwrite an active run. Archive it before starting another:

```powershell
uv run courier-sim reset --seed 73 --force
```

The old snapshot, event history, and metadata are preserved under
`.simulation/history/<simulation_run_id>/`. The new run receives a new run ID, fresh JSONL
history, and an event sequence beginning at `EVT-000001`.

`archived_at` is an administrative UTC timestamp recording when the filesystem archive was
created. It is intentionally distinct from the run's final simulation datetime.

## Milestone 2 seed behavior

The selected seed is persisted and separates experimental runs, but the current educational
Bucharest sample still uses fixed entities and coordinates. Seeds `42` and `73` therefore
create separate run identities and histories while starting with the same scenario contents.
Procedural seeded scenario variation is reserved for a later milestone.

## Documentation

- [Milestone 2 technical design](docs/milestone-2-design.md)
- [Complete simulation command reference](docs/simulation-controls.md)
- [Locked domain decisions](docs/domain-decisions.md)

## Package structure

```text
src/courier_sim/
|-- cli/
|   `-- app.py
|-- domain/
|   |-- enums.py
|   |-- models.py
|   `-- transitions.py
|-- engine/
|   |-- clock.py
|   |-- commands.py
|   |-- events.py
|   |-- models.py
|   |-- processor.py
|   `-- state.py
|-- persistence/
|   `-- repository.py
|-- sample_data/
|   `-- bucharest.py
`-- demo.py
```

## Out of scope

Milestone 2 does not implement AI agents or APIs, memory retrieval, route optimization, real
maps or traffic, random breakdowns, customer behavior, automatic messages, a web dashboard,
FastAPI, SQL storage, Docker, cloud deployment, authentication, or a graphical interface.
