import json
import sqlite3

from app.event_processor import process_world_event
from scripts.init_sqlite import DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR, initialize_connection


def test_process_world_event_routes_and_stores_memories() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        result = process_world_event(
            connection,
            {
                "event_id": "evt_monster_gate_001",
                "event_type": "monster_appeared",
                "actor_id": "monster_wolf_001",
                "target_id": None,
                "location_id": "village_gate",
                "payload": {},
                "importance": 60,
                "created_at_tick": 140,
            },
        )

        assert result.event_id == "evt_monster_gate_001"
        assert result.recipient_npc_ids == ["npc_guard_001", "npc_hunter_001", "npc_merchant_001"]
        assert result.memory_ids == [
            "mem_npc_guard_001_evt_monster_gate_001",
            "mem_npc_hunter_001_evt_monster_gate_001",
            "mem_npc_merchant_001_evt_monster_gate_001",
        ]
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM memories WHERE memory_id LIKE ?",
                ("mem_%_evt_monster_gate_001",),
            ).fetchone()[0]
            == 3
        )
        merchant_task_queue = json.loads(
            connection.execute(
                "SELECT task_queue_json FROM npc_state WHERE npc_id = ?",
                ("npc_merchant_001",),
            ).fetchone()[0]
        )
        assert any(task["source"] == "event" and task["task_type"] == "flee" for task in merchant_task_queue)


def test_process_world_event_persists_payload_and_expiration() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        process_world_event(
            connection,
            {
                "event_id": "evt_food_market_001",
                "event_type": "food_shortage",
                "actor_id": None,
                "target_id": None,
                "location_id": "market",
                "payload": {"related_ids": ["npc_merchant_001"]},
                "importance": 45,
                "created_at_tick": 150,
            },
        )

        payload_json = connection.execute(
            "SELECT payload_json FROM events WHERE event_id = ?",
            ("evt_food_market_001",),
        ).fetchone()[0]
        expires_at_tick = connection.execute(
            "SELECT expires_at_tick FROM memories WHERE memory_id = ?",
            ("mem_npc_merchant_001_evt_food_market_001",),
        ).fetchone()[0]

        payload = json.loads(payload_json)
        assert payload["related_ids"] == ["npc_merchant_001"]
        assert payload["_category"] == "resource_pressure"
        assert expires_at_tick is not None


def test_process_world_event_enqueues_default_role_response_tasks() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        result = process_world_event(
            connection,
            {
                "event_id": "evt_suspicious_gate_001",
                "event_type": "suspicious_arrival",
                "actor_id": "npc_stranger_001",
                "target_id": None,
                "location_id": "village_gate",
                "payload": {"appearance": "hooded merchant"},
                "importance": 55,
                "created_at_tick": 160,
            },
        )
        guard_queue = json.loads(
            connection.execute(
                "SELECT task_queue_json FROM npc_state WHERE npc_id = ?",
                ("npc_guard_001",),
            ).fetchone()[0]
        )

    assert "npc_guard_001" in result.recipient_npc_ids
    assert any(
        task["source"] == "event"
        and task["task_type"] == "investigate"
        and task["target_id"] == "suspicious_arrival"
        for task in guard_queue
    )
