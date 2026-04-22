PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS npc_state (
    npc_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    location_id TEXT NOT NULL,
    base_attributes_json TEXT NOT NULL,
    personality_json TEXT NOT NULL,
    needs_json TEXT NOT NULL,
    current_task_json TEXT NOT NULL,
    task_queue_json TEXT NOT NULL,
    message_queue_json TEXT NOT NULL,
    learning_bias_json TEXT NOT NULL,
    runtime_flags_json TEXT NOT NULL,
    updated_at_tick INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS relationships (
    npc_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    favor INTEGER NOT NULL CHECK (favor BETWEEN -100 AND 100),
    trust INTEGER NOT NULL CHECK (trust BETWEEN -100 AND 100),
    hostility INTEGER NOT NULL CHECK (hostility BETWEEN 0 AND 100),
    PRIMARY KEY (npc_id, target_id),
    FOREIGN KEY (npc_id) REFERENCES npc_state(npc_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memories (
    memory_id TEXT PRIMARY KEY,
    npc_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    importance INTEGER NOT NULL CHECK (importance BETWEEN 0 AND 100),
    related_ids_json TEXT NOT NULL,
    created_at_tick INTEGER NOT NULL CHECK (created_at_tick >= 0),
    expires_at_tick INTEGER CHECK (expires_at_tick IS NULL OR expires_at_tick >= created_at_tick),
    FOREIGN KEY (npc_id) REFERENCES npc_state(npc_id) ON DELETE CASCADE
);

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
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    actor_id TEXT,
    target_id TEXT,
    location_id TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    importance INTEGER NOT NULL DEFAULT 0 CHECK (importance BETWEEN 0 AND 100),
    created_at_tick INTEGER NOT NULL CHECK (created_at_tick >= 0)
);

CREATE TABLE IF NOT EXISTS npc_inventory (
    item_id TEXT PRIMARY KEY,
    npc_id TEXT NOT NULL,
    item_type TEXT NOT NULL,
    item_name TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity BETWEEN 0 AND 999),
    source_location_id TEXT,
    updated_at_tick INTEGER NOT NULL CHECK (updated_at_tick >= 0),
    FOREIGN KEY (npc_id) REFERENCES npc_state(npc_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS village_warehouse (
    item_id TEXT PRIMARY KEY,
    item_type TEXT NOT NULL,
    item_name TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity BETWEEN 0 AND 999),
    updated_at_tick INTEGER NOT NULL CHECK (updated_at_tick >= 0)
);

CREATE TABLE IF NOT EXISTS village_warehouse_transactions (
    transaction_id TEXT PRIMARY KEY,
    actor_id TEXT,
    item_type TEXT NOT NULL,
    item_name TEXT NOT NULL,
    quantity_delta INTEGER NOT NULL CHECK (quantity_delta BETWEEN -999 AND 999),
    reason TEXT NOT NULL,
    created_at_tick INTEGER NOT NULL CHECK (created_at_tick >= 0)
);

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
);

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
);

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
);

CREATE INDEX IF NOT EXISTS idx_relationships_target_id
    ON relationships(target_id);

CREATE INDEX IF NOT EXISTS idx_memories_npc_tick
    ON memories(npc_id, created_at_tick);

CREATE INDEX IF NOT EXISTS idx_npc_beliefs_npc_topic
    ON npc_beliefs(npc_id, topic_hint, created_at_tick);

CREATE INDEX IF NOT EXISTS idx_events_tick
    ON events(created_at_tick);

CREATE INDEX IF NOT EXISTS idx_npc_inventory_npc_type
    ON npc_inventory(npc_id, item_type);

CREATE INDEX IF NOT EXISTS idx_village_warehouse_type
    ON village_warehouse(item_type);

CREATE INDEX IF NOT EXISTS idx_village_warehouse_transactions_tick
    ON village_warehouse_transactions(created_at_tick, item_type);

CREATE INDEX IF NOT EXISTS idx_village_production_orders_status_tick
    ON village_production_orders(status, completes_at_tick);

CREATE INDEX IF NOT EXISTS idx_world_resource_nodes_location
    ON world_resource_nodes(location_id, resource_type);

CREATE INDEX IF NOT EXISTS idx_world_entities_location
    ON world_entities(location_id, entity_type, state);
