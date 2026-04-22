import sqlite3

from scripts.init_sqlite import DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR, initialize_connection


def test_initialize_database_creates_core_tables() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        memory_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(memories)")
        }

    assert {
        "npc_state",
        "relationships",
        "memories",
        "events",
        "npc_beliefs",
        "dialogue_turns",
        "dialogue_sessions",
        "npc_inventory",
        "village_warehouse",
        "village_warehouse_transactions",
        "village_production_orders",
        "world_resource_nodes",
        "world_entities",
    }.issubset(table_names)
    assert "expires_at_tick" in memory_columns


def test_initialize_database_seeds_npc_relationships_and_memories() -> None:
    with sqlite3.connect(":memory:") as connection:
        seed_count = initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        npc_count = connection.execute("SELECT COUNT(*) FROM npc_state").fetchone()[0]
        relationship_count = connection.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
        memory_count = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        event_count = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        belief_count = connection.execute("SELECT COUNT(*) FROM npc_beliefs").fetchone()[0]
        dialogue_turn_count = connection.execute("SELECT COUNT(*) FROM dialogue_turns").fetchone()[0]
        dialogue_session_count = connection.execute("SELECT COUNT(*) FROM dialogue_sessions").fetchone()[0]
        inventory_count = connection.execute("SELECT COUNT(*) FROM npc_inventory").fetchone()[0]
        warehouse_count = connection.execute("SELECT COUNT(*) FROM village_warehouse").fetchone()[0]
        warehouse_transaction_count = connection.execute("SELECT COUNT(*) FROM village_warehouse_transactions").fetchone()[0]
        production_order_count = connection.execute("SELECT COUNT(*) FROM village_production_orders").fetchone()[0]
        resource_count = connection.execute("SELECT COUNT(*) FROM world_resource_nodes").fetchone()[0]
        entity_count = connection.execute("SELECT COUNT(*) FROM world_entities").fetchone()[0]

    assert seed_count == 7
    assert npc_count == 7
    assert relationship_count == 21
    assert memory_count == 7
    assert event_count == 0
    assert belief_count == 0
    assert dialogue_turn_count == 0
    assert dialogue_session_count == 0
    assert inventory_count == 5
    assert warehouse_count == 6
    assert warehouse_transaction_count == 0
    assert production_order_count == 0
    assert resource_count == 4
    assert entity_count == 0
