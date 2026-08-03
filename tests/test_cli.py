import os
import subprocess
import sys
from pathlib import Path

import pytest

from courier_sim.cli.app import main


def run_cli(root: Path, *arguments: str) -> int:
    return main(["--simulation-dir", str(root), *arguments])


def test_help_is_useful() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "courier_sim.cli.app", "--help"],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).parents[1] / "src"),
        },
    )

    assert completed.returncode == 0
    assert "Control the local Courier Logistics Digital Twin" in completed.stdout
    assert "parcel-transition" in completed.stdout
    assert "complete-route" in completed.stdout


@pytest.mark.parametrize(
    "command",
    [
        "init",
        "status",
        "time",
        "advance",
        "run-until",
        "next-event",
        "events",
        "show",
        "parcel-transition",
        "shipment-transition",
        "assign-route",
        "start-route",
        "complete-route",
        "validate",
        "reset",
    ],
)
def test_every_command_has_help(command: str) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "courier_sim.cli.app", command, "--help"],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).parents[1] / "src"),
        },
    )

    assert completed.returncode == 0
    assert "usage: courier-sim" in completed.stdout


def test_init_status_and_time(tmp_path, capsys) -> None:
    root = tmp_path / ".simulation"
    assert run_cli(root, "init", "--seed", "42") == 0
    initialized = capsys.readouterr().out
    assert "RUN-20260316-001" in initialized

    assert run_cli(root, "status") == 0
    status = capsys.readouterr().out
    assert "Simulation time: 2026-03-16 11:00 Europe/Bucharest" in status
    assert "Entity counts:" in status
    assert "shipments: 4" in status
    assert "parcels: 10" in status
    assert "Pending scheduled actions: 1" in status
    assert "Historical events: 1" in status

    assert run_cli(root, "time") == 0
    assert capsys.readouterr().out.strip() == "2026-03-16 11:00 Europe/Bucharest"


def test_advance_run_until_and_next_event(tmp_path, capsys) -> None:
    first = tmp_path / "first"
    run_cli(first, "init")
    capsys.readouterr()
    assert run_cli(first, "advance", "--minutes", "15") == 0
    assert "11:15 Europe/Bucharest" in capsys.readouterr().out
    assert (
        run_cli(
            first,
            "run-until",
            "--datetime",
            "2026-03-16 12:00",
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "12:00 Europe/Bucharest" in output
    assert "Processed scheduled actions: 1" in output

    second = tmp_path / "second"
    run_cli(second, "init")
    capsys.readouterr()
    assert run_cli(second, "next-event") == 0
    assert "Processed scheduled actions: 1" in capsys.readouterr().out
    assert run_cli(second, "next-event") == 0
    assert "No pending scheduled actions" in capsys.readouterr().out


@pytest.mark.parametrize(
    "arguments",
    [
        ("advance", "--minutes", "0"),
        ("advance", "--minutes", "-1"),
        ("run-until", "--datetime", "2026-03-16 10:00"),
    ],
)
def test_invalid_time_controls_return_nonzero(
    tmp_path,
    capsys,
    arguments: tuple[str, ...],
) -> None:
    root = tmp_path / ".simulation"
    run_cli(root, "init")
    capsys.readouterr()

    assert run_cli(root, *arguments) == 2
    assert "Error:" in capsys.readouterr().err


def test_events_filters_and_show_entity(tmp_path, capsys) -> None:
    root = tmp_path / ".simulation"
    run_cli(root, "init")
    capsys.readouterr()
    run_cli(root, "parcel-transition", "P-1006-A", "SCANNED")
    capsys.readouterr()

    assert (
        run_cli(
            root,
            "events",
            "--limit",
            "1",
            "--entity-id",
            "P-1006-A",
            "--event-type",
            "PARCEL_STATUS_CHANGED",
        )
        == 0
    )
    events = capsys.readouterr().out
    assert "EVT-000002" in events
    assert "P-1006-A" in events

    assert run_cli(root, "show", "parcel", "P-1006-A") == 0
    shown = capsys.readouterr().out
    assert '"status": "SCANNED"' in shown
    assert "Europe/Bucharest" in shown


def test_valid_and_invalid_transition_commands(tmp_path, capsys) -> None:
    root = tmp_path / ".simulation"
    run_cli(root, "init")
    capsys.readouterr()

    assert run_cli(root, "shipment-transition", "SHIP-002", "ARRIVED") == 0
    assert "SHIPMENT_STATUS_CHANGED" in capsys.readouterr().out
    assert run_cli(root, "parcel-transition", "P-1005-A", "OUT_FOR_DELIVERY") == 2
    error = capsys.readouterr().err
    assert "allowed next states" in error


def test_route_commands_and_validation(tmp_path, capsys) -> None:
    root = tmp_path / ".simulation"
    run_cli(root, "init")
    capsys.readouterr()

    assert (
        run_cli(
            root,
            "assign-route",
            "ROUTE-03",
            "--driver",
            "D-03",
            "--vehicle",
            "VAN-03",
        )
        == 0
    )
    assert "ROUTE_ASSIGNED" in capsys.readouterr().out
    assert run_cli(root, "start-route", "ROUTE-03") == 0
    assert "ROUTE_STARTED" in capsys.readouterr().out
    assert run_cli(root, "complete-route", "ROUTE-01") == 0
    assert "ROUTE_COMPLETED" in capsys.readouterr().out
    assert run_cli(root, "validate") == 0
    assert "Persistence valid" in capsys.readouterr().out


def test_reset_safety_and_output(tmp_path, capsys) -> None:
    root = tmp_path / ".simulation"
    run_cli(root, "init", "--seed", "42")
    capsys.readouterr()

    assert run_cli(root, "reset", "--seed", "73") == 2
    assert "--force" in capsys.readouterr().err
    assert run_cli(root, "reset", "--seed", "73", "--force") == 0
    output = capsys.readouterr().out
    assert "Archived run: RUN-20260316-001" in output
    assert "New run: RUN-20260316-002" in output
    assert "New seed: 73" in output


def test_separate_processes_retain_time(tmp_path) -> None:
    root = tmp_path / ".simulation"
    environment = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).parents[1] / "src"),
    }
    base = [
        sys.executable,
        "-m",
        "courier_sim.cli.app",
        "--simulation-dir",
        str(root),
    ]
    subprocess.run([*base, "init", "--seed", "42"], check=True, env=environment)
    subprocess.run(
        [*base, "advance", "--minutes", "30"],
        check=True,
        env=environment,
    )
    status = subprocess.run(
        [*base, "status"],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert "2026-03-16 11:30 Europe/Bucharest" in status.stdout
    assert "Historical events: 3" in status.stdout
