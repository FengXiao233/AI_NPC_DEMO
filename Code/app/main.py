import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from app.action_planner import ActionPlanResult, plan_next_action_for_npc
from app.dialogue_history import load_dialogue_history
from app.dialogue_processor import PlayerUtteranceRequest, PlayerUtteranceResult, receive_player_utterance
from app.event_catalog import list_event_catalog_entries
from app.simulation_engine import SimulationBusyError, get_default_simulation_engine
from app.event_processor import EventProcessingResult, process_world_event
from app.memory_summarizer import WorldEvent
from app.models import (
    AgentState,
    DialogueHistoryRecord,
    EventCatalogEntry,
    ProductionOrder,
    StoredEventRecord,
    StoredInventoryItem,
    StoredMemoryRecord,
    StoredNpcBeliefRecord,
    StrictSchemaModel,
    ThoughtResult,
    WarehouseItem,
    WarehouseTransaction,
    WorldEntity,
    WorldResourceNode,
)
from app.simulation_tick import SimulationTickRequest, SimulationTickResult
from app.state_repository import (
    list_event_records,
    list_inventory_records,
    list_production_orders,
    list_warehouse_records,
    list_warehouse_transactions,
    list_belief_records,
    list_memory_records,
    list_world_entities,
    list_world_resource_nodes,
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


@app.get("/npcs/{npc_id}/inventory", response_model=list[StoredInventoryItem])
def list_npc_inventory(npc_id: str) -> list[StoredInventoryItem]:
    test_connection = getattr(app.state, "db_connection", None)
    if test_connection is not None:
        agent_state = load_agent_state(test_connection, npc_id)
        if agent_state is None:
            raise HTTPException(status_code=404, detail=f"NPC not found: {npc_id}")
        return list_inventory_records(test_connection, npc_id)

    db_path = get_db_path()
    ensure_runtime_database(db_path)
    with sqlite3.connect(db_path) as connection:
        agent_state = load_agent_state(connection, npc_id)
        if agent_state is None:
            raise HTTPException(status_code=404, detail=f"NPC not found: {npc_id}")
        return list_inventory_records(connection, npc_id)


@app.get("/world/resources", response_model=list[WorldResourceNode])
def list_world_resources(location_id: str | None = None) -> list[WorldResourceNode]:
    test_connection = getattr(app.state, "db_connection", None)
    if test_connection is not None:
        return list_world_resource_nodes(test_connection, location_id=location_id, include_depleted=True)

    db_path = get_db_path()
    ensure_runtime_database(db_path)
    with sqlite3.connect(db_path) as connection:
        return list_world_resource_nodes(connection, location_id=location_id, include_depleted=True)


@app.get("/village/warehouse", response_model=list[WarehouseItem])
def list_village_warehouse() -> list[WarehouseItem]:
    test_connection = getattr(app.state, "db_connection", None)
    if test_connection is not None:
        return list_warehouse_records(test_connection)

    db_path = get_db_path()
    ensure_runtime_database(db_path)
    with sqlite3.connect(db_path) as connection:
        return list_warehouse_records(connection)


@app.get("/village/warehouse/transactions", response_model=list[WarehouseTransaction])
def list_village_warehouse_transactions(limit: int = Query(default=50, ge=1, le=200)) -> list[WarehouseTransaction]:
    test_connection = getattr(app.state, "db_connection", None)
    if test_connection is not None:
        return list_warehouse_transactions(test_connection, limit=limit)

    db_path = get_db_path()
    ensure_runtime_database(db_path)
    with sqlite3.connect(db_path) as connection:
        return list_warehouse_transactions(connection, limit=limit)


@app.get("/village/production-orders", response_model=list[ProductionOrder])
def list_village_production_orders(include_completed: bool = False) -> list[ProductionOrder]:
    test_connection = getattr(app.state, "db_connection", None)
    if test_connection is not None:
        return list_production_orders(test_connection, include_completed=include_completed)

    db_path = get_db_path()
    ensure_runtime_database(db_path)
    with sqlite3.connect(db_path) as connection:
        return list_production_orders(connection, include_completed=include_completed)


@app.get("/world/entities", response_model=list[WorldEntity])
def list_world_dynamic_entities(location_id: str | None = None) -> list[WorldEntity]:
    test_connection = getattr(app.state, "db_connection", None)
    if test_connection is not None:
        return list_world_entities(test_connection, location_id=location_id, include_inactive=False)

    db_path = get_db_path()
    ensure_runtime_database(db_path)
    with sqlite3.connect(db_path) as connection:
        return list_world_entities(connection, location_id=location_id, include_inactive=False)


@app.get("/npcs/{npc_id}/dialogue-history", response_model=DialogueHistoryRecord)
def get_npc_dialogue_history(
    npc_id: str,
    speaker_id: str = Query(default="player_001"),
    recent_turn_limit: int = Query(default=6, ge=2, le=10),
) -> DialogueHistoryRecord:
    test_connection = getattr(app.state, "db_connection", None)
    if test_connection is not None:
        agent_state = load_agent_state(test_connection, npc_id)
        if agent_state is None:
            raise HTTPException(status_code=404, detail=f"NPC not found: {npc_id}")
        return load_dialogue_history(test_connection, npc_id, speaker_id, recent_turn_limit=recent_turn_limit)

    db_path = get_db_path()
    ensure_runtime_database(db_path)
    with sqlite3.connect(db_path) as connection:
        agent_state = load_agent_state(connection, npc_id)
        if agent_state is None:
            raise HTTPException(status_code=404, detail=f"NPC not found: {npc_id}")
        return load_dialogue_history(connection, npc_id, speaker_id, recent_turn_limit=recent_turn_limit)


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
    engine = get_default_simulation_engine()
    test_connection = getattr(app.state, "db_connection", None)
    try:
        if test_connection is not None:
            return engine.run_tick(test_connection, request)

        db_path = get_db_path()
        ensure_runtime_database(db_path)
        with sqlite3.connect(db_path) as connection:
            return engine.run_tick(connection, request)
    except SimulationBusyError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "status": "busy",
                "current_mode": engine.runtime_config.tick_reentry_mode,
                "message": str(exc),
            },
        ) from exc
