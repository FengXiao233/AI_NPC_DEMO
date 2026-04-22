import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "sqlite" / "npc_social_rpg.sqlite3"
DEFAULT_SCHEMA_PATH = PROJECT_ROOT / "data" / "sqlite" / "schema.sql"
DEFAULT_SEED_DIR = PROJECT_ROOT / "seeds" / "npcs"
DEFAULT_WORLD_RESOURCE_SEEDS = [
    {
        "node_id": "res_village_fields",
        "location_id": "village_square",
        "resource_type": "grain_field",
        "display_name": "Village grain fields",
        "available_quantity": 4,
        "max_quantity": 12,
        "respawn_rate": 1,
        "cooldown_ticks": 6,
        "metadata": {"item_type": "grain", "yield_quantity": 2},
    },
    {
        "node_id": "res_market_supplies",
        "location_id": "market",
        "resource_type": "food_crate",
        "display_name": "Market food crates",
        "available_quantity": 6,
        "max_quantity": 8,
        "respawn_rate": 2,
        "cooldown_ticks": 4,
        "metadata": {"item_type": "rations", "yield_quantity": 2},
    },
    {
        "node_id": "res_forest_berries",
        "location_id": "forest_edge",
        "resource_type": "berries",
        "display_name": "Berry bushes",
        "available_quantity": 5,
        "max_quantity": 6,
        "respawn_rate": 2,
        "cooldown_ticks": 3,
        "metadata": {"item_type": "berries", "yield_quantity": 2},
    },
    {
        "node_id": "res_forest_herbs",
        "location_id": "forest_edge",
        "resource_type": "herbs",
        "display_name": "Medicinal herbs",
        "available_quantity": 4,
        "max_quantity": 5,
        "respawn_rate": 1,
        "cooldown_ticks": 4,
        "metadata": {"item_type": "herbs", "yield_quantity": 1},
    },
]
DEFAULT_WAREHOUSE_SEEDS = [
    {"item_id": "warehouse_rations", "item_type": "rations", "item_name": "Shared rations", "quantity": 8},
    {"item_id": "warehouse_grain_seed", "item_type": "grain_seed", "item_name": "Grain seed", "quantity": 6},
    {"item_id": "warehouse_grain", "item_type": "grain", "item_name": "Stored grain", "quantity": 6},
    {"item_id": "warehouse_ore", "item_type": "ore", "item_name": "Bog iron ore", "quantity": 6},
    {"item_id": "warehouse_herbs", "item_type": "herbs", "item_name": "Medicinal herbs", "quantity": 3},
    {"item_id": "warehouse_coin", "item_type": "coin", "item_name": "Village coin reserve", "quantity": 20},
]
DEFAULT_INVENTORY_SEEDS = {
    "npc_guard_001": [
        {"item_id": "inv_guard_rations", "item_type": "rations", "item_name": "Guard rations", "quantity": 2},
    ],
    "npc_hunter_001": [
        {"item_id": "inv_hunter_meat", "item_type": "meat", "item_name": "Fresh meat", "quantity": 1},
        {"item_id": "inv_hunter_hide", "item_type": "hide", "item_name": "Animal hide", "quantity": 1},
    ],
    "npc_merchant_001": [
        {"item_id": "inv_merchant_rations", "item_type": "rations", "item_name": "Travel rations", "quantity": 4},
        {"item_id": "inv_merchant_coin", "item_type": "coin", "item_name": "Coin pouch", "quantity": 12},
    ],
}


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def apply_schema(connection: sqlite3.Connection, schema_path: Path = DEFAULT_SCHEMA_PATH) -> None:
    connection.executescript(schema_path.read_text(encoding="utf-8"))
    ensure_memory_expiration_column(connection)
    ensure_npc_beliefs_table(connection)
    ensure_dialogue_tables(connection)
    ensure_world_state_tables(connection)


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


def ensure_dialogue_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS dialogue_turns (
            turn_id TEXT PRIMARY KEY,
            npc_id TEXT NOT NULL,
            speaker_id TEXT NOT NULL,
            speaker_label TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('player', 'npc')),
            content TEXT NOT NULL,
            created_at_tick INTEGER NOT NULL CHECK (created_at_tick >= 0),
            FOREIGN KEY (npc_id) REFERENCES npc_state(npc_id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS dialogue_sessions (
            npc_id TEXT NOT NULL,
            speaker_id TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            total_turn_count INTEGER NOT NULL DEFAULT 0 CHECK (total_turn_count >= 0),
            updated_at_tick INTEGER CHECK (updated_at_tick IS NULL OR updated_at_tick >= 0),
            PRIMARY KEY (npc_id, speaker_id),
            FOREIGN KEY (npc_id) REFERENCES npc_state(npc_id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dialogue_turns_npc_speaker_tick
            ON dialogue_turns(npc_id, speaker_id, created_at_tick)
        """
    )


def ensure_world_state_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS npc_inventory (
            item_id TEXT PRIMARY KEY,
            npc_id TEXT NOT NULL,
            item_type TEXT NOT NULL,
            item_name TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK (quantity BETWEEN 0 AND 999),
            source_location_id TEXT,
            updated_at_tick INTEGER NOT NULL CHECK (updated_at_tick >= 0),
            FOREIGN KEY (npc_id) REFERENCES npc_state(npc_id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS world_resource_nodes (
            node_id TEXT PRIMARY KEY,
            location_id TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            display_name TEXT NOT NULL,
            available_quantity INTEGER NOT NULL CHECK (available_quantity BETWEEN 0 AND 999),
            max_quantity INTEGER NOT NULL CHECK (max_quantity BETWEEN 0 AND 999),
            respawn_rate INTEGER NOT NULL CHECK (respawn_rate BETWEEN 0 AND 100),
            cooldown_ticks INTEGER NOT NULL CHECK (cooldown_ticks >= 0),
            last_harvested_tick INTEGER NOT NULL DEFAULT 0 CHECK (last_harvested_tick >= 0),
            last_refreshed_tick INTEGER NOT NULL DEFAULT 0 CHECK (last_refreshed_tick >= 0),
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS village_warehouse (
            item_id TEXT PRIMARY KEY,
            item_type TEXT NOT NULL,
            item_name TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK (quantity BETWEEN 0 AND 999),
            updated_at_tick INTEGER NOT NULL CHECK (updated_at_tick >= 0)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS village_warehouse_transactions (
            transaction_id TEXT PRIMARY KEY,
            actor_id TEXT,
            item_type TEXT NOT NULL,
            item_name TEXT NOT NULL,
            quantity_delta INTEGER NOT NULL CHECK (quantity_delta BETWEEN -999 AND 999),
            reason TEXT NOT NULL,
            created_at_tick INTEGER NOT NULL CHECK (created_at_tick >= 0)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS village_production_orders (
            order_id TEXT PRIMARY KEY,
            actor_id TEXT NOT NULL,
            order_type TEXT NOT NULL,
            status TEXT NOT NULL,
            input_item_type TEXT,
            input_quantity INTEGER NOT NULL CHECK (input_quantity BETWEEN 0 AND 999),
            output_item_type TEXT NOT NULL,
            output_item_name TEXT NOT NULL,
            output_quantity INTEGER NOT NULL CHECK (output_quantity BETWEEN 1 AND 999),
            started_at_tick INTEGER NOT NULL CHECK (started_at_tick >= 0),
            completes_at_tick INTEGER NOT NULL CHECK (completes_at_tick >= started_at_tick),
            payload_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS world_entities (
            entity_id TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            display_name TEXT NOT NULL,
            location_id TEXT NOT NULL,
            state TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK (quantity BETWEEN 0 AND 999),
            threat_level INTEGER NOT NULL DEFAULT 0 CHECK (threat_level BETWEEN 0 AND 100),
            faction TEXT NOT NULL DEFAULT 'neutral',
            health INTEGER NOT NULL DEFAULT 1 CHECK (health BETWEEN 0 AND 999),
            max_health INTEGER NOT NULL DEFAULT 1 CHECK (max_health BETWEEN 1 AND 999),
            hostility INTEGER NOT NULL DEFAULT 0 CHECK (hostility BETWEEN 0 AND 100),
            aggression INTEGER NOT NULL DEFAULT 0 CHECK (aggression BETWEEN 0 AND 100),
            intelligence INTEGER NOT NULL DEFAULT 0 CHECK (intelligence BETWEEN 0 AND 100),
            awareness INTEGER NOT NULL DEFAULT 0 CHECK (awareness BETWEEN 0 AND 100),
            morale INTEGER NOT NULL DEFAULT 50 CHECK (morale BETWEEN 0 AND 100),
            attack_power INTEGER NOT NULL DEFAULT 0 CHECK (attack_power BETWEEN 0 AND 100),
            defense INTEGER NOT NULL DEFAULT 0 CHECK (defense BETWEEN 0 AND 100),
            target_id TEXT,
            behavior TEXT NOT NULL DEFAULT 'static',
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at_tick INTEGER NOT NULL CHECK (created_at_tick >= 0),
            updated_at_tick INTEGER NOT NULL CHECK (updated_at_tick >= 0)
        )
        """
    )
    ensure_world_entity_columns(connection)
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_npc_inventory_npc_type
            ON npc_inventory(npc_id, item_type)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_village_warehouse_type
            ON village_warehouse(item_type)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_village_warehouse_transactions_tick
            ON village_warehouse_transactions(created_at_tick, item_type)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_village_production_orders_status_tick
            ON village_production_orders(status, completes_at_tick)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_world_resource_nodes_location
            ON world_resource_nodes(location_id, resource_type)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_world_entities_location
            ON world_entities(location_id, entity_type, state)
        """
    )


def ensure_world_entity_columns(connection: sqlite3.Connection) -> None:
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(world_entities)")
    }
    column_defaults = {
        "faction": "TEXT NOT NULL DEFAULT 'neutral'",
        "health": "INTEGER NOT NULL DEFAULT 1 CHECK (health BETWEEN 0 AND 999)",
        "max_health": "INTEGER NOT NULL DEFAULT 1 CHECK (max_health BETWEEN 1 AND 999)",
        "hostility": "INTEGER NOT NULL DEFAULT 0 CHECK (hostility BETWEEN 0 AND 100)",
        "aggression": "INTEGER NOT NULL DEFAULT 0 CHECK (aggression BETWEEN 0 AND 100)",
        "intelligence": "INTEGER NOT NULL DEFAULT 0 CHECK (intelligence BETWEEN 0 AND 100)",
        "awareness": "INTEGER NOT NULL DEFAULT 0 CHECK (awareness BETWEEN 0 AND 100)",
        "morale": "INTEGER NOT NULL DEFAULT 50 CHECK (morale BETWEEN 0 AND 100)",
        "attack_power": "INTEGER NOT NULL DEFAULT 0 CHECK (attack_power BETWEEN 0 AND 100)",
        "defense": "INTEGER NOT NULL DEFAULT 0 CHECK (defense BETWEEN 0 AND 100)",
        "target_id": "TEXT",
    }
    for column_name, column_sql in column_defaults.items():
        if column_name not in columns:
            connection.execute(f"ALTER TABLE world_entities ADD COLUMN {column_name} {column_sql}")


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


def seed_world_state(connection: sqlite3.Connection) -> None:
    for npc_id, items in DEFAULT_INVENTORY_SEEDS.items():
        for item in items:
            connection.execute(
                """
                INSERT INTO npc_inventory (
                    item_id,
                    npc_id,
                    item_type,
                    item_name,
                    quantity,
                    source_location_id,
                    updated_at_tick
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_id) DO UPDATE SET
                    npc_id = excluded.npc_id,
                    item_type = excluded.item_type,
                    item_name = excluded.item_name,
                    quantity = excluded.quantity,
                    source_location_id = excluded.source_location_id,
                    updated_at_tick = excluded.updated_at_tick
                """,
                (
                    item["item_id"],
                    npc_id,
                    item["item_type"],
                    item["item_name"],
                    item["quantity"],
                    None,
                    0,
                ),
            )
    for node in DEFAULT_WORLD_RESOURCE_SEEDS:
        connection.execute(
            """
            INSERT INTO world_resource_nodes (
                node_id,
                location_id,
                resource_type,
                display_name,
                available_quantity,
                max_quantity,
                respawn_rate,
                cooldown_ticks,
                last_harvested_tick,
                last_refreshed_tick,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
                location_id = excluded.location_id,
                resource_type = excluded.resource_type,
                display_name = excluded.display_name,
                available_quantity = excluded.available_quantity,
                max_quantity = excluded.max_quantity,
                respawn_rate = excluded.respawn_rate,
                cooldown_ticks = excluded.cooldown_ticks,
                last_harvested_tick = excluded.last_harvested_tick,
                last_refreshed_tick = excluded.last_refreshed_tick,
                metadata_json = excluded.metadata_json
            """,
            (
                node["node_id"],
                node["location_id"],
                node["resource_type"],
                node["display_name"],
                node["available_quantity"],
                node["max_quantity"],
                node["respawn_rate"],
                node["cooldown_ticks"],
                0,
                0,
                dump_json(node["metadata"]),
            ),
        )
    for item in DEFAULT_WAREHOUSE_SEEDS:
        connection.execute(
            """
            INSERT INTO village_warehouse (
                item_id,
                item_type,
                item_name,
                quantity,
                updated_at_tick
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(item_id) DO UPDATE SET
                item_type = excluded.item_type,
                item_name = excluded.item_name,
                quantity = excluded.quantity,
                updated_at_tick = excluded.updated_at_tick
            """,
            (
                item["item_id"],
                item["item_type"],
                item["item_name"],
                item["quantity"],
                0,
            ),
        )


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
    seed_world_state(connection)
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
    connection.execute("DELETE FROM dialogue_turns")
    connection.execute("DELETE FROM dialogue_sessions")
    connection.execute("DELETE FROM world_entities")
    connection.execute("DELETE FROM world_resource_nodes")
    connection.execute("DELETE FROM village_production_orders")
    connection.execute("DELETE FROM village_warehouse_transactions")
    connection.execute("DELETE FROM village_warehouse")
    connection.execute("DELETE FROM npc_inventory")
    connection.execute("DELETE FROM memories")
    connection.execute("DELETE FROM relationships")
    connection.execute("DELETE FROM npc_state")
    seed_count = seed_npc_states(connection, seed_dir) if seed_dir else 0
    seed_world_state(connection)
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
