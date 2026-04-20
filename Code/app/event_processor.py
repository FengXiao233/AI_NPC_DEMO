import json
import sqlite3
from typing import Any

from pydantic import Field

from app.event_catalog import default_response_tasks_for_role, normalized_event_payload
from app.event_router import NpcRoutingProfile, route_event_to_npcs
from app.memory_summarizer import WorldEvent, summarize_events_for_npc
from app.models import MemorySummary, StrictSchemaModel
from app.relationship_effects import apply_relationship_effects
from scripts.init_sqlite import dump_json


class EventProcessingResult(StrictSchemaModel):
    event_id: str
    recipient_npc_ids: list[str]
    memory_ids: list[str]
    memories_by_npc: dict[str, list[MemorySummary]] = Field(default_factory=dict)
    relationship_updates: list[dict[str, Any]] = Field(default_factory=list)


def process_world_event(
    connection: sqlite3.Connection,
    event: WorldEvent | dict[str, Any],
) -> EventProcessingResult:
    parsed_event = event if isinstance(event, WorldEvent) else WorldEvent.model_validate(event)
    parsed_event = parsed_event.model_copy(
        update={"payload": normalized_event_payload(parsed_event.event_type, parsed_event.payload)}
    )
    connection.execute("PRAGMA foreign_keys = ON")

    is_new_event = not event_exists(connection, parsed_event.event_id)
    store_event(connection, parsed_event)
    relationship_updates = apply_relationship_effects(connection, parsed_event) if is_new_event else []
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

    connection.commit()
    return EventProcessingResult(
        event_id=parsed_event.event_id,
        recipient_npc_ids=recipient_npc_ids,
        memory_ids=memory_ids,
        memories_by_npc=memories_by_npc,
        relationship_updates=relationship_updates,
    )


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
