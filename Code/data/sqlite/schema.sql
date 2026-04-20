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

CREATE INDEX IF NOT EXISTS idx_relationships_target_id
    ON relationships(target_id);

CREATE INDEX IF NOT EXISTS idx_memories_npc_tick
    ON memories(npc_id, created_at_tick);

CREATE INDEX IF NOT EXISTS idx_npc_beliefs_npc_topic
    ON npc_beliefs(npc_id, topic_hint, created_at_tick);

CREATE INDEX IF NOT EXISTS idx_events_tick
    ON events(created_at_tick);
