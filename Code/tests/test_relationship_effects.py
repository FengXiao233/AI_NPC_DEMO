import sqlite3

from app.event_processor import process_world_event
from scripts.init_sqlite import DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR, initialize_connection


def test_player_helped_updates_target_npc_relationship_once() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        result = process_world_event(
            connection,
            {
                "event_id": "evt_player_helped_merchant_001",
                "event_type": "player_helped",
                "actor_id": "player_001",
                "target_id": "npc_merchant_001",
                "location_id": "market",
                "payload": {},
                "importance": 70,
                "created_at_tick": 200,
            },
        )
        process_world_event(
            connection,
            {
                "event_id": "evt_player_helped_merchant_001",
                "event_type": "player_helped",
                "actor_id": "player_001",
                "target_id": "npc_merchant_001",
                "location_id": "market",
                "payload": {},
                "importance": 70,
                "created_at_tick": 200,
            },
        )
        favor, trust, hostility = connection.execute(
            """
            SELECT favor, trust, hostility
            FROM relationships
            WHERE npc_id = ? AND target_id = ?
            """,
            ("npc_merchant_001", "player_001"),
        ).fetchone()

    assert result.relationship_updates == [
        {
            "npc_id": "npc_merchant_001",
            "target_id": "player_001",
            "favor_delta": 6,
            "trust_delta": 10,
            "hostility_delta": -3,
        }
    ]
    assert favor == 21
    assert trust == 30
    assert hostility == 0


def test_help_given_updates_both_npc_relationships() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        result = process_world_event(
            connection,
            {
                "event_id": "evt_guard_helped_hunter_001",
                "event_type": "help_given",
                "actor_id": "npc_guard_001",
                "target_id": "npc_hunter_001",
                "location_id": "forest_edge",
                "payload": {},
                "importance": 65,
                "created_at_tick": 210,
            },
        )

    assert {
        (update["npc_id"], update["target_id"])
        for update in result.relationship_updates
    } == {
        ("npc_hunter_001", "npc_guard_001"),
        ("npc_guard_001", "npc_hunter_001"),
    }
