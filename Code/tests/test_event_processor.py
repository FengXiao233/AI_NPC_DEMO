import json
import sqlite3

from app.event_processor import process_world_event
from app.models import ThoughtResult
from scripts.init_sqlite import DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR, initialize_connection


SEEDED_NPC_IDS = [
    "npc_blacksmith_001",
    "npc_farmer_001",
    "npc_guard_001",
    "npc_hunter_001",
    "npc_merchant_001",
    "npc_physician_001",
    "npc_village_chief_001",
]


class EchoThoughtProvider:
    def __init__(self) -> None:
        self.npc_ids: list[str] = []

    def think(self, agent_state, baseline_thought: ThoughtResult) -> ThoughtResult:
        self.npc_ids.append(agent_state.npc_id)
        return baseline_thought.model_copy(update={"notes": "secondary event thought"})


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
        assert result.recipient_npc_ids == SEEDED_NPC_IDS
        assert result.memory_ids == [f"mem_{npc_id}_evt_monster_gate_001" for npc_id in SEEDED_NPC_IDS]
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM memories WHERE memory_id LIKE ?",
                ("mem_%_evt_monster_gate_001",),
            ).fetchone()[0]
            == 7
        )
        merchant_task_queue = json.loads(
            connection.execute(
                "SELECT task_queue_json FROM npc_state WHERE npc_id = ?",
                ("npc_merchant_001",),
            ).fetchone()[0]
        )
        guard_task_queue = json.loads(
            connection.execute(
                "SELECT task_queue_json FROM npc_state WHERE npc_id = ?",
                ("npc_guard_001",),
            ).fetchone()[0]
        )
        hunter_task_queue = json.loads(
            connection.execute(
                "SELECT task_queue_json FROM npc_state WHERE npc_id = ?",
                ("npc_hunter_001",),
            ).fetchone()[0]
        )
        assert any(task["source"] == "event" and task["task_type"] == "flee" for task in merchant_task_queue)
        assert any(task["source"] == "event" and task["task_type"] == "patrol" for task in guard_task_queue)
        assert any(task["source"] == "event" and task["task_type"] == "hunt" for task in hunter_task_queue)


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


def test_important_event_runs_secondary_model_thought_for_high_priority_npcs() -> None:
    provider = EchoThoughtProvider()
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        result = process_world_event(
            connection,
            {
                "event_id": "evt_food_secondary_thought_001",
                "event_type": "food_shortage",
                "actor_id": None,
                "target_id": None,
                "location_id": "market",
                "payload": {"related_ids": ["npc_merchant_001", "npc_hunter_001"]},
                "importance": 60,
                "created_at_tick": 170,
            },
            secondary_thought_provider=provider,
        )
        merchant_queue = json.loads(
            connection.execute(
                "SELECT task_queue_json FROM npc_state WHERE npc_id = ?",
                ("npc_merchant_001",),
            ).fetchone()[0]
        )

    assert provider.npc_ids == [
        "npc_hunter_001",
        "npc_merchant_001",
        "npc_physician_001",
        "npc_village_chief_001",
    ]
    assert set(result.secondary_plan_results) == {
        "npc_hunter_001",
        "npc_merchant_001",
        "npc_physician_001",
        "npc_village_chief_001",
    }
    assert all(plan.thought.notes.endswith("route=model") for plan in result.secondary_plan_results.values())
    assert any(task["source"] == "thought" for task in merchant_queue)


def test_duplicate_event_does_not_repeat_secondary_thought() -> None:
    provider = EchoThoughtProvider()
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        event = {
            "event_id": "evt_food_secondary_thought_once",
            "event_type": "food_shortage",
            "actor_id": None,
            "target_id": None,
            "location_id": "market",
            "payload": {"related_ids": ["npc_merchant_001"]},
            "importance": 60,
            "created_at_tick": 170,
        }

        first_result = process_world_event(connection, event, secondary_thought_provider=provider)
        second_result = process_world_event(connection, event, secondary_thought_provider=provider)

    assert first_result.secondary_plan_results
    assert second_result.secondary_plan_results == {}
