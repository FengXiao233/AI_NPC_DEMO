import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from app.action_planner import ActionPlanResult, plan_next_action_for_npc
from app.dialogue_processor import PlayerUtteranceRequest, PlayerUtteranceResult, receive_player_utterance
from app.event_catalog import list_event_catalog_entries
from app.event_processor import EventProcessingResult, process_world_event
from app.memory_summarizer import WorldEvent
from app.models import AgentState, EventCatalogEntry, StoredEventRecord, StoredMemoryRecord, StoredNpcBeliefRecord, StrictSchemaModel, ThoughtResult
from app.simulation_tick import SimulationTickRequest, SimulationTickResult, run_simulation_tick
from app.state_repository import (
    list_event_records,
    list_belief_records,
    list_memory_records,
    load_agent_state,
    load_all_agent_states,
)
from app.task_executor import TaskExecutionResult, execute_current_task_for_npc
from app.thought_service import generate_thought
from scripts.init_sqlite import DEFAULT_DB_PATH, initialize_database, reset_connection, reset_database


app = FastAPI(title="NPC Thought Service")


class DebugResetResult(StrictSchemaModel):
    status: str
    seeded_npc_count: int


@app.post("/thought", response_model=ThoughtResult)
def thought(agent_state: AgentState) -> ThoughtResult:
    return generate_thought(agent_state)


@app.post("/events", response_model=EventProcessingResult)
def ingest_event(event: WorldEvent) -> EventProcessingResult:
    test_connection = getattr(app.state, "db_connection", None)
    if test_connection is not None:
        return process_world_event(test_connection, event)

    db_path = get_db_path()
    ensure_runtime_database(db_path)
    with sqlite3.connect(db_path) as connection:
        return process_world_event(connection, event)


@app.post("/npcs/{npc_id}/utterances", response_model=PlayerUtteranceResult)
def receive_utterance(npc_id: str, request: PlayerUtteranceRequest) -> PlayerUtteranceResult:
    test_connection = getattr(app.state, "db_connection", None)
    if test_connection is not None:
        result = receive_player_utterance(test_connection, npc_id, request)
    else:
        db_path = get_db_path()
        ensure_runtime_database(db_path)
        with sqlite3.connect(db_path) as connection:
            result = receive_player_utterance(connection, npc_id, request)

    if result is None:
        raise HTTPException(status_code=404, detail=f"NPC not found: {npc_id}")
    return result


def get_db_path() -> Path:
    return getattr(app.state, "db_path", DEFAULT_DB_PATH)


def ensure_runtime_database(db_path: Path) -> None:
    if db_path.exists():
        initialize_database(db_path, seed_dir=None)
        return
    initialize_database(db_path)


@app.post("/debug/reset", response_model=DebugResetResult)
def reset_world_state() -> DebugResetResult:
    test_connection = getattr(app.state, "db_connection", None)
    if test_connection is not None:
        seed_count = reset_connection(test_connection)
    else:
        db_path = get_db_path()
        seed_count = reset_database(db_path)

    return DebugResetResult(status="reset", seeded_npc_count=seed_count)


@app.get("/npcs", response_model=list[AgentState])
def list_npcs() -> list[AgentState]:
    test_connection = getattr(app.state, "db_connection", None)
    if test_connection is not None:
        return load_all_agent_states(test_connection)

    db_path = get_db_path()
    ensure_runtime_database(db_path)
    with sqlite3.connect(db_path) as connection:
        return load_all_agent_states(connection)


@app.get("/npcs/{npc_id}", response_model=AgentState)
def get_npc(npc_id: str) -> AgentState:
    test_connection = getattr(app.state, "db_connection", None)
    if test_connection is not None:
        agent_state = load_agent_state(test_connection, npc_id)
    else:
        db_path = get_db_path()
        ensure_runtime_database(db_path)
        with sqlite3.connect(db_path) as connection:
            agent_state = load_agent_state(connection, npc_id)

    if agent_state is None:
        raise HTTPException(status_code=404, detail=f"NPC not found: {npc_id}")
    return agent_state


@app.get("/events", response_model=list[StoredEventRecord])
def list_events(limit: int = Query(default=50, ge=1, le=200)) -> list[StoredEventRecord]:
    test_connection = getattr(app.state, "db_connection", None)
    if test_connection is not None:
        return list_event_records(test_connection, limit=limit)

    db_path = get_db_path()
    ensure_runtime_database(db_path)
    with sqlite3.connect(db_path) as connection:
        return list_event_records(connection, limit=limit)


@app.get("/event-catalog", response_model=list[EventCatalogEntry])
def get_event_catalog() -> list[EventCatalogEntry]:
    return list_event_catalog_entries()


@app.get("/npcs/{npc_id}/memories", response_model=list[StoredMemoryRecord])
def list_npc_memories(
    npc_id: str,
    include_expired: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[StoredMemoryRecord]:
    test_connection = getattr(app.state, "db_connection", None)
    if test_connection is not None:
        agent_state = load_agent_state(test_connection, npc_id)
        if agent_state is None:
            raise HTTPException(status_code=404, detail=f"NPC not found: {npc_id}")
        return list_memory_records(
            test_connection,
            npc_id,
            current_tick=agent_state.runtime_flags.last_thought_tick,
            include_expired=include_expired,
            limit=limit,
        )

    db_path = get_db_path()
    ensure_runtime_database(db_path)
    with sqlite3.connect(db_path) as connection:
        agent_state = load_agent_state(connection, npc_id)
        if agent_state is None:
            raise HTTPException(status_code=404, detail=f"NPC not found: {npc_id}")
        return list_memory_records(
            connection,
            npc_id,
            current_tick=agent_state.runtime_flags.last_thought_tick,
            include_expired=include_expired,
            limit=limit,
        )


@app.get("/npcs/{npc_id}/beliefs", response_model=list[StoredNpcBeliefRecord])
def list_npc_beliefs(
    npc_id: str,
    include_expired: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[StoredNpcBeliefRecord]:
    test_connection = getattr(app.state, "db_connection", None)
    if test_connection is not None:
        agent_state = load_agent_state(test_connection, npc_id)
        if agent_state is None:
            raise HTTPException(status_code=404, detail=f"NPC not found: {npc_id}")
        return list_belief_records(
            test_connection,
            npc_id,
            current_tick=agent_state.runtime_flags.last_thought_tick,
            include_expired=include_expired,
            limit=limit,
        )

    db_path = get_db_path()
    ensure_runtime_database(db_path)
    with sqlite3.connect(db_path) as connection:
        agent_state = load_agent_state(connection, npc_id)
        if agent_state is None:
            raise HTTPException(status_code=404, detail=f"NPC not found: {npc_id}")
        return list_belief_records(
            connection,
            npc_id,
            current_tick=agent_state.runtime_flags.last_thought_tick,
            include_expired=include_expired,
            limit=limit,
        )


@app.get("/npcs/{npc_id}/thought", response_model=ThoughtResult)
def thought_for_npc(npc_id: str) -> ThoughtResult:
    test_connection = getattr(app.state, "db_connection", None)
    if test_connection is not None:
        agent_state = load_agent_state(test_connection, npc_id)
    else:
        db_path = get_db_path()
        ensure_runtime_database(db_path)
        with sqlite3.connect(db_path) as connection:
            agent_state = load_agent_state(connection, npc_id)

    if agent_state is None:
        raise HTTPException(status_code=404, detail=f"NPC not found: {npc_id}")
    return generate_thought(agent_state)


@app.post("/npcs/{npc_id}/plan", response_model=ActionPlanResult)
def plan_for_npc(npc_id: str) -> ActionPlanResult:
    test_connection = getattr(app.state, "db_connection", None)
    if test_connection is not None:
        result = plan_next_action_for_npc(test_connection, npc_id)
    else:
        db_path = get_db_path()
        ensure_runtime_database(db_path)
        with sqlite3.connect(db_path) as connection:
            result = plan_next_action_for_npc(connection, npc_id)

    if result is None:
        raise HTTPException(status_code=404, detail=f"NPC not found: {npc_id}")
    return result


@app.post("/npcs/{npc_id}/execute-task", response_model=TaskExecutionResult)
def execute_task_for_npc(npc_id: str) -> TaskExecutionResult:
    test_connection = getattr(app.state, "db_connection", None)
    if test_connection is not None:
        result = execute_current_task_for_npc(test_connection, npc_id)
    else:
        db_path = get_db_path()
        ensure_runtime_database(db_path)
        with sqlite3.connect(db_path) as connection:
            result = execute_current_task_for_npc(connection, npc_id)

    if result is None:
        raise HTTPException(status_code=404, detail=f"NPC not found: {npc_id}")
    return result


@app.post("/simulation/tick", response_model=SimulationTickResult)
def simulation_tick(request: SimulationTickRequest) -> SimulationTickResult:
    test_connection = getattr(app.state, "db_connection", None)
    if test_connection is not None:
        return run_simulation_tick(test_connection, request)

    db_path = get_db_path()
    ensure_runtime_database(db_path)
    with sqlite3.connect(db_path) as connection:
        return run_simulation_tick(connection, request)
