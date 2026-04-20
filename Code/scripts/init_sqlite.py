import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "sqlite" / "npc_social_rpg.sqlite3"
DEFAULT_SCHEMA_PATH = PROJECT_ROOT / "data" / "sqlite" / "schema.sql"
DEFAULT_SEED_DIR = PROJECT_ROOT / "seeds" / "npcs"


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def apply_schema(connection: sqlite3.Connection, schema_path: Path = DEFAULT_SCHEMA_PATH) -> None:
    connection.executescript(schema_path.read_text(encoding="utf-8"))
    ensure_memory_expiration_column(connection)
    ensure_npc_beliefs_table(connection)


def ensure_memory_expiration_column(connection: sqlite3.Connection) -> None:
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(memories)")
    }
    if "expires_at_tick" not in columns:
        connection.execute("ALTER TABLE memories ADD COLUMN expires_at_tick INTEGER")


def ensure_npc_beliefs_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS npc_beliefs (
            belief_id TEXT PRIMARY KEY,
            npc_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            topic_hint TEXT,
            claim TEXT NOT NULL,
            confidence INTEGER NOT NULL CHECK (confidence BETWEEN 0 AND 100),
            truth_status TEXT NOT NULL CHECK (truth_status IN ('unverified', 'confirmed', 'disproven')),
            created_at_tick INTEGER NOT NULL CHECK (created_at_tick >= 0),
            expires_at_tick INTEGER CHECK (expires_at_tick IS NULL OR expires_at_tick >= created_at_tick),
            FOREIGN KEY (npc_id) REFERENCES npc_state(npc_id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_npc_beliefs_npc_topic
            ON npc_beliefs(npc_id, topic_hint, created_at_tick)
        """
    )


def seed_npc_states(connection: sqlite3.Connection, seed_dir: Path = DEFAULT_SEED_DIR) -> int:
    seed_count = 0
    for seed_path in sorted(seed_dir.glob("*.json")):
        npc = json.loads(seed_path.read_text(encoding="utf-8"))

        connection.execute(
            """
            INSERT INTO npc_state (
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
                runtime_flags_json,
                updated_at_tick
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(npc_id) DO UPDATE SET
                name = excluded.name,
                role = excluded.role,
                location_id = excluded.location_id,
                base_attributes_json = excluded.base_attributes_json,
                personality_json = excluded.personality_json,
                needs_json = excluded.needs_json,
                current_task_json = excluded.current_task_json,
                task_queue_json = excluded.task_queue_json,
                message_queue_json = excluded.message_queue_json,
                learning_bias_json = excluded.learning_bias_json,
                runtime_flags_json = excluded.runtime_flags_json,
                updated_at_tick = excluded.updated_at_tick
            """,
            (
                npc["npc_id"],
                npc["name"],
                npc["role"],
                npc["location_id"],
                dump_json(npc["base_attributes"]),
                dump_json(npc["personality"]),
                dump_json(npc["needs"]),
                dump_json(npc["current_task"]),
                dump_json(npc["task_queue"]),
                dump_json(npc["message_queue"]),
                dump_json(npc["learning_bias"]),
                dump_json(npc["runtime_flags"]),
                npc["runtime_flags"].get("last_thought_tick", 0),
            ),
        )

        for relationship in npc["relationships"]:
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
                    npc["npc_id"],
                    relationship["target_id"],
                    relationship["favor"],
                    relationship["trust"],
                    relationship["hostility"],
                ),
            )

        for memory in npc["memory_summary"]:
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
                    memory["memory_id"],
                    npc["npc_id"],
                    memory["summary"],
                    memory["importance"],
                    dump_json(memory["related_ids"]),
                    memory["created_at_tick"],
                    memory.get("expires_at_tick"),
                ),
            )

        seed_count += 1

    return seed_count


def initialize_database(
    db_path: Path = DEFAULT_DB_PATH,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
    seed_dir: Path | None = DEFAULT_SEED_DIR,
) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        return initialize_connection(connection, schema_path, seed_dir)


def initialize_connection(
    connection: sqlite3.Connection,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
    seed_dir: Path | None = DEFAULT_SEED_DIR,
) -> int:
    connection.execute("PRAGMA foreign_keys = ON")
    apply_schema(connection, schema_path)
    seed_count = seed_npc_states(connection, seed_dir) if seed_dir else 0
    connection.commit()
    return seed_count


def reset_connection(
    connection: sqlite3.Connection,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
    seed_dir: Path | None = DEFAULT_SEED_DIR,
) -> int:
    connection.execute("PRAGMA foreign_keys = ON")
    apply_schema(connection, schema_path)
    connection.execute("DELETE FROM events")
    connection.execute("DELETE FROM npc_beliefs")
    connection.execute("DELETE FROM memories")
    connection.execute("DELETE FROM relationships")
    connection.execute("DELETE FROM npc_state")
    seed_count = seed_npc_states(connection, seed_dir) if seed_dir else 0
    connection.commit()
    return seed_count


def reset_database(
    db_path: Path = DEFAULT_DB_PATH,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
    seed_dir: Path | None = DEFAULT_SEED_DIR,
) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        return reset_connection(connection, schema_path, seed_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize the NPC social RPG SQLite database.")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--schema-path", type=Path, default=DEFAULT_SCHEMA_PATH)
    parser.add_argument("--seed-dir", type=Path, default=DEFAULT_SEED_DIR)
    parser.add_argument("--no-seed", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    seed_dir = None if args.no_seed else args.seed_dir
    seed_count = initialize_database(args.db_path, args.schema_path, seed_dir)
    print(f"Initialized SQLite database: {args.db_path}")
    print(f"Seeded NPC states: {seed_count}")


if __name__ == "__main__":
    main()
