import json
import sqlite3
from typing import Any

from pydantic import Field

from app.action_planner import ActionPlanResult, commit_action_plan, plan_action_for_state
from app.event_catalog import default_response_tasks_for_role, get_event_definition, normalized_event_payload
from app.event_router import NpcRoutingProfile, route_event_to_npcs
from app.memory_summarizer import WorldEvent, summarize_events_for_npc
from app.models import MemorySummary, StrictSchemaModel
from app.relationship_effects import apply_relationship_effects
from app.state_repository import load_agent_state
from app.thought_provider import ThoughtProvider
from app.thought_service import generate_thought
from app.world_state import populate_event_world_effects
from scripts.init_sqlite import dump_json

IMPORTANT_EVENT_SECONDARY_THOUGHT_THRESHOLD = 55
SECONDARY_THOUGHT_PRIORITY_TIERS = {"high", "highest"}


class EventProcessingResult(StrictSchemaModel):
    event_id: str
    recipient_npc_ids: list[str]
    memory_ids: list[str]
    memories_by_npc: dict[str, list[MemorySummary]] = Field(default_factory=dict)
    relationship_updates: list[dict[str, Any]] = Field(default_factory=list)
    secondary_plan_results: dict[str, ActionPlanResult] = Field(default_factory=dict)
    spawned_entity_ids: list[str] = Field(default_factory=list)


def process_world_event(
    connection: sqlite3.Connection,
    event: WorldEvent | dict[str, Any],
    secondary_thought_provider: ThoughtProvider | None = None,
) -> EventProcessingResult:
    parsed_event = event if isinstance(event, WorldEvent) else WorldEvent.model_validate(event)
    parsed_event = parsed_event.model_copy(
        update={"payload": normalized_event_payload(parsed_event.event_type, parsed_event.payload)}
    )
    connection.execute("PRAGMA foreign_keys = ON")

    is_new_event = not event_exists(connection, parsed_event.event_id)
    store_event(connection, parsed_event)
    spawned_entity_ids = populate_event_world_effects(connection, parsed_event) if is_new_event else []
    relationship_updates = apply_relationship_effects(connection, parsed_event) if is_new_event else []
    if is_new_event:
        apply_event_survival_effects(connection, parsed_event)
    profiles = load_npc_routing_profiles(connection)
    recipient_npc_ids = route_event_to_npcs(parsed_event, profiles)

    memories_by_npc = {}
    memory_ids = []
    for npc_id in recipient_npc_ids:
        memories = summarize_events_for_npc(npc_id, [parsed_event], already_routed=True)
        for memory in memories:
            store_memory(connection, npc_id, memory)
            memory_ids.append(memory.memory_id)
        memories_by_npc[npc_id] = memories
        enqueue_default_event_responses(connection, npc_id, parsed_event)

    secondary_plan_results = (
        run_secondary_thought_for_event(
            connection,
            parsed_event,
            recipient_npc_ids,
            provider=secondary_thought_provider,
        )
        if is_new_event
        else {}
    )

    connection.commit()
    return EventProcessingResult(
        event_id=parsed_event.event_id,
        recipient_npc_ids=recipient_npc_ids,
        memory_ids=memory_ids,
        memories_by_npc=memories_by_npc,
        relationship_updates=relationship_updates,
        secondary_plan_results=secondary_plan_results,
        spawned_entity_ids=spawned_entity_ids,
    )


def run_secondary_thought_for_event(
    connection: sqlite3.Connection,
    event: WorldEvent,
    recipient_npc_ids: list[str],
    provider: ThoughtProvider | None = None,
) -> dict[str, ActionPlanResult]:
    if not should_run_secondary_thought_for_event(event):
        return {}

    plan_results: dict[str, ActionPlanResult] = {}
    for npc_id in recipient_npc_ids:
        agent_state = load_agent_state(connection, npc_id)
        if agent_state is None or agent_state.runtime_flags.priority_tier not in SECONDARY_THOUGHT_PRIORITY_TIERS:
            continue
        thought = generate_thought(agent_state, provider=provider)
        plan_result = plan_action_for_state(agent_state, thought=thought)
        commit_action_plan(connection, agent_state, plan_result)
        plan_results[npc_id] = plan_result
    return plan_results


def should_run_secondary_thought_for_event(event: WorldEvent) -> bool:
    return event.importance >= IMPORTANT_EVENT_SECONDARY_THOUGHT_THRESHOLD or get_event_definition(event.event_type).significant


def load_npc_routing_profiles(connection: sqlite3.Connection) -> list[NpcRoutingProfile]:
    profiles = []
    rows = connection.execute(
        """
        SELECT npc_id, role, location_id, runtime_flags_json
        FROM npc_state
        ORDER BY npc_id
        """
    ).fetchall()

    for npc_id, role, location_id, runtime_flags_json in rows:
        watched_ids = [
            row[0]
            for row in connection.execute(
                "SELECT target_id FROM relationships WHERE npc_id = ? ORDER BY target_id",
                (npc_id,),
            )
        ]
        runtime_flags = json.loads(runtime_flags_json)
        profiles.append(
            NpcRoutingProfile(
                npc_id=npc_id,
                role=role,
                location_id=location_id,
                is_critical_npc=runtime_flags.get("is_critical_npc", False),
                watched_ids=watched_ids,
            )
        )

    return profiles


def apply_event_survival_effects(connection: sqlite3.Connection, event: WorldEvent) -> None:
    if event.event_type != "attack" or not event.target_id or not event.target_id.startswith("npc_"):
        return
    row = connection.execute(
        "SELECT needs_json FROM npc_state WHERE npc_id = ?",
        (event.target_id,),
    ).fetchone()
    if row is None:
        return
    needs = json.loads(row[0])
    damage = int(event.payload.get("damage", 8))
    needs["health"] = clamp_need(int(needs.get("health", 100)) - max(1, damage))
    needs["safety"] = clamp_need(int(needs.get("safety", 50)) - min(30, damage + 6))
    connection.execute(
        """
        UPDATE npc_state
        SET needs_json = ?
        WHERE npc_id = ?
        """,
        (
            dump_json(needs),
            event.target_id,
        ),
    )


def clamp_need(value: int) -> int:
    return max(0, min(value, 100))


def enqueue_default_event_responses(
    connection: sqlite3.Connection,
    npc_id: str,
    event: WorldEvent,
) -> None:
    row = connection.execute(
        """
        SELECT role, task_queue_json
        FROM npc_state
        WHERE npc_id = ?
        """,
        (npc_id,),
    ).fetchone()
    if row is None:
        return

    role, task_queue_json = row
    task_queue = json.loads(task_queue_json)
    for task in default_response_tasks_for_role(event, role, npc_id):
        if not has_equivalent_event_task(task_queue, task):
            task_queue.append(task)

    connection.execute(
        """
        UPDATE npc_state
        SET task_queue_json = ?
        WHERE npc_id = ?
        """,
        (dump_json(task_queue), npc_id),
    )


def has_equivalent_event_task(task_queue: list[dict[str, Any]], task: dict[str, Any]) -> bool:
    return any(
        existing.get("task_id") == task["task_id"]
        or (
            existing.get("source") == "event"
            and existing.get("task_type") == task["task_type"]
            and existing.get("target_id") == task.get("target_id")
            and existing.get("location_id") == task.get("location_id")
        )
        for existing in task_queue
    )


def store_event(connection: sqlite3.Connection, event: WorldEvent) -> None:
    connection.execute(
        """
        INSERT INTO events (
            event_id,
            event_type,
            actor_id,
            target_id,
            location_id,
            payload_json,
            importance,
            created_at_tick
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_id) DO UPDATE SET
            event_type = excluded.event_type,
            actor_id = excluded.actor_id,
            target_id = excluded.target_id,
            location_id = excluded.location_id,
            payload_json = excluded.payload_json,
            importance = excluded.importance,
            created_at_tick = excluded.created_at_tick
        """,
        (
            event.event_id,
            event.event_type,
            event.actor_id,
            event.target_id,
            event.location_id,
            dump_json(event.payload),
            event.importance,
            event.created_at_tick,
        ),
    )


def event_exists(connection: sqlite3.Connection, event_id: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        is not None
    )


def store_memory(connection: sqlite3.Connection, npc_id: str, memory: MemorySummary) -> None:
    connection.execute(
        """
        INSERT INTO memories (
            memory_id,
            npc_id,
            summary,
            importance,
            related_ids_json,
            created_at_tick,
            expires_at_tick
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(memory_id) DO UPDATE SET
            npc_id = excluded.npc_id,
            summary = excluded.summary,
            importance = excluded.importance,
            related_ids_json = excluded.related_ids_json,
            created_at_tick = excluded.created_at_tick,
            expires_at_tick = excluded.expires_at_tick
        """,
        (
            memory.memory_id,
            npc_id,
            memory.summary,
            memory.importance,
            dump_json(memory.related_ids),
            memory.created_at_tick,
            memory.expires_at_tick,
        ),
    )
