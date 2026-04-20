import sqlite3
from typing import Any

from app.event_catalog import get_event_definition
from app.memory_summarizer import WorldEvent


def apply_relationship_effects(
    connection: sqlite3.Connection,
    event: WorldEvent,
) -> list[dict[str, Any]]:
    deltas = get_event_definition(event.event_type).relationship_delta
    if deltas is None:
        return []

    updates = relationship_updates_for_event(connection, event, deltas)
    for update in updates:
        upsert_relationship(
            connection,
            npc_id=update["npc_id"],
            target_id=update["target_id"],
            favor_delta=update["favor_delta"],
            trust_delta=update["trust_delta"],
            hostility_delta=update["hostility_delta"],
        )
    return updates


def relationship_updates_for_event(
    connection: sqlite3.Connection,
    event: WorldEvent,
    deltas: dict[str, int],
) -> list[dict[str, Any]]:
    actor_id = event.actor_id
    target_id = event.target_id
    if actor_id is None or target_id is None:
        return []

    updates = []

    if is_npc_id(connection, target_id):
        updates.append(make_update(target_id, actor_id, deltas))

    if event.event_type in {"help_given", "trade_completed"} and is_npc_id(connection, actor_id):
        updates.append(make_update(actor_id, target_id, deltas))

    return updates


def make_update(npc_id: str, target_id: str, deltas: dict[str, int]) -> dict[str, Any]:
    return {
        "npc_id": npc_id,
        "target_id": target_id,
        "favor_delta": deltas["favor"],
        "trust_delta": deltas["trust"],
        "hostility_delta": deltas["hostility"],
    }


def upsert_relationship(
    connection: sqlite3.Connection,
    npc_id: str,
    target_id: str,
    favor_delta: int,
    trust_delta: int,
    hostility_delta: int,
) -> None:
    row = connection.execute(
        """
        SELECT favor, trust, hostility
        FROM relationships
        WHERE npc_id = ? AND target_id = ?
        """,
        (npc_id, target_id),
    ).fetchone()

    if row is None:
        favor, trust, hostility = 0, 0, 0
    else:
        favor, trust, hostility = row

    connection.execute(
        """
        INSERT INTO relationships (npc_id, target_id, favor, trust, hostility)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(npc_id, target_id) DO UPDATE SET
            favor = excluded.favor,
            trust = excluded.trust,
            hostility = excluded.hostility
        """,
        (
            npc_id,
            target_id,
            clamp_relation(favor + favor_delta),
            clamp_relation(trust + trust_delta),
            clamp_hostility(hostility + hostility_delta),
        ),
    )


def is_npc_id(connection: sqlite3.Connection, entity_id: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM npc_state WHERE npc_id = ?",
            (entity_id,),
        ).fetchone()
        is not None
    )


def clamp_relation(value: int) -> int:
    return max(-100, min(value, 100))


def clamp_hostility(value: int) -> int:
    return max(0, min(value, 100))
