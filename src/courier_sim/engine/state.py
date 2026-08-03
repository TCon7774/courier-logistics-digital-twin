"""Deterministic creation of a fresh simulation world."""

from datetime import datetime
from zoneinfo import ZoneInfo

from courier_sim.engine.models import ScheduledAction, ScheduledActionType, WorldState
from courier_sim.sample_data.bucharest import build_sample_bucharest_scenario

BUCHAREST = ZoneInfo("Europe/Bucharest")
INITIAL_SIMULATION_DATETIME = datetime(2026, 3, 16, 11, 0, tzinfo=BUCHAREST)


def build_initial_state(simulation_run_id: str, seed: int) -> WorldState:
    """Build a deterministic active state and the narrow Milestone 2 schedule."""
    scenario = build_sample_bucharest_scenario(seed=seed)
    scheduled_actions = [
        ScheduledAction(
            action_id="ACT-000001",
            action_type=ScheduledActionType.SHIPMENT_ARRIVAL,
            execute_at=datetime(2026, 3, 16, 11, 30, tzinfo=BUCHAREST),
            creation_sequence=1,
            entity_id="SHIP-002",
            data={"target_status": "ARRIVED"},
        )
    ]
    return WorldState(
        simulation_run_id=simulation_run_id,
        scenario_seed=seed,
        current_datetime=INITIAL_SIMULATION_DATETIME,
        scenario=scenario,
        scheduled_actions=scheduled_actions,
        next_scheduled_action_sequence=2,
    )
