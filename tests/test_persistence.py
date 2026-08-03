import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from courier_sim.domain.enums import ParcelStatus, RouteStatus
from courier_sim.domain.transitions import TransitionError
from courier_sim.engine.commands import (
    AdvanceTimeCommand,
    CompleteRouteCommand,
    ParcelTransitionCommand,
)
from courier_sim.engine.models import CommandResult, WorldState
from courier_sim.engine.processor import CommandProcessor
from courier_sim.persistence import repository as repository_module
from courier_sim.persistence.repository import (
    ActiveSimulationExistsError,
    EndReason,
    PersistenceError,
    RunMetadata,
    RunStatus,
    SimulationRepository,
)


def test_initialize_creates_three_active_files_and_history(tmp_path) -> None:
    repository = SimulationRepository(tmp_path / ".simulation")
    loaded = repository.initialize(42)

    assert loaded.state.simulation_run_id == "RUN-20260316-001"
    assert loaded.events[0].event_id == "EVT-000001"
    assert repository.history_directory.is_dir()
    assert {path.name for path in repository.active_directory.iterdir()} == {
        "current_state.json",
        "events.jsonl",
        "run_metadata.json",
    }


def test_init_refuses_to_overwrite_an_active_run(tmp_path) -> None:
    repository = SimulationRepository(tmp_path / ".simulation")
    repository.initialize(42)

    with pytest.raises(ActiveSimulationExistsError, match="reset"):
        repository.initialize(73)


def test_complete_round_trip_preserves_full_world_and_history(tmp_path) -> None:
    repository = SimulationRepository(tmp_path / ".simulation")
    initial = repository.initialize(42)
    processor = CommandProcessor(initial.state)
    advanced = processor.execute(AdvanceTimeCommand(timedelta(hours=1)))
    repository.commit(advanced)
    transitioned = processor.execute(ParcelTransitionCommand("P-1006-A", ParcelStatus.SCANNED))
    repository.commit(transitioned)
    completed = processor.execute(CompleteRouteCommand("ROUTE-01"))
    saved = repository.commit(completed)

    del initial, processor, advanced, transitioned, completed
    reloaded = SimulationRepository(tmp_path / ".simulation").load()

    assert reloaded.state == saved.state
    assert reloaded.events == saved.events
    assert reloaded.state.current_datetime.hour == 12
    assert not reloaded.state.scheduled_actions
    parcel = next(item for item in reloaded.state.scenario.parcels if item.parcel_id == "P-1006-A")
    route = next(item for item in reloaded.state.scenario.routes if item.route_id == "ROUTE-01")
    driver = next(item for item in reloaded.state.scenario.drivers if item.driver_id == "D-01")
    vehicle = next(item for item in reloaded.state.scenario.vehicles if item.vehicle_id == "VAN-01")
    assert parcel.status is ParcelStatus.SCANNED
    assert route.status is RouteStatus.COMPLETED
    assert route.started_at is not None and route.completed_at is not None
    assert route.historical_driver_id == "D-01"
    assert driver.current_route_id is None
    assert vehicle.current_driver_id is None


def test_event_sequence_continues_after_reload(tmp_path) -> None:
    repository = SimulationRepository(tmp_path / ".simulation")
    loaded = repository.initialize(42)
    first = CommandProcessor(loaded.state).execute(
        ParcelTransitionCommand("P-1006-A", ParcelStatus.SCANNED)
    )
    repository.commit(first)

    reloaded = SimulationRepository(tmp_path / ".simulation").load()
    second = CommandProcessor(reloaded.state).execute(
        ParcelTransitionCommand("P-1006-A", ParcelStatus.SORTED)
    )
    final = repository.commit(second)

    assert second.events[0].event_id == "EVT-000003"
    assert [event.event_id for event in final.events] == [
        "EVT-000001",
        "EVT-000002",
        "EVT-000003",
    ]


def test_repeated_saves_do_not_duplicate_or_rewrite_events(tmp_path) -> None:
    repository = SimulationRepository(tmp_path / ".simulation")
    loaded = repository.initialize(42)
    events_path = repository.active_directory / "events.jsonl"
    before = events_path.read_bytes()

    unchanged = CommandResult(state=loaded.state, events=())
    repository.commit(unchanged)
    repository.commit(unchanged)

    assert events_path.read_bytes() == before
    assert len(repository.load().events) == 1


def test_recommitting_the_same_event_is_rejected_as_a_duplicate(tmp_path) -> None:
    repository = SimulationRepository(tmp_path / ".simulation")
    loaded = repository.initialize(42)
    result = CommandProcessor(loaded.state).execute(
        ParcelTransitionCommand("P-1006-A", ParcelStatus.SCANNED)
    )
    repository.commit(result)

    with pytest.raises(PersistenceError, match="expected continuation"):
        repository.commit(result)

    assert len(repository.load().events) == 2


def test_append_only_history_preserves_existing_lines(tmp_path) -> None:
    repository = SimulationRepository(tmp_path / ".simulation")
    loaded = repository.initialize(42)
    events_path = repository.active_directory / "events.jsonl"
    first_line = events_path.read_text(encoding="utf-8")
    result = CommandProcessor(loaded.state).execute(
        ParcelTransitionCommand("P-1006-A", ParcelStatus.SCANNED)
    )
    repository.commit(result)

    after = events_path.read_text(encoding="utf-8")
    assert after.startswith(first_line)
    assert after.count("\n") == 2


def test_invalid_command_leaves_all_persisted_files_unchanged(tmp_path) -> None:
    repository = SimulationRepository(tmp_path / ".simulation")
    loaded = repository.initialize(42)
    before = {path.name: path.read_bytes() for path in repository.active_directory.iterdir()}

    with pytest.raises(TransitionError):
        CommandProcessor(loaded.state).execute(
            ParcelTransitionCommand("P-1005-A", ParcelStatus.OUT_FOR_DELIVERY)
        )

    after = {path.name: path.read_bytes() for path in repository.active_directory.iterdir()}
    assert after == before
    repository.validate()


def test_invalid_current_state_json_is_reported(tmp_path) -> None:
    repository = SimulationRepository(tmp_path / ".simulation")
    repository.initialize(42)
    (repository.active_directory / "current_state.json").write_text(
        "{not-json",
        encoding="utf-8",
    )

    with pytest.raises(PersistenceError, match="invalid current-state snapshot"):
        repository.load()


def test_malformed_jsonl_line_is_reported(tmp_path) -> None:
    repository = SimulationRepository(tmp_path / ".simulation")
    repository.initialize(42)
    with (repository.active_directory / "events.jsonl").open(
        "a",
        encoding="utf-8",
    ) as handle:
        handle.write("not-json\n")

    with pytest.raises(PersistenceError, match="line 2"):
        repository.load()


def test_inconsistent_metadata_is_reported(tmp_path) -> None:
    repository = SimulationRepository(tmp_path / ".simulation")
    repository.initialize(42)
    path = repository.active_directory / "run_metadata.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["seed"] = 73
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(PersistenceError, match="seed disagrees"):
        repository.load()


def test_reset_same_seed_archives_complete_run_and_starts_fresh_history(tmp_path) -> None:
    repository = SimulationRepository(tmp_path / ".simulation")
    loaded = repository.initialize(42)
    result = CommandProcessor(loaded.state).execute(AdvanceTimeCommand(timedelta(hours=1)))
    old = repository.commit(result)
    old_event_bytes = (repository.active_directory / "events.jsonl").read_bytes()

    reset = repository.reset(42, force=True)
    archive = reset.archive_directory
    archived = SimulationRepository(tmp_path / ".simulation")._load_directory(
        archive,
        expected_status=RunStatus.ARCHIVED,
    )

    assert reset.archived_run_id == "RUN-20260316-001"
    assert reset.active.state.simulation_run_id == "RUN-20260316-002"
    assert reset.active.state.scenario_seed == 42
    assert [event.event_id for event in reset.active.events] == ["EVT-000001"]
    assert (archive / "events.jsonl").read_bytes() == old_event_bytes
    assert archived.state == old.state
    assert archived.events == old.events
    assert archived.metadata.end_reason is EndReason.FORCE_RESET
    assert archived.metadata.archived_at is not None
    assert archived.metadata.archived_at.utcoffset() == timedelta(0)
    assert archived.metadata.archived_at <= datetime.now(UTC)
    assert archived.metadata.archived_at != old.state.current_datetime


def test_reset_different_seed_keeps_histories_separate(tmp_path) -> None:
    repository = SimulationRepository(tmp_path / ".simulation")
    repository.initialize(42)
    second = repository.reset(42, force=True)
    third = repository.reset(73, force=True)

    second_metadata = RunMetadata.model_validate_json(
        (
            repository.history_directory
            / second.active.state.simulation_run_id
            / "run_metadata.json"
        ).read_text(encoding="utf-8")
    )
    assert third.active.state.simulation_run_id == "RUN-20260316-003"
    assert third.active.state.scenario_seed == 73
    assert second_metadata.end_reason is EndReason.NEW_SEED
    assert len(third.active.events) == 1


def test_reset_without_force_is_rejected_and_active_is_intact(tmp_path) -> None:
    repository = SimulationRepository(tmp_path / ".simulation")
    original = repository.initialize(42)

    with pytest.raises(PersistenceError, match="--force"):
        repository.reset(42, force=False)

    assert repository.load() == original


def test_archive_failure_leaves_active_run_intact(tmp_path, monkeypatch) -> None:
    repository = SimulationRepository(tmp_path / ".simulation")
    original = repository.initialize(42)

    def fail_copy(*args, **kwargs):
        raise OSError("controlled archive failure")

    monkeypatch.setattr(repository, "_copy_archive", fail_copy)
    with pytest.raises(PersistenceError, match="active run was preserved"):
        repository.reset(73, force=True)

    assert repository.load() == original
    assert not list(repository.history_directory.iterdir())


def test_reset_without_active_initializes_without_empty_archive(tmp_path) -> None:
    repository = SimulationRepository(tmp_path / ".simulation")
    result = repository.reset(73, force=False)

    assert result.archived_run_id is None
    assert result.active.state.scenario_seed == 73
    assert not list(repository.history_directory.iterdir())


def test_direct_state_change_without_event_is_rejected(tmp_path) -> None:
    repository = SimulationRepository(tmp_path / ".simulation")
    loaded = repository.initialize(42)
    data = loaded.state.model_dump(mode="python")
    parcel = next(item for item in data["scenario"]["parcels"] if item["parcel_id"] == "P-1006-A")
    parcel["status"] = ParcelStatus.SCANNED
    edited = WorldState.model_validate(data)

    with pytest.raises(PersistenceError, match="direct snapshot mutation is forbidden"):
        repository.commit(CommandResult(state=edited, events=()))

    assert repository.load() == loaded


def test_unknown_persistence_version_is_rejected(tmp_path) -> None:
    repository = SimulationRepository(tmp_path / ".simulation")
    repository.initialize(42)
    metadata_path = repository.active_directory / "run_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["persistence_version"] = "999.0"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(PersistenceError, match="invalid run metadata"):
        repository.load()


def test_staged_commit_failure_preserves_complete_old_bundle(tmp_path, monkeypatch) -> None:
    repository = SimulationRepository(tmp_path / ".simulation")
    loaded = repository.initialize(42)
    result = CommandProcessor(loaded.state).execute(
        ParcelTransitionCommand("P-1006-A", ParcelStatus.SCANNED)
    )
    original_write_model = SimulationRepository._write_model

    def fail_staged_metadata(path, model):
        if path.name == "run_metadata.json" and path.parent.name.startswith(".commit-"):
            raise OSError("controlled staged metadata failure")
        return original_write_model(path, model)

    monkeypatch.setattr(
        SimulationRepository,
        "_write_model",
        staticmethod(fail_staged_metadata),
    )

    with pytest.raises(PersistenceError, match="could not persist command atomically"):
        repository.commit(result)

    assert repository.load() == loaded
    assert not list(repository.root.glob(".commit-*.tmp"))


def test_commit_publication_failure_restores_complete_old_bundle(tmp_path, monkeypatch) -> None:
    repository = SimulationRepository(tmp_path / ".simulation")
    loaded = repository.initialize(42)
    result = CommandProcessor(loaded.state).execute(
        ParcelTransitionCommand("P-1006-A", ParcelStatus.SCANNED)
    )
    original_replace = Path.replace

    def fail_new_active_publication(path, target):
        is_staged_commit = path.name.startswith(".commit-") and not path.name.startswith(
            ".commit-backup-"
        )
        if is_staged_commit and Path(target) == repository.active_directory:
            raise OSError("controlled active publication failure")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_new_active_publication)

    with pytest.raises(PersistenceError, match="could not persist command atomically"):
        repository.commit(result)

    assert repository.load() == loaded
    assert not list(repository.root.glob(".commit-*.tmp"))
    assert not list(repository.root.glob(".commit-backup-*.tmp"))


def test_reset_backup_cleanup_failure_keeps_new_run_and_archive(
    tmp_path,
    monkeypatch,
) -> None:
    repository = SimulationRepository(tmp_path / ".simulation")
    original = repository.initialize(42)
    original_rmtree = repository_module.shutil.rmtree

    def fail_only_redundant_backup(path, *args, **kwargs):
        if Path(path).name.startswith(".old-active-"):
            raise OSError("controlled redundant-backup cleanup failure")
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(repository_module.shutil, "rmtree", fail_only_redundant_backup)

    with pytest.warns(RuntimeWarning, match="reset succeeded"):
        reset = repository.reset(73, force=True)

    assert reset.active.state.simulation_run_id != original.state.simulation_run_id
    assert repository.load().state.scenario_seed == 73
    assert reset.archive_directory.is_dir()
    archived = repository._load_directory(
        reset.archive_directory,
        expected_status=RunStatus.ARCHIVED,
    )
    assert archived.state == original.state
    assert list(repository.root.glob(".old-active-*.tmp"))
