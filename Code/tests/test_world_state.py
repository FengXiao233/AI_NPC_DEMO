import sqlite3

from app.event_processor import process_world_event
from app.state_repository import list_world_entities, list_world_resource_nodes, load_agent_state
from app.world_state import advance_entity_behaviors, ensure_intelligent_monster_npc, generate_random_world_events, refresh_world_resources
from scripts.init_sqlite import DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR, initialize_connection


def test_monster_event_spawns_visible_world_entity() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        result = process_world_event(
            connection,
            {
                "event_id": "evt_world_spawn_monster",
                "event_type": "monster_appeared",
                "actor_id": "monster_wolf_alpha",
                "target_id": None,
                "location_id": "village_gate",
                "payload": {"monster_kind": "wolf", "monster_id": "monster_wolf_alpha", "count": 2},
                "importance": 70,
                "created_at_tick": 180,
            },
        )
        entities = list_world_entities(connection, location_id="village_gate")

    assert result.spawned_entity_ids == ["monster_wolf_alpha"]
    assert entities[0].entity_id == "monster_wolf_alpha"
    assert entities[0].entity_type == "monster"
    assert entities[0].quantity == 2
    assert entities[0].faction == "monster"
    assert entities[0].hostility > 0
    assert entities[0].intelligence < 70
    assert entities[0].health == entities[0].max_health


def test_intelligent_monster_event_creates_npc_template() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        process_world_event(
            connection,
            {
                "event_id": "evt_world_spawn_shaman",
                "event_type": "monster_appeared",
                "actor_id": "monster_shaman_alpha",
                "target_id": "npc_merchant_001",
                "location_id": "forest_edge",
                "payload": {"monster_kind": "goblin_shaman", "monster_id": "monster_shaman_alpha", "count": 1},
                "importance": 82,
                "created_at_tick": 190,
            },
        )
        entities = list_world_entities(connection, location_id="forest_edge")
        monster_state = load_agent_state(connection, "npc_monster_shaman_alpha")

    entity = next(item for item in entities if item.entity_id == "monster_shaman_alpha")
    assert entity.intelligence >= 70
    assert entity.behavior == "npc_controlled"
    assert entity.payload["npc_id"] == "npc_monster_shaman_alpha"
    assert monster_state is not None
    assert monster_state.role == "monster"
    assert monster_state.current_task.task_type == "hunt"


def test_intelligent_monster_sync_does_not_rewind_runtime_tick() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        process_world_event(
            connection,
            {
                "event_id": "evt_world_spawn_shaman_runtime",
                "event_type": "monster_appeared",
                "actor_id": "monster_shaman_runtime",
                "target_id": "npc_merchant_001",
                "location_id": "forest_edge",
                "payload": {"monster_kind": "goblin_shaman", "monster_id": "monster_shaman_runtime", "count": 1},
                "importance": 82,
                "created_at_tick": 190,
            },
        )
        connection.execute(
            """
            UPDATE npc_state
            SET runtime_flags_json = ?
            WHERE npc_id = ?
            """,
            (
                '{"is_critical_npc":true,"priority_tier":"high","thought_cooldown_ticks":8,"last_thought_tick":220,"last_plan_tick":210}',
                "npc_monster_shaman_runtime",
            ),
        )
        entity = next(item for item in list_world_entities(connection) if item.entity_id == "monster_shaman_runtime")
        ensure_intelligent_monster_npc(connection, entity)
        monster_state = load_agent_state(connection, "npc_monster_shaman_runtime")

    assert monster_state is not None
    assert monster_state.runtime_flags.last_thought_tick == 220


def test_resource_refresh_replenishes_depleted_nodes_after_cooldown() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        connection.execute(
            """
            UPDATE world_resource_nodes
            SET available_quantity = ?, last_harvested_tick = ?
            WHERE node_id = ?
            """,
            (1, 10, "res_forest_berries"),
        )
        connection.commit()

        refreshes = refresh_world_resources(connection, current_tick=20)
        resources = list_world_resource_nodes(connection, location_id="forest_edge", include_depleted=True)

    berry_node = next(node for node in resources if node.node_id == "res_forest_berries")
    assert any(item.node_id == "res_forest_berries" for item in refreshes)
    assert berry_node.available_quantity > 1


def test_random_world_event_generation_is_deterministic_by_tick() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        events = generate_random_world_events(connection, current_tick=180)

    assert [event.event_type for event in events] == ["monster_appeared", "traveler_arrived"]


def test_monster_behavior_escalates_to_attack_when_npc_stays_in_same_location() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        process_world_event(
            connection,
            {
                "event_id": "evt_world_behavior_monster",
                "event_type": "monster_appeared",
                "actor_id": "monster_behavior_wolf",
                "target_id": None,
                "location_id": "market",
                "payload": {"monster_kind": "wolf", "monster_id": "monster_behavior_wolf", "count": 1},
                "importance": 72,
                "created_at_tick": 180,
            },
        )
        connection.execute(
            "UPDATE npc_state SET location_id = ? WHERE npc_id = ?",
            ("market", "npc_guard_001"),
        )
        connection.commit()

        first_events = advance_entity_behaviors(connection, current_tick=181)
        second_events = advance_entity_behaviors(connection, current_tick=184)
        entity_row = connection.execute(
            "SELECT state FROM world_entities WHERE entity_id = ?",
            ("monster_behavior_wolf",),
        ).fetchone()

    assert first_events == []
    assert [event.event_type for event in second_events] == ["attack"]
    assert second_events[0].target_id == "npc_merchant_001"
    assert entity_row == ("attacking",)
