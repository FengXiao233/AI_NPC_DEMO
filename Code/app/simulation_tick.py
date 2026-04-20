import json
import sqlite3

from pydantic import Field

from app.action_planner import ActionPlanResult, plan_next_action_for_npc
from app.models import StrictSchemaModel
from app.passive_state import apply_passive_state_drift
from app.state_repository import load_agent_state
from app.task_executor import TaskExecutionResult, execute_current_task_for_npc
from scripts.init_sqlite import dump_json


class SimulationTickRequest(StrictSchemaModel):
    current_tick: int = Field(ge=0)
    npc_ids: list[str] = Field(default_factory=list)


class NpcTickResult(StrictSchemaModel):
    npc_id: str
    passive_needs: dict[str, int] | None = None
    execution_result: TaskExecutionResult | None = None
    plan_result: ActionPlanResult | None = None
    skipped_reason: str = ""


class SimulationTickResult(StrictSchemaModel):
    current_tick: int
    npc_results: list[NpcTickResult]


def run_simulation_tick(
    connection: sqlite3.Connection,
    request: SimulationTickRequest,
) -> SimulationTickResult:
    # Thought architecture:
    # - Most ticks should stay cheap: passive drift + current task execution + routine/fallback planning.
    # - Future model thought should be routed by app.thought_service, not called directly from the tick loop.
    # - Model output must remain an inclination; ActionPlanner still decides queue/interruption/execution.
    # Deferred unless the user explicitly asks to implement model thought.
    npc_ids = request.npc_ids or load_all_npc_ids(connection)
    npc_results = []

    for npc_id in npc_ids:
        update_last_thought_tick(connection, npc_id, request.current_tick)
        before_state = load_agent_state(connection, npc_id)
        if before_state is None:
            npc_results.append(NpcTickResult(npc_id=npc_id, skipped_reason="NPC not found."))
            continue

        passive_needs = apply_passive_state_drift(connection, npc_id)
        execution_result = execute_current_task_for_npc(connection, npc_id)
        after_state = load_agent_state(connection, npc_id)
        if after_state is None:
            npc_results.append(NpcTickResult(npc_id=npc_id, skipped_reason="NPC disappeared after execution."))
            continue

        plan_result = None
        if should_plan(after_state):
            plan_result = plan_next_action_for_npc(connection, npc_id)

        npc_results.append(
            NpcTickResult(
                npc_id=npc_id,
                passive_needs=passive_needs,
                execution_result=execution_result,
                plan_result=plan_result,
            )
        )

    connection.commit()
    return SimulationTickResult(current_tick=request.current_tick, npc_results=npc_results)


def should_plan(agent_state) -> bool:
    if agent_state.current_task.task_type == "idle":
        return True
    if agent_state.message_queue:
        return True
    cooldown = agent_state.runtime_flags.thought_cooldown_ticks
    last_tick = agent_state.runtime_flags.last_thought_tick
    return cooldown == 0 or last_tick % cooldown == 0


def load_all_npc_ids(connection: sqlite3.Connection) -> list[str]:
    return [
        row[0]
        for row in connection.execute("SELECT npc_id FROM npc_state ORDER BY npc_id").fetchall()
    ]


def update_last_thought_tick(connection: sqlite3.Connection, npc_id: str, current_tick: int) -> None:
    row = connection.execute(
        "SELECT runtime_flags_json FROM npc_state WHERE npc_id = ?",
        (npc_id,),
    ).fetchone()
    if row is None:
        return

    runtime_flags = json.loads(row[0])
    runtime_flags["last_thought_tick"] = current_tick
    connection.execute(
        """
        UPDATE npc_state
        SET runtime_flags_json = ?,
            updated_at_tick = ?
        WHERE npc_id = ?
        """,
        (
            dump_json(runtime_flags),
            current_tick,
            npc_id,
        ),
    )
