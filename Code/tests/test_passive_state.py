import json
import sqlite3

from app.passive_state import apply_passive_state_drift
from scripts.init_sqlite import DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR, initialize_connection


def test_apply_passive_state_drift_changes_needs() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        needs = apply_passive_state_drift(connection, "npc_guard_001")
        needs_json = connection.execute(
            "SELECT needs_json FROM npc_state WHERE npc_id = ?",
            ("npc_guard_001",),
        ).fetchone()[0]

    stored_needs = json.loads(needs_json)
    assert needs == stored_needs
    assert stored_needs["hunger"] == 37
    assert stored_needs["energy"] == 69
    assert stored_needs["social"] == 21


def test_apply_passive_state_drift_clamps_needs() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        connection.execute(
            """
            UPDATE npc_state
            SET needs_json = ?
            WHERE npc_id = ?
            """,
            (
                '{"energy":0,"hunger":100,"safety":80,"social":100}',
                "npc_guard_001",
            ),
        )
        connection.commit()

        needs = apply_passive_state_drift(connection, "npc_guard_001")

    assert needs["energy"] == 0
    assert needs["hunger"] == 100
    assert needs["social"] == 100
