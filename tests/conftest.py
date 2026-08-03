from courier_sim.engine.commands import InitializeSimulationCommand
from courier_sim.engine.models import WorldState
from courier_sim.engine.processor import CommandProcessor
from courier_sim.engine.state import build_initial_state


def make_state(run_id: str = "RUN-20260316-001", seed: int = 42) -> WorldState:
    state = build_initial_state(run_id, seed)
    return CommandProcessor(state).execute(InitializeSimulationCommand()).state
