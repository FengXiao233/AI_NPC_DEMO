import json
import sqlite3

from app.models import AgentState, MemorySummary, NpcBelief, StoredEventRecord, StoredMemoryRecord, StoredNpcBeliefRecord
from scripts.init_sqlite import dump_json


def list_npc_ids(connection: sqlite3.Connection) -> list[str]:
    return [
        row[0]
        for row in connection.execute("SELECT npc_id FROM npc_state ORDER BY npc_id").fetchall()
    ]


def load_all_agent_states(connection: sqlite3.Connection) -> list[AgentState]:
    return [
        agent_state
        for npc_id in list_npc_ids(connection)
        if (agent_state := load_agent_state(connection, npc_id)) is not None
    ]


def load_agent_state(connection: sqlite3.Connection, npc_id: str) -> AgentState | None:
    row = connection.execute(
        """
        SELECT
            npc_id,
            name,
            role,
            location_id,
            base_attributes_json,
            personality_json,
            needs_json,
            current_task_json,
            task_queue_json,
            message_queue_json,
            learning_bias_json,
            runtime_flags_json
        FROM npc_state
        WHERE npc_id = ?
        """,
        (npc_id,),
    ).fetchone()

    if row is None:
        return None

    runtime_flags = json.loads(row[11])
    current_tick = runtime_flags["last_thought_tick"]
    data = {
        "npc_id": row[0],
        "name": row[1],
        "role": row[2],
        "location_id": row[3],
        "base_attributes": json.loads(row[4]),
        "personality": json.loads(row[5]),
        "needs": json.loads(row[6]),
        "relationships": load_relationships(connection, npc_id),
        "current_task": json.loads(row[7]),
        "task_queue": json.loads(row[8]),
        "message_queue": json.loads(row[9]),
        "memory_summary": load_active_memories(connection, npc_id, current_tick),
        "beliefs": load_active_beliefs(connection, npc_id, current_tick),
        "learning_bias": json.loads(row[10]),
        "runtime_flags": runtime_flags,
    }
    return AgentState.model_validate(data)


def load_relationships(connection: sqlite3.Connection, npc_id: str) -> list[dict]:
    rows = connection.execute(
        """
        SELECT target_id, favor, trust, hostility
        FROM relationships
        WHERE npc_id = ?
        ORDER BY target_id
        """,
        (npc_id,),
    ).fetchall()
    return [
        {
            "target_id": target_id,
            "favor": favor,
            "trust": trust,
            "hostility": hostility,
        }
        for target_id, favor, trust, hostility in rows
    ]


def load_active_memories(
    connection: sqlite3.Connection,
    npc_id: str,
    current_tick: int,
    limit: int = 10,
) -> list[dict]:
    rows = connection.execute(
        """
        SELECT memory_id, summary, importance, related_ids_json, created_at_tick, expires_at_tick
        FROM memories
        WHERE npc_id = ?
          AND (expires_at_tick IS NULL OR expires_at_tick > ?)
        ORDER BY importance DESC, created_at_tick DESC
        LIMIT ?
        """,
        (npc_id, current_tick, limit),
    ).fetchall()
    return [
        {
            "memory_id": memory_id,
            "summary": summary,
            "importance": importance,
            "related_ids": json.loads(related_ids_json),
            "created_at_tick": created_at_tick,
            "expires_at_tick": expires_at_tick,
        }
        for memory_id, summary, importance, related_ids_json, created_at_tick, expires_at_tick in rows
    ]


def list_event_records(connection: sqlite3.Connection, limit: int = 50) -> list[StoredEventRecord]:
    rows = connection.execute(
        """
        SELECT
            event_id,
            event_type,
            actor_id,
            target_id,
            location_id,
            payload_json,
            importance,
            created_at_tick
        FROM events
        ORDER BY created_at_tick DESC, event_id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        StoredEventRecord(
            event_id=event_id,
            event_type=event_type,
            actor_id=actor_id,
            target_id=target_id,
            location_id=location_id,
            payload=json.loads(payload_json),
            importance=importance,
            created_at_tick=created_at_tick,
        )
        for (
            event_id,
            event_type,
            actor_id,
            target_id,
            location_id,
            payload_json,
            importance,
            created_at_tick,
        ) in rows
    ]


def find_event_records_by_topic(
    connection: sqlite3.Connection,
    topic_hint: str | None,
    location_id: str | None,
    created_at_tick: int,
    lookback_ticks: int = 120,
    limit: int = 5,
) -> list[StoredEventRecord]:
    event_types = event_types_for_topic(topic_hint)
    if not event_types:
        return []

    earliest_evidence_tick = max(0, created_at_tick - lookback_ticks)
    params: list[object] = [*event_types, earliest_evidence_tick]
    location_filter = ""
    if location_id is not None:
        location_filter = "AND (location_id = ? OR location_id IS NULL)"
        params.append(location_id)
    params.append(limit)

    placeholders = ",".join("?" for _ in event_types)
    rows = connection.execute(
        f"""
        SELECT
            event_id,
            event_type,
            actor_id,
            target_id,
            location_id,
            payload_json,
            importance,
            created_at_tick
          FROM events
          WHERE event_type IN ({placeholders})
           AND created_at_tick >= ?
          {location_filter}
        ORDER BY created_at_tick DESC, importance DESC, event_id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [
        StoredEventRecord(
            event_id=event_id,
            event_type=event_type,
            actor_id=actor_id,
            target_id=target_id,
            location_id=stored_location_id,
            payload=json.loads(payload_json),
            importance=importance,
            created_at_tick=event_created_at_tick,
        )
        for (
            event_id,
            event_type,
            actor_id,
            target_id,
            stored_location_id,
            payload_json,
            importance,
            event_created_at_tick,
        ) in rows
    ]


def event_types_for_topic(topic_hint: str | None) -> tuple[str, ...]:
    if topic_hint == "monster_threat":
        return ("monster_appeared", "attack")
    if topic_hint == "suspicious_arrival":
        return ("suspicious_arrival",)
    if topic_hint == "food_shortage":
        return ("food_shortage",)
    if topic_hint == "help_request":
        return ("help_given", "help_refused", "player_helped", "player_harmed")
    return ()


def list_memory_records(
    connection: sqlite3.Connection,
    npc_id: str,
    current_tick: int | None = None,
    include_expired: bool = False,
    limit: int = 50,
) -> list[StoredMemoryRecord]:
    params: list[object] = [npc_id]
    expiration_filter = ""
    if not include_expired and current_tick is not None:
        expiration_filter = "AND (expires_at_tick IS NULL OR expires_at_tick > ?)"
        params.append(current_tick)
    params.append(limit)

    rows = connection.execute(
        f"""
        SELECT
            memory_id,
            npc_id,
            summary,
            importance,
            related_ids_json,
            created_at_tick,
            expires_at_tick
        FROM memories
        WHERE npc_id = ?
          {expiration_filter}
        ORDER BY created_at_tick DESC, importance DESC, memory_id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [
        StoredMemoryRecord(
            memory_id=memory_id,
            npc_id=stored_npc_id,
            summary=summary,
            importance=importance,
            related_ids=json.loads(related_ids_json),
            created_at_tick=created_at_tick,
            expires_at_tick=expires_at_tick,
        )
        for (
            memory_id,
            stored_npc_id,
            summary,
            importance,
            related_ids_json,
            created_at_tick,
            expires_at_tick,
        ) in rows
    ]


def load_active_beliefs(
    connection: sqlite3.Connection,
    npc_id: str,
    current_tick: int,
    limit: int = 10,
) -> list[dict]:
    rows = connection.execute(
        """
        SELECT
            belief_id,
            source_type,
            source_id,
            topic_hint,
            claim,
            confidence,
            truth_status,
            created_at_tick,
            expires_at_tick
        FROM npc_beliefs
        WHERE npc_id = ?
          AND (expires_at_tick IS NULL OR expires_at_tick > ?)
        ORDER BY confidence DESC, created_at_tick DESC
        LIMIT ?
        """,
        (npc_id, current_tick, limit),
    ).fetchall()
    return [
        {
            "belief_id": belief_id,
            "source_type": source_type,
            "source_id": source_id,
            "topic_hint": topic_hint,
            "claim": claim,
            "confidence": confidence,
            "truth_status": truth_status,
            "created_at_tick": created_at_tick,
            "expires_at_tick": expires_at_tick,
        }
        for (
            belief_id,
            source_type,
            source_id,
            topic_hint,
            claim,
            confidence,
            truth_status,
            created_at_tick,
            expires_at_tick,
        ) in rows
    ]


def list_belief_records(
    connection: sqlite3.Connection,
    npc_id: str,
    current_tick: int | None = None,
    include_expired: bool = False,
    limit: int = 50,
) -> list[StoredNpcBeliefRecord]:
    params: list[object] = [npc_id]
    expiration_filter = ""
    if not include_expired and current_tick is not None:
        expiration_filter = "AND (expires_at_tick IS NULL OR expires_at_tick > ?)"
        params.append(current_tick)
    params.append(limit)

    rows = connection.execute(
        f"""
        SELECT
            belief_id,
            npc_id,
            source_type,
            source_id,
            topic_hint,
            claim,
            confidence,
            truth_status,
            created_at_tick,
            expires_at_tick
        FROM npc_beliefs
        WHERE npc_id = ?
          {expiration_filter}
        ORDER BY created_at_tick DESC, confidence DESC, belief_id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [
        StoredNpcBeliefRecord(
            belief_id=belief_id,
            npc_id=stored_npc_id,
            source_type=source_type,
            source_id=source_id,
            topic_hint=topic_hint,
            claim=claim,
            confidence=confidence,
            truth_status=truth_status,
            created_at_tick=created_at_tick,
            expires_at_tick=expires_at_tick,
        )
        for (
            belief_id,
            stored_npc_id,
            source_type,
            source_id,
            topic_hint,
            claim,
            confidence,
            truth_status,
            created_at_tick,
            expires_at_tick,
        ) in rows
    ]


def upsert_npc_belief(connection: sqlite3.Connection, npc_id: str, belief: NpcBelief) -> None:
    connection.execute(
        """
        INSERT INTO npc_beliefs (
            belief_id,
            npc_id,
            source_type,
            source_id,
            topic_hint,
            claim,
            confidence,
            truth_status,
            created_at_tick,
            expires_at_tick
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(belief_id) DO UPDATE SET
            topic_hint = excluded.topic_hint,
            claim = excluded.claim,
            confidence = excluded.confidence,
            truth_status = excluded.truth_status,
            expires_at_tick = excluded.expires_at_tick
        """,
        (
            belief.belief_id,
            npc_id,
            belief.source_type,
            belief.source_id,
            belief.topic_hint,
            belief.claim,
            belief.confidence,
            belief.truth_status,
            belief.created_at_tick,
            belief.expires_at_tick,
        ),
    )


def update_npc_belief_truth_status(
    connection: sqlite3.Connection,
    belief_id: str,
    truth_status: str,
    confidence: int,
    expires_at_tick: int | None,
) -> None:
    connection.execute(
        """
        UPDATE npc_beliefs
        SET truth_status = ?,
            confidence = ?,
            expires_at_tick = ?
        WHERE belief_id = ?
        """,
        (
            truth_status,
            confidence,
            expires_at_tick,
            belief_id,
        ),
    )


def store_memory_record(connection: sqlite3.Connection, npc_id: str, memory: MemorySummary) -> None:
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


def update_npc_message_queue(
    connection: sqlite3.Connection,
    npc_id: str,
    message_queue: list[dict],
) -> None:
    connection.execute(
        """
        UPDATE npc_state
        SET message_queue_json = ?
        WHERE npc_id = ?
        """,
        (
            dump_json(message_queue),
            npc_id,
        ),
    )
