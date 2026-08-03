# Project instructions

These instructions apply permanently to work in this repository.

- Develop the project incrementally and complete only the requested milestone.
- Keep every milestone small and testable.
- Separate domain logic from storage, user interfaces, AI, and external services.
- Do not invent business rules when requirements are already specified.
- Use deterministic test data where possible.
- Add tests for every meaningful validation rule.
- Prefer readable code over clever abstractions.
- Avoid premature optimization and unnecessary dependencies.
- Do not implement future milestones unless explicitly requested.
- Explain the resulting structure clearly when work is finished.
- Use Python 3.12, `uv`, Pydantic 2, pytest, Ruff, and a `src` package layout.
- Keep all sample people, organizations, addresses, and infrastructure fictional.
- Do not require paid services, API keys, or network access.
- Route every state change through the command processor; user interfaces and future agents
  must not mutate domain objects directly.
- Define status changes in central transition maps and enforce conditional business validation.
- Reject illegal transitions without partial in-memory or persisted mutation.
- Treat event history as append-only and give every event a unique, immutable event ID.
- Treat structured event metadata as deeply immutable, not merely protected from field
  reassignment.
- Store current state and historical events in separate JSON and JSONL files.
- Publish persistence changes only after staging and validating a complete replacement bundle;
  never expose state, metadata, and history from different commits.
- Reject direct snapshot changes that do not include command-generated events.
- Require the state and run metadata persistence versions to match the supported format.
- Keep simulation time timezone-aware, explicitly controlled, and independent of wall-clock time.
- Interpret duration advances as elapsed time using UTC arithmetic, then convert back to
  `Europe/Bucharest`, so daylight-saving changes behave identically after reload.
- Cancel scheduled actions when an approved terminal transition makes them impossible.
- Keep current driver and vehicle assignment fields truthful and mutually consistent.
- Keep driver and vehicle availability statuses consistent with their current route links and
  recheck shift eligibility when a route starts.
- Clear current assignments when a route completes while retaining its historical driver and
  vehicle links.
- Keep administrative filesystem timestamps, such as archive time, distinct from simulation
  datetimes.
- Display user-facing CLI timestamps with their full date and `Europe/Bucharest`.
- Introduce no paid or network service without explicit approval.
- Future milestones must use, not bypass, the simulation engine and command processor.

Before completing a milestone, run:

```powershell
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
