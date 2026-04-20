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

    assert {"npc_state", "relationships", "memories", "events", "npc_beliefs"}.issubset(table_names)
    assert "expires_at_tick" in memory_columns


def test_initialize_database_seeds_npc_relationships_and_memories() -> None:
    with sqlite3.connect(":memory:") as connection:
        seed_count = initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        npc_count = connection.execute("SELECT COUNT(*) FROM npc_state").fetchone()[0]
        relationship_count = connection.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
        memory_count = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        event_count = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        belief_count = connection.execute("SELECT COUNT(*) FROM npc_beliefs").fetchone()[0]

    assert seed_count == 3
    assert npc_count == 3
    assert relationship_count == 7
    assert memory_count == 3
    assert event_count == 0
    assert belief_count == 0
