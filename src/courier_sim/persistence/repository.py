"""JSON snapshot, append-only JSONL history, and safe run archives."""

from __future__ import annotations

import os
import re
import shutil
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Self
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, ValidationError, model_validator

from courier_sim.engine.commands import InitializeSimulationCommand
from courier_sim.engine.models import (
    PERSISTENCE_VERSION,
    CommandResult,
    LogisticsEvent,
    WorldState,
)
from courier_sim.engine.processor import CommandProcessor
from courier_sim.engine.state import INITIAL_SIMULATION_DATETIME, build_initial_state

AwareDateTime = Annotated[datetime, AwareDatetime]
EVENT_ID_PATTERN = re.compile(r"^EVT-(\d{6})$")
RUN_ID_PATTERN = re.compile(r"^RUN-(\d{8})-(\d{3})$")


class PersistenceError(RuntimeError):
    """Persisted simulation data is absent, malformed, or inconsistent."""


class ActiveSimulationExistsError(PersistenceError):
    """Initialization would overwrite an active run."""


class NoActiveSimulationError(PersistenceError):
    """A command requires an initialized active run."""


class RunStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class EndReason(StrEnum):
    FORCE_RESET = "FORCE_RESET"
    NEW_SEED = "NEW_SEED"
    MANUAL_ARCHIVE = "MANUAL_ARCHIVE"


class RunMetadata(BaseModel):
    """Run-level facts kept separate from the complete state snapshot."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    persistence_version: Literal["2.0"] = PERSISTENCE_VERSION
    simulation_run_id: str
    seed: int
    created_at: AwareDateTime
    initial_simulation_datetime: AwareDateTime
    current_simulation_datetime: AwareDateTime
    status: RunStatus
    archived_at: AwareDateTime | None = None
    end_reason: EndReason | None = None
    final_event_id: str | None = None

    @model_validator(mode="after")
    def archive_fields_match_status(self) -> Self:
        if self.status is RunStatus.ACTIVE:
            if self.archived_at is not None or self.end_reason is not None:
                raise ValueError("active run metadata cannot contain archive fields")
        elif self.archived_at is None or self.end_reason is None:
            raise ValueError("archived run metadata requires archive time and end reason")
        return self


@dataclass(frozen=True)
class LoadedSimulation:
    state: WorldState
    events: tuple[LogisticsEvent, ...]
    metadata: RunMetadata


@dataclass(frozen=True)
class ResetResult:
    archived_run_id: str | None
    archive_directory: Path | None
    previous_seed: int | None
    active: LoadedSimulation


class SimulationRepository:
    """Own the approved active/history directory persistence convention."""

    def __init__(self, simulation_directory: Path | str = ".simulation") -> None:
        self.root = Path(simulation_directory)
        self.active_directory = self.root / "active"
        self.history_directory = self.root / "history"

    @property
    def has_active_simulation(self) -> bool:
        return self.active_directory.exists()

    def initialize(self, seed: int) -> LoadedSimulation:
        if self.active_directory.exists():
            raise ActiveSimulationExistsError(
                "an active simulation already exists; use "
                f"'courier-sim reset --seed {seed} --force' to archive it safely"
            )
        self.root.mkdir(parents=True, exist_ok=True)
        self.history_directory.mkdir(parents=True, exist_ok=True)
        run_id = self._next_run_id()
        result = CommandProcessor(build_initial_state(run_id, seed)).execute(
            InitializeSimulationCommand()
        )
        metadata = self._active_metadata(result.state, result.events)
        temporary = self.root / f".active-{run_id}.tmp"
        if temporary.exists():
            raise PersistenceError(
                f"temporary initialization directory already exists: {temporary}"
            )
        try:
            self._write_bundle_to_directory(
                temporary,
                result.state,
                result.events,
                metadata,
            )
            temporary.replace(self.active_directory)
        except OSError as exc:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise PersistenceError(f"could not initialize active simulation: {exc}") from exc
        return LoadedSimulation(result.state, result.events, metadata)

    def load(self) -> LoadedSimulation:
        if not self.active_directory.is_dir():
            raise NoActiveSimulationError(
                "no active simulation exists; run 'courier-sim init --seed 42'"
            )
        return self._load_directory(self.active_directory, expected_status=RunStatus.ACTIVE)

    def validate(self) -> LoadedSimulation:
        """Load and fully validate active snapshot, metadata, history, and relationships."""
        return self.load()

    def commit(self, result: CommandResult) -> LoadedSimulation:
        """Append only new events and atomically replace the current snapshot."""
        loaded = self.load()
        if result.state.simulation_run_id != loaded.state.simulation_run_id:
            raise PersistenceError("command result belongs to a different simulation run")
        if result.state.scenario_seed != loaded.state.scenario_seed:
            raise PersistenceError("command result seed does not match active run metadata")
        if not result.events and result.state != loaded.state:
            raise PersistenceError(
                "state-changing commits require command-generated events; "
                "direct snapshot mutation is forbidden"
            )

        existing_count = len(loaded.events)
        expected_new_ids = [
            f"EVT-{sequence:06d}"
            for sequence in range(existing_count + 1, existing_count + len(result.events) + 1)
        ]
        actual_new_ids = [event.event_id for event in result.events]
        if actual_new_ids != expected_new_ids:
            raise PersistenceError(
                f"new event IDs are not the expected continuation: {actual_new_ids}"
            )
        if any(
            event.simulation_run_id != result.state.simulation_run_id for event in result.events
        ):
            raise PersistenceError("new event belongs to a different simulation run")
        if result.state.next_event_sequence != existing_count + len(result.events) + 1:
            raise PersistenceError("state next_event_sequence is inconsistent with event history")
        if result.events and loaded.events:
            if result.events[0].occurred_at < loaded.events[-1].occurred_at:
                raise PersistenceError("new events would violate chronological append order")

        metadata = loaded.metadata.model_copy(
            update={
                "current_simulation_datetime": result.state.current_datetime,
                "final_event_id": (
                    result.events[-1].event_id if result.events else loaded.metadata.final_event_id
                ),
            }
        )
        self._atomic_commit(result.state, result.events, metadata)
        return LoadedSimulation(
            result.state,
            (*loaded.events, *result.events),
            metadata,
        )

    def reset(self, seed: int, *, force: bool) -> ResetResult:
        if not self.active_directory.exists():
            active = self.initialize(seed)
            return ResetResult(None, None, None, active)
        if not force:
            raise PersistenceError(
                "reset refused because an active simulation exists; add --force to archive it"
            )

        old = self.load()
        reason = EndReason.FORCE_RESET if old.state.scenario_seed == seed else EndReason.NEW_SEED
        archive_target = self.history_directory / old.state.simulation_run_id
        if archive_target.exists():
            raise PersistenceError(f"archive directory already exists: {archive_target}")
        new_run_id = self._next_run_id()
        initialized = CommandProcessor(build_initial_state(new_run_id, seed)).execute(
            InitializeSimulationCommand()
        )
        new_metadata = self._active_metadata(initialized.state, initialized.events)
        archived_metadata = old.metadata.model_copy(
            update={
                "status": RunStatus.ARCHIVED,
                # Administrative archive time is intentionally independent from the
                # simulation clock and records when the filesystem archive was made.
                "archived_at": datetime.now(UTC),
                "end_reason": reason,
                "current_simulation_datetime": old.state.current_datetime,
                "final_event_id": old.events[-1].event_id if old.events else None,
            }
        )

        archive_temporary = self.history_directory / f".{old.state.simulation_run_id}.tmp"
        active_temporary = self.root / f".active-{new_run_id}.tmp"
        backup_active = self.root / f".old-active-{old.state.simulation_run_id}.tmp"
        for path in (archive_temporary, active_temporary, backup_active):
            if path.exists():
                raise PersistenceError(f"temporary reset path already exists: {path}")

        archive_published = False
        active_moved = False
        new_active_published = False
        try:
            self._copy_archive(archive_temporary, archived_metadata)
            self._load_directory(archive_temporary, expected_status=RunStatus.ARCHIVED)
            self._write_bundle_to_directory(
                active_temporary,
                initialized.state,
                initialized.events,
                new_metadata,
            )
            self._load_directory(active_temporary, expected_status=RunStatus.ACTIVE)

            self.active_directory.replace(backup_active)
            active_moved = True
            archive_temporary.replace(archive_target)
            archive_published = True
            active_temporary.replace(self.active_directory)
            new_active_published = True
        except (OSError, PersistenceError) as exc:
            recovery_errors: list[str] = []
            if active_moved and not new_active_published and backup_active.exists():
                try:
                    backup_active.replace(self.active_directory)
                    active_moved = False
                except OSError as recovery_exc:
                    recovery_errors.append(f"could not restore active backup: {recovery_exc}")
            if archive_published and not new_active_published and archive_target.exists():
                try:
                    shutil.rmtree(archive_target)
                except OSError as recovery_exc:
                    recovery_errors.append(f"could not remove partial archive: {recovery_exc}")
            for path in (archive_temporary, active_temporary):
                if path.exists():
                    try:
                        shutil.rmtree(path)
                    except OSError as recovery_exc:
                        recovery_errors.append(
                            f"could not remove temporary path {path}: {recovery_exc}"
                        )
            recovery_note = (
                f" Recovery issues: {'; '.join(recovery_errors)}" if recovery_errors else ""
            )
            raise PersistenceError(
                f"reset archive failed before publication; active run was preserved: {exc}."
                f"{recovery_note}"
            ) from exc

        # Publication is complete once both the archive and replacement active directory
        # exist. Failure to remove the redundant backup must not undo that successful reset.
        if backup_active.exists():
            try:
                shutil.rmtree(backup_active)
            except OSError as exc:
                warnings.warn(
                    f"reset succeeded, but redundant backup cleanup failed at "
                    f"{backup_active}: {exc}",
                    RuntimeWarning,
                    stacklevel=2,
                )

        return ResetResult(
            archived_run_id=old.state.simulation_run_id,
            archive_directory=archive_target,
            previous_seed=old.state.scenario_seed,
            active=LoadedSimulation(initialized.state, initialized.events, new_metadata),
        )

    def _atomic_commit(
        self,
        state: WorldState,
        new_events: tuple[LogisticsEvent, ...],
        metadata: RunMetadata,
    ) -> None:
        token = uuid4().hex
        staged = self.root / f".commit-{state.simulation_run_id}-{token}.tmp"
        backup = self.root / f".commit-backup-{state.simulation_run_id}-{token}.tmp"
        if staged.exists() or backup.exists():  # practically impossible, but never overwrite
            raise PersistenceError("temporary commit path already exists")
        active_moved = False
        new_active_published = False
        try:
            staged.mkdir(parents=False)
            self._write_model(staged / "current_state.json", state)
            self._write_model(staged / "run_metadata.json", metadata)
            source_events = self.active_directory / "events.jsonl"
            staged_events = staged / "events.jsonl"
            shutil.copy2(source_events, staged_events)
            if new_events:
                with staged_events.open("a", encoding="utf-8", newline="\n") as handle:
                    for event in new_events:
                        handle.write(event.model_dump_json())
                        handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            original_event_bytes = source_events.read_bytes()
            if not staged_events.read_bytes().startswith(original_event_bytes):
                raise PersistenceError("staged event history changed existing append-only bytes")
            self._load_directory(staged, expected_status=RunStatus.ACTIVE)

            self.active_directory.replace(backup)
            active_moved = True
            staged.replace(self.active_directory)
            new_active_published = True
        except (OSError, ValidationError, PersistenceError) as exc:
            recovery_errors: list[str] = []
            if active_moved and not new_active_published and backup.exists():
                try:
                    backup.replace(self.active_directory)
                    active_moved = False
                except OSError as recovery_exc:
                    recovery_errors.append(f"could not restore active backup: {recovery_exc}")
            if staged.exists():
                try:
                    shutil.rmtree(staged)
                except OSError as recovery_exc:
                    recovery_errors.append(f"could not remove staged commit: {recovery_exc}")
            recovery_note = (
                f" Recovery issues: {'; '.join(recovery_errors)}" if recovery_errors else ""
            )
            raise PersistenceError(
                f"could not persist command atomically: {exc}.{recovery_note}"
            ) from exc

        if backup.exists():
            try:
                shutil.rmtree(backup)
            except OSError as exc:
                warnings.warn(
                    f"commit succeeded, but redundant backup cleanup failed at {backup}: {exc}",
                    RuntimeWarning,
                    stacklevel=2,
                )

    def _copy_archive(self, destination: Path, metadata: RunMetadata) -> None:
        destination.mkdir(parents=False)
        for filename in ("current_state.json", "events.jsonl"):
            shutil.copy2(self.active_directory / filename, destination / filename)
        self._write_model(destination / "run_metadata.json", metadata)

    def _load_directory(
        self,
        directory: Path,
        *,
        expected_status: RunStatus,
    ) -> LoadedSimulation:
        state = self._load_model(
            directory / "current_state.json",
            WorldState,
            "current-state snapshot",
        )
        metadata = self._load_model(
            directory / "run_metadata.json",
            RunMetadata,
            "run metadata",
        )
        events = self._load_events(directory / "events.jsonl")
        self._validate_bundle(state, events, metadata, expected_status)
        return LoadedSimulation(state, events, metadata)

    @staticmethod
    def _load_model(path: Path, model_type, label: str):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise PersistenceError(f"could not read {label} at {path}: {exc}") from exc
        try:
            return model_type.model_validate_json(text)
        except ValidationError as exc:
            raise PersistenceError(f"invalid {label} at {path}: {exc}") from exc

    @staticmethod
    def _load_events(path: Path) -> tuple[LogisticsEvent, ...]:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise PersistenceError(f"could not read event history at {path}: {exc}") from exc
        events: list[LogisticsEvent] = []
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                raise PersistenceError(
                    f"malformed event history at {path}, line {line_number}: blank line"
                )
            try:
                events.append(LogisticsEvent.model_validate_json(line))
            except ValidationError as exc:
                raise PersistenceError(
                    f"malformed event history at {path}, line {line_number}: {exc}"
                ) from exc
        return tuple(events)

    @staticmethod
    def _validate_bundle(
        state: WorldState,
        events: tuple[LogisticsEvent, ...],
        metadata: RunMetadata,
        expected_status: RunStatus,
    ) -> None:
        if metadata.status is not expected_status:
            raise PersistenceError(
                f"run metadata status is {metadata.status}, expected {expected_status}"
            )
        if not (
            state.simulation_run_id
            == metadata.simulation_run_id
            == (events[0].simulation_run_id if events else state.simulation_run_id)
        ):
            raise PersistenceError("simulation run IDs disagree across persistence files")
        if any(event.simulation_run_id != state.simulation_run_id for event in events):
            raise PersistenceError("event history mixes simulation run IDs")
        if state.scenario_seed != metadata.seed:
            raise PersistenceError("scenario seed disagrees with run metadata")
        if not (state.persistence_version == metadata.persistence_version == PERSISTENCE_VERSION):
            raise PersistenceError("persistence versions disagree or are unsupported")
        if state.current_datetime != metadata.current_simulation_datetime:
            raise PersistenceError("current simulation datetime disagrees with run metadata")
        event_ids = [event.event_id for event in events]
        if len(event_ids) != len(set(event_ids)):
            raise PersistenceError("event history contains duplicate event IDs")
        for sequence, event in enumerate(events, start=1):
            match = EVENT_ID_PATTERN.fullmatch(event.event_id)
            if match is None or int(match.group(1)) != sequence:
                raise PersistenceError(
                    f"event history is not sequential at {event.event_id}; "
                    f"expected EVT-{sequence:06d}"
                )
            if sequence > 1 and event.occurred_at < events[sequence - 2].occurred_at:
                raise PersistenceError("event history is not in chronological execution order")
        if state.next_event_sequence != len(events) + 1:
            raise PersistenceError("next_event_sequence does not continue event history")
        expected_final = events[-1].event_id if events else None
        if metadata.final_event_id != expected_final:
            raise PersistenceError("run metadata final_event_id disagrees with event history")

    @staticmethod
    def _write_bundle_to_directory(
        directory: Path,
        state: WorldState,
        events: tuple[LogisticsEvent, ...],
        metadata: RunMetadata,
    ) -> None:
        directory.mkdir(parents=True)
        SimulationRepository._write_model(directory / "current_state.json", state)
        with (directory / "events.jsonl").open(
            "w",
            encoding="utf-8",
            newline="\n",
        ) as handle:
            for event in events:
                handle.write(event.model_dump_json())
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        SimulationRepository._write_model(directory / "run_metadata.json", metadata)

    @staticmethod
    def _write_model(path: Path, model: BaseModel) -> None:
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(model.model_dump_json(indent=2))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _next_run_id(self) -> str:
        date_part = INITIAL_SIMULATION_DATETIME.strftime("%Y%m%d")
        sequences: list[int] = []
        if self.history_directory.exists():
            for path in self.history_directory.iterdir():
                match = RUN_ID_PATTERN.fullmatch(path.name)
                if match is not None and match.group(1) == date_part:
                    sequences.append(int(match.group(2)))
        if self.active_directory.exists():
            try:
                metadata = self._load_model(
                    self.active_directory / "run_metadata.json",
                    RunMetadata,
                    "run metadata",
                )
            except PersistenceError:
                raise
            match = RUN_ID_PATTERN.fullmatch(metadata.simulation_run_id)
            if match is not None and match.group(1) == date_part:
                sequences.append(int(match.group(2)))
        return f"RUN-{date_part}-{max(sequences, default=0) + 1:03d}"

    @staticmethod
    def _active_metadata(
        state: WorldState,
        events: tuple[LogisticsEvent, ...],
    ) -> RunMetadata:
        return RunMetadata(
            simulation_run_id=state.simulation_run_id,
            seed=state.scenario_seed,
            created_at=state.current_datetime,
            initial_simulation_datetime=state.current_datetime,
            current_simulation_datetime=state.current_datetime,
            status=RunStatus.ACTIVE,
            final_event_id=events[-1].event_id if events else None,
        )
