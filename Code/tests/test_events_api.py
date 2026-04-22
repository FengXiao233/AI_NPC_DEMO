import sqlite3

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from app.simulation_engine import SimulationBusyError
from scripts.init_sqlite import DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR, initialize_connection


SEEDED_NPC_IDS = [
    "npc_blacksmith_001",
    "npc_farmer_001",
    "npc_guard_001",
    "npc_hunter_001",
    "npc_merchant_001",
    "npc_physician_001",
    "npc_village_chief_001",
]


def test_events_endpoint_accepts_world_event() -> None:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

    try:
        app.state.db_connection = connection
        with TestClient(app) as client:
            response = client.post(
                "/events",
                json={
                    "event_id": "evt_api_monster_gate_001",
                    "event_type": "monster_appeared",
                    "actor_id": "monster_wolf_001",
                    "target_id": None,
                    "location_id": "village_gate",
                    "payload": {},
                    "importance": 60,
                    "created_at_tick": 180,
                },
            )

        assert response.status_code == 200
        assert response.json()["recipient_npc_ids"] == SEEDED_NPC_IDS
    finally:
        del app.state.db_connection
        connection.close()


def test_event_log_endpoint_returns_stored_events() -> None:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

    try:
        app.state.db_connection = connection
        with TestClient(app) as client:
            ingest_response = client.post(
                "/events",
                json={
                    "event_id": "evt_api_log_monster_001",
                    "event_type": "monster_appeared",
                    "actor_id": "monster_wolf_001",
                    "target_id": None,
                    "location_id": "village_gate",
                    "payload": {"severity": "low"},
                    "importance": 60,
                    "created_at_tick": 180,
                },
            )
            log_response = client.get("/events")

        assert ingest_response.status_code == 200
        assert log_response.status_code == 200
        assert log_response.json()[0]["event_id"] == "evt_api_log_monster_001"
        assert log_response.json()[0]["payload"]["severity"] == "low"
        assert log_response.json()[0]["payload"]["_category"] == "monster_incursion"
    finally:
        del app.state.db_connection
        connection.close()


def test_event_catalog_endpoint_returns_metadata_for_godot_visualization() -> None:
    with TestClient(app) as client:
        response = client.get("/event-catalog")

    assert response.status_code == 200
    monster_entry = next(item for item in response.json() if item["event_type"] == "monster_appeared")
    assert monster_entry["category"] == "monster_incursion"
    assert "monster_kind" in monster_entry["payload_fields"]
    assert any(
        role_response["role"] == "guard"
        and role_response["task_type"] == "patrol"
        for role_response in monster_entry["default_role_responses"]
    )
    traveler_entry = next(item for item in response.json() if item["event_type"] == "traveler_arrived")
    assert traveler_entry["category"] == "visitor_activity"


def test_player_utterance_endpoint_queues_claim_for_npc() -> None:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

    try:
        app.state.db_connection = connection
        with TestClient(app) as client:
            response = client.post(
                "/npcs/npc_guard_001/utterances",
                json={
                    "speaker_id": "player_001",
                    "content": "村口来了一个很奇怪的商人。",
                    "created_at_tick": 210,
                },
            )
            state_response = client.get("/npcs/npc_guard_001")

        assert response.status_code == 200
        assert response.json()["topic_hint"] == "suspicious_arrival"
        assert response.json()["queued_message"]["message_type"] == "player_utterance"
        assert state_response.json()["message_queue"][0]["content"] == "村口来了一个很奇怪的商人。"
    finally:
        del app.state.db_connection
        connection.close()


def test_dialogue_history_endpoint_returns_recent_turns_and_summary() -> None:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

    try:
        app.state.db_connection = connection
        with TestClient(app) as client:
            for index in range(4):
                response = client.post(
                    "/npcs/npc_guard_001/utterances",
                    json={
                        "speaker_id": "player_001",
                        "content": f"Tell me update number {index + 1} about the gate.",
                        "created_at_tick": 230 + index,
                        "message_id": f"msg_api_dialogue_{index + 1}",
                    },
                )
                assert response.status_code == 200

            history_response = client.get("/npcs/npc_guard_001/dialogue-history?speaker_id=player_001")

        assert history_response.status_code == 200
        payload = history_response.json()
        assert payload["npc_id"] == "npc_guard_001"
        assert payload["speaker_id"] == "player_001"
        assert payload["total_turn_count"] == 8
        assert len(payload["recent_turns"]) == 6
        assert payload["summary"] != ""
    finally:
        del app.state.db_connection
        connection.close()


def test_npc_state_endpoints_return_sqlite_state() -> None:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

    try:
        app.state.db_connection = connection
        with TestClient(app) as client:
            list_response = client.get("/npcs")
            state_response = client.get("/npcs/npc_hunter_001")
            missing_response = client.get("/npcs/missing_npc")

        assert list_response.status_code == 200
        assert [item["npc_id"] for item in list_response.json()] == SEEDED_NPC_IDS
        assert state_response.status_code == 200
        assert state_response.json()["npc_id"] == "npc_hunter_001"
        assert missing_response.status_code == 404
    finally:
        del app.state.db_connection
        connection.close()


def test_npc_memories_endpoint_returns_routed_memory_records() -> None:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

    try:
        app.state.db_connection = connection
        with TestClient(app) as client:
            event_response = client.post(
                "/events",
                json={
                    "event_id": "evt_api_guard_memory_001",
                    "event_type": "monster_appeared",
                    "actor_id": "monster_wolf_001",
                    "target_id": None,
                    "location_id": "village_gate",
                    "payload": {},
                    "importance": 60,
                    "created_at_tick": 180,
                },
            )
            memory_response = client.get("/npcs/npc_guard_001/memories")
            missing_response = client.get("/npcs/missing_npc/memories")

        assert event_response.status_code == 200
        assert memory_response.status_code == 200
        assert memory_response.json()[0]["npc_id"] == "npc_guard_001"
        assert memory_response.json()[0]["memory_id"] == "mem_npc_guard_001_evt_api_guard_memory_001"
        assert missing_response.status_code == 404
    finally:
        del app.state.db_connection
        connection.close()


def test_npc_thought_endpoint_reads_sqlite_memory() -> None:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

    try:
        app.state.db_connection = connection
        with TestClient(app) as client:
            event_response = client.post(
                "/events",
                json={
                    "event_id": "evt_api_food_market_001",
                    "event_type": "food_shortage",
                    "actor_id": None,
                    "target_id": None,
                    "location_id": "market",
                    "payload": {"related_ids": ["npc_merchant_001"]},
                    "importance": 45,
                    "created_at_tick": 180,
                },
            )
            thought_response = client.get("/npcs/npc_merchant_001/thought")

        assert event_response.status_code == 200
        assert thought_response.status_code == 200
        assert any(
            focus["target_id"] == "market"
            for focus in thought_response.json()["target_focus"]
        )
    finally:
        del app.state.db_connection
        connection.close()


def test_npc_plan_endpoint_updates_sqlite_task_queue() -> None:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

    try:
        app.state.db_connection = connection
        with TestClient(app) as client:
            response = client.post("/npcs/npc_hunter_001/plan")

        task_queue_json = connection.execute(
            "SELECT task_queue_json FROM npc_state WHERE npc_id = ?",
            ("npc_hunter_001",),
        ).fetchone()[0]

        assert response.status_code == 200
        assert response.json()["mode"] == "queued"
        assert any(task["task_type"] == "gather" for task in json_loads(task_queue_json))
    finally:
        del app.state.db_connection
        connection.close()


def json_loads(value: str):
    import json

    return json.loads(value)


def test_player_utterance_beliefs_endpoint_returns_subjective_fact_without_event() -> None:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

    try:
        app.state.db_connection = connection
        with TestClient(app) as client:
            utterance_response = client.post(
                "/npcs/npc_guard_001/utterances",
                json={
                    "speaker_id": "player_001",
                    "content": "There is a monster near the gate.",
                    "created_at_tick": 211,
                },
            )
            belief_response = client.get("/npcs/npc_guard_001/beliefs")
            event_response = client.get("/events")

        assert utterance_response.status_code == 200
        assert utterance_response.json()["belief"]["topic_hint"] == "monster_threat"
        assert utterance_response.json()["belief"]["truth_status"] == "unverified"
        assert belief_response.status_code == 200
        assert belief_response.json()[0]["topic_hint"] == "monster_threat"
        assert event_response.json() == []
    finally:
        del app.state.db_connection
        connection.close()


def test_npc_execute_task_endpoint_updates_sqlite_state() -> None:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
    connection.execute(
        """
        UPDATE npc_state
        SET current_task_json = ?
        WHERE npc_id = ?
        """,
        (
            '{"task_type":"rest","target_id":null,"location_id":"inn","priority":60,"interruptible":true}',
            "npc_guard_001",
        ),
    )
    connection.commit()

    try:
        app.state.db_connection = connection
        with TestClient(app) as client:
            response = client.post("/npcs/npc_guard_001/execute-task")

        assert response.status_code == 200
        assert response.json()["executed_task"]["task_type"] == "rest"
        assert response.json()["needs"]["energy"] == 95
    finally:
        del app.state.db_connection
        connection.close()


def test_npc_execute_task_endpoint_returns_belief_verification() -> None:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

    try:
        app.state.db_connection = connection
        with TestClient(app) as client:
            utterance_response = client.post(
                "/npcs/npc_guard_001/utterances",
                json={
                    "speaker_id": "player_001",
                    "content": "There is a monster near the village gate.",
                    "created_at_tick": 211,
                    "message_id": "msg_api_verify_monster",
                },
            )
            event_response = client.post(
                "/events",
                json={
                    "event_id": "evt_api_verify_monster",
                    "event_type": "monster_appeared",
                    "actor_id": "monster_wolf_001",
                    "target_id": None,
                    "location_id": "village_gate",
                    "payload": {},
                    "importance": 70,
                    "created_at_tick": 212,
                },
            )
            connection.execute(
                """
                UPDATE npc_state
                SET current_task_json = ?,
                    runtime_flags_json = ?
                WHERE npc_id = ?
                """,
                (
                    '{"task_type":"investigate","target_id":"belief_npc_guard_001_msg_api_verify_monster","location_id":"village_gate","priority":80,"interruptible":true}',
                    '{"is_critical_npc":true,"thought_cooldown_ticks":20,"last_thought_tick":220}',
                    "npc_guard_001",
                ),
            )
            connection.commit()
            execute_response = client.post("/npcs/npc_guard_001/execute-task")

        verification = execute_response.json()["belief_verification"]
        assert utterance_response.status_code == 200
        assert event_response.status_code == 200
        assert execute_response.status_code == 200
        assert verification["truth_status"] == "confirmed"
        assert verification["evidence_event_ids"] == ["evt_api_verify_monster"]
        assert verification["follow_up_task"]["task_type"] == "patrol"
        assert execute_response.json()["next_current_task"]["task_type"] == "patrol"
    finally:
        del app.state.db_connection
        connection.close()


def test_simulation_tick_endpoint_runs_backend_loop() -> None:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

    try:
        app.state.db_connection = connection
        with TestClient(app) as client:
            response = client.post(
                "/simulation/tick",
                json={
                    "current_tick": 120,
                    "npc_ids": ["npc_hunter_001"],
                },
            )

        assert response.status_code == 200
        assert response.json()["npc_results"][0]["execution_result"]["executed_task"]["task_type"] == "hunt"
    finally:
        del app.state.db_connection
        connection.close()


def test_simulation_tick_endpoint_surfaces_belief_verification() -> None:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

    try:
        app.state.db_connection = connection
        with TestClient(app) as client:
            client.post(
                "/npcs/npc_guard_001/utterances",
                json={
                    "speaker_id": "player_001",
                    "content": "There is a monster near the village gate.",
                    "created_at_tick": 211,
                    "message_id": "msg_api_tick_monster",
                },
            )
            client.post(
                "/events",
                json={
                    "event_id": "evt_api_tick_monster",
                    "event_type": "monster_appeared",
                    "actor_id": "monster_wolf_001",
                    "target_id": None,
                    "location_id": "village_gate",
                    "payload": {},
                    "importance": 70,
                    "created_at_tick": 212,
                },
            )
            connection.execute(
                """
                UPDATE npc_state
                SET current_task_json = ?
                WHERE npc_id = ?
                """,
                (
                    '{"task_type":"investigate","target_id":"belief_npc_guard_001_msg_api_tick_monster","location_id":"village_gate","priority":80,"interruptible":true}',
                    "npc_guard_001",
                ),
            )
            connection.commit()
            tick_response = client.post(
                "/simulation/tick",
                json={
                    "current_tick": 220,
                    "npc_ids": ["npc_guard_001"],
                },
            )

        execution_result = tick_response.json()["npc_results"][0]["execution_result"]
        verification = execution_result["belief_verification"]
        assert tick_response.status_code == 200
        assert verification["truth_status"] == "confirmed"
        assert verification["follow_up_task"]["task_type"] == "patrol"
        assert execution_result["next_current_task"]["task_type"] == "patrol"
    finally:
        del app.state.db_connection
        connection.close()


def test_simulation_tick_endpoint_can_return_profile() -> None:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

    try:
        app.state.db_connection = connection
        with TestClient(app) as client:
            response = client.post(
                "/simulation/tick",
                json={
                    "current_tick": 120,
                    "npc_ids": ["npc_hunter_001"],
                    "include_profile": True,
                },
            )

        assert response.status_code == 200
        assert response.json()["profile"]["execution_worker_count"] >= 1
        assert response.json()["profile"]["npc_profiles"][0]["npc_id"] == "npc_hunter_001"
    finally:
        del app.state.db_connection
        connection.close()


def test_simulation_tick_endpoint_returns_busy_when_engine_rejects_reentry(monkeypatch) -> None:
    class BusyEngine:
        runtime_config = type("RuntimeConfig", (), {"tick_reentry_mode": "reject"})()

        def run_tick(self, connection, request):
            raise SimulationBusyError("simulation tick already running")

    monkeypatch.setattr(main_module, "get_default_simulation_engine", lambda: BusyEngine())

    with TestClient(app) as client:
        response = client.post(
            "/simulation/tick",
            json={
                "current_tick": 120,
                "npc_ids": ["npc_hunter_001"],
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"]["status"] == "busy"
    assert response.json()["detail"]["current_mode"] == "reject"


def test_debug_reset_endpoint_restores_seed_state_and_clears_events() -> None:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

    try:
        app.state.db_connection = connection
        with TestClient(app) as client:
            client.post(
                "/events",
                json={
                    "event_id": "evt_api_reset_monster_001",
                    "event_type": "monster_appeared",
                    "actor_id": "monster_wolf_001",
                    "target_id": None,
                    "location_id": "village_gate",
                    "payload": {},
                    "importance": 60,
                    "created_at_tick": 180,
                },
            )
            client.post(
                "/simulation/tick",
                json={
                    "current_tick": 181,
                    "npc_ids": ["npc_merchant_001"],
                },
            )
            reset_response = client.post("/debug/reset")
            npc_response = client.get("/npcs/npc_merchant_001")
            event_response = client.get("/events")

        assert reset_response.status_code == 200
        assert reset_response.json() == {"status": "reset", "seeded_npc_count": 7}
        assert npc_response.json()["needs"] == {
            "energy": 76,
            "hunger": 30,
            "health": 90,
            "safety": 70,
            "social": 55,
        }
        assert event_response.json() == []
    finally:
        del app.state.db_connection
        connection.close()


def test_world_endpoints_expose_seeded_resources_and_spawned_entities() -> None:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

    try:
        app.state.db_connection = connection
        with TestClient(app) as client:
            resource_response = client.get("/world/resources?location_id=forest_edge")
            ingest_response = client.post(
                "/events",
                json={
                    "event_id": "evt_api_visible_monster",
                    "event_type": "monster_appeared",
                    "actor_id": "monster_api_wolf",
                    "target_id": None,
                    "location_id": "village_gate",
                    "payload": {"monster_kind": "wolf", "monster_id": "monster_api_wolf", "count": 1},
                    "importance": 70,
                    "created_at_tick": 180,
                },
            )
            entity_response = client.get("/world/entities?location_id=village_gate")

        assert resource_response.status_code == 200
        assert {item["resource_type"] for item in resource_response.json()} == {"berries", "herbs"}
        assert ingest_response.status_code == 200
        assert ingest_response.json()["spawned_entity_ids"] == ["monster_api_wolf"]
        assert entity_response.status_code == 200
        assert entity_response.json()[0]["entity_id"] == "monster_api_wolf"
    finally:
        del app.state.db_connection
        connection.close()


def test_village_economy_endpoints_expose_orders_and_warehouse_transactions() -> None:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

    try:
        app.state.db_connection = connection
        with TestClient(app) as client:
            execute_response = client.post("/npcs/npc_farmer_001/execute-task")
            order_response = client.get("/village/production-orders")
            transaction_response = client.get("/village/warehouse/transactions")

        assert execute_response.status_code == 200
        assert order_response.status_code == 200
        assert transaction_response.status_code == 200
        assert order_response.json()[0]["order_type"] == "plant"
        assert order_response.json()[0]["status"] == "pending"
        assert transaction_response.json()[0]["reason"] == "plant_started"
        assert transaction_response.json()[0]["quantity_delta"] == -1
    finally:
        del app.state.db_connection
        connection.close()


def test_inventory_and_world_tick_endpoints_show_materialized_world_updates() -> None:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

    try:
        app.state.db_connection = connection
        with TestClient(app) as client:
            tick_response = client.post(
                "/simulation/tick",
                json={
                    "current_tick": 180,
                    "npc_ids": ["npc_guard_001", "npc_hunter_001", "npc_merchant_001"],
                    "enable_world_updates": True,
                },
            )
            inventory_response = client.get("/npcs/npc_hunter_001/inventory")
            entity_response = client.get("/world/entities")

        assert tick_response.status_code == 200
        payload = tick_response.json()
        assert payload["world_update"]["generated_event_ids"] == [
            "evt_random_monster_180",
            "evt_random_traveler_180",
        ]
        assert inventory_response.status_code == 200
        assert len(inventory_response.json()) >= 2
        assert any(item["execution_result"] is not None for item in payload["npc_results"])
        assert entity_response.status_code == 200
        assert any(item["entity_type"] in {"monster", "traveler"} for item in entity_response.json())
    finally:
        del app.state.db_connection
        connection.close()
