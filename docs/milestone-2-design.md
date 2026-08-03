# Milestone 2 technical design

## Goals

Milestone 2 turns the static fictional Bucharest logistics model into a deterministic,
locally controlled simulation. It adds validated commands, explicit time control, scheduled
shipment arrivals, immutable operational history, route execution, and reloadable JSON/JSONL
persistence.

## Architecture

```text
PowerShell CLI
      |
      v
Typed command -> CommandProcessor
                       |
                       +-> central transition maps
                       +-> conditional business rules
                       +-> SimulationClock / pending actions
                       +-> working copy of WorldState
                       `-> EventRecorder
                                |
                                v
                    SimulationRepository
                       |       |       |
                       v       v       v
                  state JSON  event   run metadata
                              JSONL      JSON
```

The command processor has no filesystem responsibility. The repository does not decide
business transitions. The CLI only translates input and presents results.

## Module responsibilities

- `domain/enums.py` and `domain/models.py`: logistics entities, lifecycle enums, route
  timestamps, historical assignments, and outcome summaries.
- `domain/transitions.py`: central parcel, shipment, and route maps plus conditional parcel
  rules.
- `engine/clock.py`: timezone-aware forward-only clock behavior and CLI datetime parsing.
- `engine/commands.py`: the finite set of typed state-changing requests.
- `engine/events.py`: deterministic event allocation using `EVT-000001` sequences.
- `engine/models.py`: `WorldState`, pending scheduled actions, and immutable events.
- `engine/processor.py`: atomic validation, mutation of a working copy, event creation,
  scheduled-action execution, and route behavior.
- `engine/state.py`: deterministic initial scenario and the narrow initial shipment-arrival
  schedule.
- `persistence/repository.py`: active-run load/save, atomic snapshots, JSONL append,
  consistency checks, run IDs, and safe archives.
- `cli/app.py`: PowerShell-oriented argument parsing, error handling, and readable output.

## Command-processing flow

1. Load and validate all active persistence files.
2. Create a deep working copy of `WorldState`.
3. Dispatch a typed command.
4. Validate map-level and conditional rules before replacing an entity.
5. Allocate immutable events from the working state's next sequence.
6. Revalidate the complete world and all cross-entity links.
7. Return the new state and only the new events.
8. Copy the prior event bytes into a staged active bundle and append only the new events.
9. Validate the staged state, metadata, and complete history together.
10. Swap the staged directory into place with a recoverable backup.

An exception before step 7 leaves the processor's original state unchanged. A persistence
failure before publication restores the complete old active directory. Cleanup failure after
publication does not undo a successful commit; it leaves only a redundant warning-labelled
backup for later removal.

## Transition-validation flow

```text
requested status
      |
      v
central map permits edge? -- no --> reject with current and allowed states
      |
     yes
      |
      v
conditional rules pass?  -- no --> reject with the specific reason
      |
     yes
      |
      v
build and validate replacement entity
```

Parcel completion checks the delivery method. Loading requires an assigned route, and
out-for-delivery requires that route to be in progress. Locker collection preserves the
original courier confirmation timestamp and records a later or equal `collected_at`.

## Clock and scheduled-action flow

The simulation starts at `2026-03-16 11:00 Europe/Bucharest`. The clock moves only through an
explicit `advance`, `run-until`, or `next-event` command. During an advance, due actions are
sorted by execution datetime, creation sequence, then action ID. The processor temporarily
moves to each action timestamp, executes the shipment transition through the same validated
logic used by a manual command, records the event, and finally moves to the requested target.
A manual arrival consumes its matching pending arrival so the action cannot execute twice.
A terminal `MISSING` transition also consumes that now-impossible arrival. Duration advances
use UTC elapsed-time arithmetic and return to the Bucharest zone, producing identical results
before and after persistence across daylight-saving boundaries.

## Persistence flow

Normal commands validate `current_state.json`, `events.jsonl`, and `run_metadata.json`.
The repository creates a complete staged directory, preserves all prior JSONL bytes, appends
new lines there, and validates the complete bundle before publishing it. This prevents a
partially replaced snapshot or metadata file from becoming visible.

Reset first prepares and validates a complete archive and a complete replacement active run.
It then publishes the archive and swaps the active directory. A failure before the publication
commit point restores the old run. A redundant-backup cleanup failure after publication leaves
the new active run and archive intact and emits a warning instead of performing a false rollback.

## Route-completion flow

Completion requires an in-progress route, a start time earlier than current simulation time,
truthful active assignments, and an explicit outcome for every parcel. A stop counts as
completed when all of its parcels have resolved route outcomes. The processor derives the
summary, records completion, retains historical driver/vehicle IDs, clears current links,
and makes the driver and vehicle available.

## Event-ID design

Each run begins at `EVT-000001`. `WorldState.next_event_sequence` is persisted, and loading
requires it to equal the JSONL event count plus one. IDs must be unique and exactly sequential.
The globally meaningful identity is the pair `(simulation_run_id, event_id)`.

Run IDs use `RUN-<initial-simulation-date>-<sequence>`, for example
`RUN-20260316-002`. The sequence is derived from active and archived run directories.

## Important invariants

- No CLI state mutation bypasses `CommandProcessor`.
- Time never moves backward.
- Datetimes are timezone-aware; CLI output names `Europe/Bucharest`.
- Driver, vehicle, and active-route links agree in every direction.
- Completed routes have no current links and retain historical links.
- Failed commands create no success events.
- Existing JSONL lines never change during a successful normal command.
- State run ID, metadata run ID, and every event run ID agree.
- State and metadata use the supported persistence format version.
- Event IDs are unique and sequential after every reload.
- Event metadata cannot be mutated through nested dictionaries or lists.
- A new run never inherits events from an older run.
- Driver and vehicle availability statuses agree with active route links.
- Direct state changes without command-generated events cannot be committed.

## Out of scope

There is no AI or OpenAI API use, memory retrieval, vector database, route optimization,
mapping, real or random traffic, vehicle breakdown simulation, automatic customer behavior,
message sending, web/API server, database, Docker, authentication, cloud deployment, or
graphical interface.
