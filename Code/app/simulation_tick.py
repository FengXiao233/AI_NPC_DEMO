import json
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor

from pydantic import Field

from app.action_planner import ActionPlanResult, commit_action_plan, plan_action_for_state
from app.event_processor import process_world_event
from app.models import AgentState, StrictSchemaModel, WorldUpdateResult
from app.passive_state import apply_passive_state_drift
from app.state_repository import load_agent_state
from app.task_executor import (
    TaskExecutionContext,
    TaskExecutionPreview,
    TaskExecutionResult,
    build_task_execution_context,
    commit_task_execution_preview,
    preview_task_execution,
    task_execution_result_from_preview,
)
from app.world_state import (
    advance_entity_behaviors,
    generate_random_world_events,
    mature_due_production_orders,
    move_roaming_entities,
    refresh_world_resources,
)
from scripts.init_sqlite import dump_json


class SimulationTickRequest(StrictSchemaModel):
    current_tick: int = Field(ge=0)
    npc_ids: list[str] = Field(default_factory=list)
    include_profile: bool = False
    enable_world_updates: bool = False


class NpcTickProfile(StrictSchemaModel):
    npc_id: str
    execution_preview_ms: float = 0.0
    execution_commit_ms: float = 0.0
    planning_preview_ms: float = 0.0
    planning_commit_ms: float = 0.0
    planned: bool = False
    used_model: bool = False
    skipped_reason: str = ""


class SimulationTickProfile(StrictSchemaModel):
    total_ms: float
    update_clock_ms: float
    passive_phase_ms: float
    execution_context_ms: float
    execution_preview_ms: float
    execution_commit_ms: float
    planning_preview_ms: float
    planning_commit_ms: float
    execution_worker_count: int
    plan_worker_count: int
    planned_npc_ids: list[str] = Field(default_factory=list)
    model_planned_npc_ids: list[str] = Field(default_factory=list)
    slowest_execution_npc_id: str | None = None
    slowest_planning_npc_id: str | None = None
    npc_profiles: list[NpcTickProfile] = Field(default_factory=list)


class NpcTickResult(StrictSchemaModel):
    npc_id: str
    passive_needs: dict[str, int] | None = None
    execution_result: TaskExecutionResult | None = None
    plan_result: ActionPlanResult | None = None
    skipped_reason: str = ""


class SimulationTickResult(StrictSchemaModel):
    current_tick: int
    npc_results: list[NpcTickResult]
    profile: SimulationTickProfile | None = None
    world_update: WorldUpdateResult | None = None


def run_simulation_tick(
    connection: sqlite3.Connection,
    request: SimulationTickRequest,
    execution_workers: int | None = None,
    plan_workers: int | None = None,
) -> SimulationTickResult:
    total_start = time.perf_counter()
    npc_ids = request.npc_ids or load_all_npc_ids(connection)
    npc_results_by_id: dict[str, NpcTickResult] = {}
    npc_profiles_by_id = {npc_id: NpcTickProfile(npc_id=npc_id) for npc_id in npc_ids}
    execution_inputs: list[tuple[AgentState, TaskExecutionContext]] = []
    passive_needs_by_id: dict[str, dict[str, int] | None] = {}
    states_requiring_plan: list[AgentState] = []
    world_update = WorldUpdateResult()

    clock_start = time.perf_counter()
    for npc_id in npc_ids:
        update_last_thought_tick(connection, npc_id, request.current_tick)
    update_clock_ms = elapsed_ms(clock_start)
    world_update.matured_production_order_ids = mature_due_production_orders(connection, request.current_tick)

    if request.enable_world_updates:
        world_update.refreshed_resources = refresh_world_resources(connection, request.current_tick)
        world_update.moved_entity_ids = move_roaming_entities(connection, request.current_tick)
        for event in advance_entity_behaviors(connection, request.current_tick):
            result = process_world_event(connection, event)
            world_update.generated_event_ids.append(result.event_id)
            world_update.spawned_entity_ids.extend(result.spawned_entity_ids)
        for event in generate_random_world_events(connection, request.current_tick):
            result = process_world_event(connection, event)
            world_update.generated_event_ids.append(result.event_id)
            world_update.spawned_entity_ids.extend(result.spawned_entity_ids)

    passive_start = time.perf_counter()
    states_after_passive: dict[str, AgentState] = {}
    for npc_id in npc_ids:
        current_state = load_agent_state(connection, npc_id)
        if current_state is None:
            reason = "NPC not found."
            npc_results_by_id[npc_id] = NpcTickResult(npc_id=npc_id, skipped_reason=reason)
            npc_profiles_by_id[npc_id].skipped_reason = reason
            continue

        passive_needs = apply_passive_state_drift(connection, npc_id)
        passive_needs_by_id[npc_id] = passive_needs
        after_passive_state = load_agent_state(connection, npc_id)
        if after_passive_state is None:
            reason = "NPC disappeared after passive drift."
            npc_results_by_id[npc_id] = NpcTickResult(npc_id=npc_id, skipped_reason=reason)
            npc_profiles_by_id[npc_id].skipped_reason = reason
            continue
        states_after_passive[npc_id] = after_passive_state
    passive_phase_ms = elapsed_ms(passive_start)

    execution_context_start = time.perf_counter()
    for npc_id in npc_ids:
        agent_state = states_after_passive.get(npc_id)
        if agent_state is None:
            continue
        execution_inputs.append((agent_state, build_task_execution_context(connection, agent_state)))
    execution_context_ms = elapsed_ms(execution_context_start)

    execution_preview_start = time.perf_counter()
    execution_previews, execution_preview_timings, execution_worker_count = build_execution_previews_parallel(
        execution_inputs,
        execution_workers=execution_workers,
    )
    execution_preview_ms = elapsed_ms(execution_preview_start)

    execution_commit_start = time.perf_counter()
    for npc_id in npc_ids:
        preview = execution_previews.get(npc_id)
        if preview is None:
            continue
        commit_start = time.perf_counter()
        commit_task_execution_preview(connection, preview)
        npc_profiles_by_id[npc_id].execution_preview_ms = execution_preview_timings.get(npc_id, 0.0)
        npc_profiles_by_id[npc_id].execution_commit_ms = elapsed_ms(commit_start)

        after_state = load_agent_state(connection, npc_id)
        if after_state is None:
            reason = "NPC disappeared after execution."
            npc_results_by_id[npc_id] = NpcTickResult(
                npc_id=npc_id,
                passive_needs=passive_needs_by_id.get(npc_id),
                execution_result=task_execution_result_from_preview(preview),
                skipped_reason=reason,
            )
            npc_profiles_by_id[npc_id].skipped_reason = reason
            continue
        if should_plan(after_state):
            states_requiring_plan.append(after_state)

        npc_results_by_id[npc_id] = NpcTickResult(
            npc_id=npc_id,
            passive_needs=passive_needs_by_id.get(npc_id),
            execution_result=task_execution_result_from_preview(preview),
        )
    execution_commit_ms = elapsed_ms(execution_commit_start)

    planning_preview_start = time.perf_counter()
    planned_results, planning_preview_timings, plan_worker_count = build_plan_results_parallel(
        states_requiring_plan,
        plan_workers=plan_workers,
    )
    planning_preview_ms = elapsed_ms(planning_preview_start)

    planning_commit_start = time.perf_counter()
    states_by_npc_id = {state.npc_id: state for state in states_requiring_plan}
    planned_npc_ids: list[str] = []
    model_planned_npc_ids: list[str] = []
    for npc_id in npc_ids:
        if npc_id not in planned_results:
            continue
        planned_npc_ids.append(npc_id)
        npc_profiles_by_id[npc_id].planned = True
        npc_profiles_by_id[npc_id].planning_preview_ms = planning_preview_timings.get(npc_id, 0.0)
        npc_profiles_by_id[npc_id].used_model = thought_used_model(planned_results[npc_id])
        if npc_profiles_by_id[npc_id].used_model:
            model_planned_npc_ids.append(npc_id)
        commit_start = time.perf_counter()
        update_last_plan_tick(connection, npc_id, request.current_tick)
        commit_action_plan(connection, states_by_npc_id[npc_id], planned_results[npc_id])
        npc_profiles_by_id[npc_id].planning_commit_ms = elapsed_ms(commit_start)
        npc_results_by_id[npc_id].plan_result = planned_results[npc_id]
    planning_commit_ms = elapsed_ms(planning_commit_start)

    connection.commit()

    profile = None
    if request.include_profile:
        profile = SimulationTickProfile(
            total_ms=elapsed_ms(total_start),
            update_clock_ms=update_clock_ms,
            passive_phase_ms=passive_phase_ms,
            execution_context_ms=execution_context_ms,
            execution_preview_ms=execution_preview_ms,
            execution_commit_ms=execution_commit_ms,
            planning_preview_ms=planning_preview_ms,
            planning_commit_ms=planning_commit_ms,
            execution_worker_count=execution_worker_count,
            plan_worker_count=plan_worker_count,
            planned_npc_ids=planned_npc_ids,
            model_planned_npc_ids=model_planned_npc_ids,
            slowest_execution_npc_id=slowest_execution_npc_id(npc_profiles_by_id),
            slowest_planning_npc_id=slowest_planning_npc_id(npc_profiles_by_id),
            npc_profiles=[npc_profiles_by_id[npc_id] for npc_id in npc_ids],
        )

    return SimulationTickResult(
        current_tick=request.current_tick,
        npc_results=[npc_results_by_id[npc_id] for npc_id in npc_ids if npc_id in npc_results_by_id],
        profile=profile,
        world_update=world_update if request.enable_world_updates else None,
    )


def should_plan(agent_state: AgentState) -> bool:
    if agent_state.current_task.task_type == "idle":
        return True
    if has_new_messages(agent_state):
        return True
    cooldown = agent_state.runtime_flags.thought_cooldown_ticks
    last_plan_tick = agent_state.runtime_flags.last_plan_tick
    current_tick = agent_state.runtime_flags.last_thought_tick
    return cooldown == 0 or current_tick - last_plan_tick >= cooldown


def has_new_messages(agent_state: AgentState) -> bool:
    last_plan_tick = agent_state.runtime_flags.last_plan_tick
    current_tick = agent_state.runtime_flags.last_thought_tick
    return any(
        last_plan_tick < message.created_at_tick <= current_tick
        for message in agent_state.message_queue
    )


def load_all_npc_ids(connection: sqlite3.Connection) -> list[str]:
    return [
        row[0]
        for row in connection.execute("SELECT npc_id FROM npc_state ORDER BY npc_id").fetchall()
    ]


def build_execution_previews_parallel(
    execution_inputs: list[tuple[AgentState, TaskExecutionContext]],
    execution_workers: int | None = None,
) -> tuple[dict[str, TaskExecutionPreview], dict[str, float], int]:
    if not execution_inputs:
        return {}, {}, 0
    if len(execution_inputs) == 1:
        preview, preview_ms = build_execution_preview_for_state(execution_inputs[0])
        return {preview.npc_id: preview}, {preview.npc_id: preview_ms}, 1

    worker_count = resolve_worker_count(len(execution_inputs), override=execution_workers)
    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="tick-exec") as executor:
        preview_pairs = list(executor.map(build_execution_preview_for_state, execution_inputs))
    return (
        {preview.npc_id: preview for preview, _ in preview_pairs},
        {preview.npc_id: preview_ms for preview, preview_ms in preview_pairs},
        worker_count,
    )


def build_execution_preview_for_state(
    execution_input: tuple[AgentState, TaskExecutionContext],
) -> tuple[TaskExecutionPreview, float]:
    agent_state, execution_context = execution_input
    start = time.perf_counter()
    preview = preview_task_execution(agent_state, execution_context)
    return preview, elapsed_ms(start)


def build_plan_results_parallel(
    agent_states: list[AgentState],
    plan_workers: int | None = None,
) -> tuple[dict[str, ActionPlanResult], dict[str, float], int]:
    if not agent_states:
        return {}, {}, 0
    if len(agent_states) == 1:
        plan_result, preview_ms = build_plan_result_for_state(agent_states[0])
        return {plan_result.npc_id: plan_result}, {plan_result.npc_id: preview_ms}, 1

    worker_count = resolve_worker_count(len(agent_states), override=plan_workers)
    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="tick-plan") as executor:
        plan_pairs = list(executor.map(build_plan_result_for_state, agent_states))
    return (
        {plan_result.npc_id: plan_result for plan_result, _ in plan_pairs},
        {plan_result.npc_id: preview_ms for plan_result, preview_ms in plan_pairs},
        worker_count,
    )


def build_plan_result_for_state(agent_state: AgentState) -> tuple[ActionPlanResult, float]:
    start = time.perf_counter()
    plan_result = plan_action_for_state(agent_state)
    return plan_result, elapsed_ms(start)


def resolve_worker_count(task_count: int, override: int | None = None) -> int:
    if override is not None:
        return max(1, min(override, task_count))
    configured = os.getenv("SIMULATION_PLAN_MAX_WORKERS", "").strip()
    if configured:
        try:
            return max(1, min(int(configured), task_count))
        except ValueError:
            pass
    default_workers = min(8, max(2, task_count))
    return max(1, min(default_workers, task_count))


def thought_used_model(plan_result: ActionPlanResult) -> bool:
    notes = plan_result.thought.notes.lower()
    return "route=model" in notes or "source=llm" in notes


def slowest_execution_npc_id(npc_profiles_by_id: dict[str, NpcTickProfile]) -> str | None:
    candidates = [
        (
            profile.execution_preview_ms + profile.execution_commit_ms,
            profile.npc_id,
        )
        for profile in npc_profiles_by_id.values()
        if profile.execution_preview_ms > 0 or profile.execution_commit_ms > 0
    ]
    if not candidates:
        return None
    return max(candidates)[1]


def slowest_planning_npc_id(npc_profiles_by_id: dict[str, NpcTickProfile]) -> str | None:
    candidates = [
        (
            profile.planning_preview_ms + profile.planning_commit_ms,
            profile.npc_id,
        )
        for profile in npc_profiles_by_id.values()
        if profile.planning_preview_ms > 0 or profile.planning_commit_ms > 0
    ]
    if not candidates:
        return None
    return max(candidates)[1]


def elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 3)


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


def update_last_plan_tick(connection: sqlite3.Connection, npc_id: str, current_tick: int) -> None:
    row = connection.execute(
        "SELECT runtime_flags_json FROM npc_state WHERE npc_id = ?",
        (npc_id,),
    ).fetchone()
    if row is None:
        return

    runtime_flags = json.loads(row[0])
    runtime_flags["last_plan_tick"] = current_tick
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
