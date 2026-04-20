import sqlite3

from app.event_processor import process_world_event
from app.models import AgentState, NpcBelief
from app.state_repository import (
    list_belief_records,
    list_event_records,
    list_memory_records,
    list_npc_ids,
    load_agent_state,
    load_all_agent_states,
    upsert_npc_belief,
)
from scripts.init_sqlite import DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR, initialize_connection


def test_load_agent_state_rebuilds_state_from_sqlite() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        agent_state = load_agent_state(connection, "npc_merchant_001")

    assert isinstance(agent_state, AgentState)
    assert agent_state.npc_id == "npc_merchant_001"
    assert agent_state.role == "merchant"
    assert {relationship.target_id for relationship in agent_state.relationships} == {
        "npc_guard_001",
        "npc_hunter_001",
        "player_001",
    }


def test_load_all_agent_states_returns_seed_npcs() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        npc_ids = list_npc_ids(connection)
        agent_states = load_all_agent_states(connection)

    assert npc_ids == ["npc_guard_001", "npc_hunter_001", "npc_merchant_001"]
    assert [agent_state.npc_id for agent_state in agent_states] == npc_ids


def test_load_agent_state_includes_routed_memories_and_filters_expired() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        process_world_event(
            connection,
            {
                "event_id": "evt_repo_food_market_001",
                "event_type": "food_shortage",
                "actor_id": None,
                "target_id": None,
                "location_id": "market",
                "payload": {"related_ids": ["npc_merchant_001"]},
                "importance": 45,
                "created_at_tick": 150,
            },
        )
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
            """,
            (
                "mem_expired",
                "npc_merchant_001",
                "This memory should be filtered.",
                100,
                '["npc_merchant_001"]',
                1,
                50,
            ),
        )
        connection.execute(
            """
            UPDATE npc_state
            SET runtime_flags_json = ?
            WHERE npc_id = ?
            """,
            (
                '{"is_critical_npc":true,"thought_cooldown_ticks":20,"last_thought_tick":100}',
                "npc_merchant_001",
            ),
        )
        connection.commit()

        agent_state = load_agent_state(connection, "npc_merchant_001")

    assert "mem_npc_merchant_001_evt_repo_food_market_001" in {
        memory.memory_id for memory in agent_state.memory_summary
    }
    assert "mem_expired" not in {memory.memory_id for memory in agent_state.memory_summary}


def test_list_event_records_returns_recent_events() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        process_world_event(
            connection,
            {
                "event_id": "evt_repo_monster_gate_001",
                "event_type": "monster_appeared",
                "actor_id": "monster_wolf_001",
                "target_id": None,
                "location_id": "village_gate",
                "payload": {"severity": "low"},
                "importance": 60,
                "created_at_tick": 150,
            },
        )

        event_records = list_event_records(connection)

    assert event_records[0].event_id == "evt_repo_monster_gate_001"
    assert event_records[0].payload["severity"] == "low"
    assert event_records[0].payload["_category"] == "monster_incursion"


def test_list_memory_records_can_include_or_filter_expired_memories() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
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
            """,
            (
                "mem_repo_active",
                "npc_guard_001",
                "A fresh warning near the gate.",
                70,
                '["village_gate"]',
                90,
                130,
            ),
        )
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
            """,
            (
                "mem_repo_expired",
                "npc_guard_001",
                "An old rumor has faded.",
                80,
                '["market"]',
                10,
                50,
            ),
        )
        connection.commit()

        active_memories = list_memory_records(
            connection,
            "npc_guard_001",
            current_tick=100,
            include_expired=False,
        )
        all_memories = list_memory_records(
            connection,
            "npc_guard_001",
            current_tick=100,
            include_expired=True,
        )

    active_memory_ids = {memory.memory_id for memory in active_memories}
    all_memory_ids = {memory.memory_id for memory in all_memories}
    assert "mem_repo_active" in active_memory_ids
    assert "mem_repo_expired" not in active_memory_ids
    assert {"mem_repo_active", "mem_repo_expired"}.issubset(all_memory_ids)


def test_list_belief_records_can_include_or_filter_expired_beliefs() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        upsert_npc_belief(
            connection,
            "npc_guard_001",
            NpcBelief(
                belief_id="belief_repo_active",
                source_type="player_utterance",
                source_id="msg_active",
                topic_hint="monster_threat",
                claim="There may be a monster near the gate.",
                confidence=70,
                truth_status="unverified",
                created_at_tick=90,
                expires_at_tick=130,
            ),
        )
        upsert_npc_belief(
            connection,
            "npc_guard_001",
            NpcBelief(
                belief_id="belief_repo_expired",
                source_type="player_utterance",
                source_id="msg_expired",
                topic_hint="suspicious_arrival",
                claim="An old suspicious arrival rumor.",
                confidence=80,
                truth_status="unverified",
                created_at_tick=10,
                expires_at_tick=50,
            ),
        )
        connection.execute(
            """
            UPDATE npc_state
            SET runtime_flags_json = ?
            WHERE npc_id = ?
            """,
            (
                '{"is_critical_npc":true,"thought_cooldown_ticks":10,"last_thought_tick":100}',
                "npc_guard_001",
            ),
        )
        connection.commit()

        active_beliefs = list_belief_records(
            connection,
            "npc_guard_001",
            current_tick=100,
            include_expired=False,
        )
        all_beliefs = list_belief_records(
            connection,
            "npc_guard_001",
            current_tick=100,
            include_expired=True,
        )
        agent_state = load_agent_state(connection, "npc_guard_001")

    active_belief_ids = {belief.belief_id for belief in active_beliefs}
    all_belief_ids = {belief.belief_id for belief in all_beliefs}
    assert "belief_repo_active" in active_belief_ids
    assert "belief_repo_expired" not in active_belief_ids
    assert {"belief_repo_active", "belief_repo_expired"}.issubset(all_belief_ids)
    assert agent_state is not None
    assert [belief.belief_id for belief in agent_state.beliefs] == ["belief_repo_active"]
