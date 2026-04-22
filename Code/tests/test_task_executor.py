import json
import sqlite3

from app.event_processor import process_world_event
from app.models import NpcBelief
from app.dialogue_processor import PlayerUtteranceRequest, receive_player_utterance
from app.state_repository import (
    list_belief_records,
    list_dialogue_turn_records,
    list_inventory_records,
    list_memory_records,
    list_production_orders,
    list_warehouse_transactions,
    list_warehouse_records,
    list_world_entities,
    list_world_resource_nodes,
    upsert_npc_belief,
)
from app.task_executor import execute_current_task_for_npc
from app.world_state import mature_due_production_orders
from scripts.init_sqlite import DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR, initialize_connection


def test_execute_current_task_applies_gather_effects_and_promotes_next_task() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        connection.execute(
            """
            UPDATE npc_state
            SET current_task_json = ?,
                task_queue_json = ?
            WHERE npc_id = ?
            """,
            (
                '{"task_type":"gather","target_id":null,"location_id":"forest_edge","priority":80,"interruptible":true}',
                '[{"task_id":"task_rest_001","task_type":"rest","target_id":null,"location_id":"inn","priority":50,"interruptible":true,"source":"thought","status":"queued"}]',
                "npc_hunter_001",
            ),
        )
        connection.commit()

        result = execute_current_task_for_npc(connection, "npc_hunter_001")
        location_id, needs_json, current_task_json, task_queue_json = connection.execute(
            """
            SELECT location_id, needs_json, current_task_json, task_queue_json
            FROM npc_state
            WHERE npc_id = ?
            """,
            ("npc_hunter_001",),
        ).fetchone()

    needs = json.loads(needs_json)
    current_task = json.loads(current_task_json)
    task_queue = json.loads(task_queue_json)

    assert result.executed_task["task_type"] == "gather"
    assert location_id == "forest_edge"
    assert needs["hunger"] == 72
    assert needs["energy"] == 51
    assert current_task["task_type"] == "rest"
    assert task_queue == []


def test_execute_current_task_uses_role_routine_when_queue_is_empty() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        connection.execute(
            """
            UPDATE npc_state
            SET current_task_json = ?,
                task_queue_json = ?
            WHERE npc_id = ?
            """,
            (
                '{"task_type":"rest","target_id":null,"location_id":"inn","priority":60,"interruptible":true}',
                "[]",
                "npc_guard_001",
            ),
        )
        connection.commit()

        execute_current_task_for_npc(connection, "npc_guard_001")
        current_task_json = connection.execute(
            "SELECT current_task_json FROM npc_state WHERE npc_id = ?",
            ("npc_guard_001",),
        ).fetchone()[0]

    current_task = json.loads(current_task_json)
    assert current_task["task_type"] == "patrol"
    assert current_task["location_id"] == "inn"


def test_trade_consumes_energy_and_increases_hunger_pressure() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        result = execute_current_task_for_npc(connection, "npc_merchant_001")

    assert result.executed_task["task_type"] == "trade"
    assert result.needs["energy"] == 72
    assert result.needs["hunger"] == 32
    assert result.needs["social"] == 52


def test_eat_consumes_food_and_recovers_hunger_from_warehouse() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        connection.execute(
            """
            UPDATE npc_state
            SET needs_json = ?,
                current_task_json = ?,
                task_queue_json = ?
            WHERE npc_id = ?
            """,
            (
                '{"energy":66,"hunger":80,"health":90,"safety":70,"social":42}',
                '{"task_type":"eat","target_id":null,"location_id":"village_square","priority":80,"interruptible":true}',
                "[]",
                "npc_farmer_001",
            ),
        )
        connection.commit()

        result = execute_current_task_for_npc(connection, "npc_farmer_001")
        warehouse = list_warehouse_records(connection)

    assert result.world_effects is not None
    assert result.world_effects["success"] is True
    assert result.world_effects["source"] == "warehouse"
    assert result.needs["hunger"] == 60
    assert result.needs["health"] == 93
    assert next(item for item in warehouse if item.item_type == "grain").quantity == 5


def test_farmer_plant_consumes_seed_and_creates_maturing_grain_order() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        result = execute_current_task_for_npc(connection, "npc_farmer_001")
        warehouse_before_maturity = list_warehouse_records(connection)
        fields_before_maturity = list_world_resource_nodes(connection, location_id="village_square", include_depleted=True)
        pending_orders = list_production_orders(connection)

        matured_ids = mature_due_production_orders(connection, result.world_effects["completes_at_tick"])
        warehouse_after_maturity = list_warehouse_records(connection)
        fields_after_maturity = list_world_resource_nodes(connection, location_id="village_square", include_depleted=True)
        completed_orders = list_production_orders(connection, include_completed=True)
        transactions = list_warehouse_transactions(connection, limit=10)

    assert result.executed_task["task_type"] == "plant"
    assert result.world_effects is not None
    assert result.world_effects["success"] is True
    assert result.world_effects["status"] == "in_progress"
    assert next(item for item in warehouse_before_maturity if item.item_type == "grain_seed").quantity == 5
    assert next(item for item in warehouse_before_maturity if item.item_type == "grain").quantity == 6
    assert next(node for node in fields_before_maturity if node.node_id == "res_village_fields").available_quantity == 4
    assert len(pending_orders) == 1
    assert pending_orders[0].order_type == "plant"
    assert pending_orders[0].status == "pending"
    assert matured_ids == [result.world_effects["production_order_id"]]
    assert next(item for item in warehouse_after_maturity if item.item_type == "grain").quantity == 9
    assert next(node for node in fields_after_maturity if node.node_id == "res_village_fields").available_quantity == 7
    assert completed_orders[0].status == "completed"
    assert {transaction.reason for transaction in transactions} >= {"plant_started", "plant_completed"}


def test_blacksmith_forge_consumes_ore_and_creates_maturing_equipment_order() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        result = execute_current_task_for_npc(connection, "npc_blacksmith_001")
        warehouse_before_maturity = list_warehouse_records(connection)
        pending_orders = list_production_orders(connection)

        matured_ids = mature_due_production_orders(connection, result.world_effects["completes_at_tick"])
        warehouse_after_maturity = list_warehouse_records(connection)
        completed_orders = list_production_orders(connection, include_completed=True)
        transactions = list_warehouse_transactions(connection, limit=10)

    assert result.executed_task["task_type"] == "forge"
    assert result.world_effects is not None
    assert result.world_effects["success"] is True
    assert result.world_effects["status"] == "in_progress"
    assert next(item for item in warehouse_before_maturity if item.item_type == "ore").quantity == 4
    assert not any(item.item_type == "equipment_weapon" for item in warehouse_before_maturity)
    assert len(pending_orders) == 1
    assert pending_orders[0].order_type == "forge"
    assert pending_orders[0].status == "pending"
    assert matured_ids == [result.world_effects["production_order_id"]]
    assert any(item.item_type == "equipment_weapon" for item in warehouse_after_maturity)
    assert completed_orders[0].status == "completed"
    assert {transaction.reason for transaction in transactions} >= {"forge_started", "forge_completed"}


def test_physician_help_treats_most_injured_villager_from_shared_herbs() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        connection.execute(
            """
            UPDATE npc_state
            SET needs_json = ?
            WHERE npc_id = ?
            """,
            (
                '{"energy":70,"hunger":42,"health":40,"safety":64,"social":44}',
                "npc_guard_001",
            ),
        )
        connection.commit()

        result = execute_current_task_for_npc(connection, "npc_physician_001")
        guard_needs_json = connection.execute(
            "SELECT needs_json FROM npc_state WHERE npc_id = ?",
            ("npc_guard_001",),
        ).fetchone()[0]
        warehouse = list_warehouse_records(connection)
        transactions = list_warehouse_transactions(connection, limit=5)

    guard_needs = json.loads(guard_needs_json)
    assert result.executed_task["task_type"] == "help"
    assert result.world_effects is not None
    assert result.world_effects["success"] is True
    assert result.world_effects["target_npc_id"] == "npc_guard_001"
    assert result.world_effects["source"] == "warehouse"
    assert guard_needs["health"] == 62
    assert next(item for item in warehouse if item.item_type == "herbs").quantity == 2
    assert any(transaction.reason == "heal_used" for transaction in transactions)


def test_village_chief_patrol_assigns_shortage_work_without_duplicating_active_jobs() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        connection.execute("UPDATE village_warehouse SET quantity = 2 WHERE item_type = 'rations'")
        connection.execute("UPDATE village_warehouse SET quantity = 2 WHERE item_type = 'grain'")
        connection.commit()

        result = execute_current_task_for_npc(connection, "npc_village_chief_001")
        hunter_queue_json = connection.execute(
            "SELECT task_queue_json FROM npc_state WHERE npc_id = ?",
            ("npc_hunter_001",),
        ).fetchone()[0]
        farmer_queue_json = connection.execute(
            "SELECT task_queue_json FROM npc_state WHERE npc_id = ?",
            ("npc_farmer_001",),
        ).fetchone()[0]
        blacksmith_queue_json = connection.execute(
            "SELECT task_queue_json FROM npc_state WHERE npc_id = ?",
            ("npc_blacksmith_001",),
        ).fetchone()[0]

    hunter_queue = json.loads(hunter_queue_json)
    farmer_queue = json.loads(farmer_queue_json)
    blacksmith_queue = json.loads(blacksmith_queue_json)
    assert result.executed_task["task_type"] == "patrol"
    assert result.world_effects is not None
    assert result.world_effects["success"] is True
    assert result.world_effects["reason"] == "warehouse_coordination"
    assert any(assignment["npc_id"] == "npc_hunter_001" and assignment["task_type"] == "gather" for assignment in result.world_effects["assignments"])
    assert any(task["task_type"] == "gather" for task in hunter_queue)
    assert not any(task["task_type"] == "plant" for task in farmer_queue)
    assert not any(task["task_type"] == "forge" for task in blacksmith_queue)


def test_remote_talk_task_does_not_apply_social_effects() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        connection.execute(
            """
            UPDATE npc_state
            SET current_task_json = ?,
                task_queue_json = ?
            WHERE npc_id = ?
            """,
            (
                '{"task_type":"talk","target_id":"npc_merchant_001","location_id":"market","priority":80,"interruptible":true}',
                "[]",
                "npc_guard_001",
            ),
        )
        connection.commit()

        result = execute_current_task_for_npc(connection, "npc_guard_001")
        current_task_json = connection.execute(
            "SELECT current_task_json FROM npc_state WHERE npc_id = ?",
            ("npc_guard_001",),
        ).fetchone()[0]

    assert result.executed_task["task_type"] == "talk"
    assert result.needs["social"] == 20
    assert result.needs["energy"] == 70
    assert json.loads(current_task_json)["task_type"] == "patrol"


def test_report_task_forwards_merchant_belief_to_guard_for_verification() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        receive_player_utterance(
            connection,
            "npc_merchant_001",
            PlayerUtteranceRequest(
                speaker_id="player_001",
                content="A suspicious stranger came to the village gate.",
                created_at_tick=90,
                message_id="msg_player_to_merchant_suspicious",
            ),
        )
        connection.execute(
            """
            UPDATE npc_state
            SET current_task_json = ?,
                runtime_flags_json = ?
            WHERE npc_id = ?
            """,
            (
                '{"task_type":"report","target_id":"npc_guard_001","location_id":"village_gate","priority":92,"interruptible":true}',
                '{"is_critical_npc":true,"thought_cooldown_ticks":20,"last_thought_tick":130}',
                "npc_merchant_001",
            ),
        )
        connection.commit()

        result = execute_current_task_for_npc(connection, "npc_merchant_001")
        guard_beliefs = list_belief_records(connection, "npc_guard_001")
        dialogue_turns = list_dialogue_turn_records(connection, "npc_guard_001", "npc_merchant_001")

    assert result.executed_task["task_type"] == "report"
    assert result.report_result is not None
    assert result.report_result["to_npc_id"] == "npc_guard_001"
    assert result.report_result["from_npc_id"] == "npc_merchant_001"
    assert result.report_result["credibility"] > 60
    assert result.report_result["accepted"] is True
    assert result.report_result["utterance"].startswith("Darin, I need you to hear this:")
    assert "Mira" in result.report_result["reply"]
    assert guard_beliefs[0].topic_hint == "suspicious_arrival"
    assert guard_beliefs[0].source_type == "npc_report"
    assert guard_beliefs[0].truth_status == "unverified"
    assert [turn.speaker_label for turn in dialogue_turns] == ["Mira", "Darin"]
    assert dialogue_turns[0].content == result.report_result["utterance"]
    assert dialogue_turns[1].content == result.report_result["reply"]


def test_report_without_explicit_target_prefers_same_location_relationship_and_role_relevance() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        upsert_npc_belief(
            connection,
            "npc_merchant_001",
            NpcBelief(
                belief_id="belief_merchant_market_shortage",
                source_type="player_utterance",
                source_id="msg_market_shortage",
                topic_hint="food_shortage",
                claim="Food supplies are running low near the market.",
                confidence=58,
                truth_status="unverified",
                created_at_tick=90,
                expires_at_tick=220,
            ),
        )
        connection.execute(
            """
            UPDATE npc_state
            SET location_id = ?
            WHERE npc_id = ?
            """,
            ("market", "npc_hunter_001"),
        )
        connection.execute(
            """
            UPDATE relationships
            SET trust = ?, favor = ?, hostility = ?
            WHERE npc_id = ? AND target_id = ?
            """,
            (35, 18, 0, "npc_merchant_001", "npc_hunter_001"),
        )
        connection.execute(
            """
            UPDATE npc_state
            SET current_task_json = ?,
                runtime_flags_json = ?
            WHERE npc_id = ?
            """,
            (
                '{"task_type":"report","target_id":null,"location_id":"market","priority":80,"interruptible":true}',
                '{"is_critical_npc":true,"priority_tier":"highest","thought_cooldown_ticks":20,"last_thought_tick":130,"last_plan_tick":100}',
                "npc_merchant_001",
            ),
        )
        connection.commit()

        result = execute_current_task_for_npc(connection, "npc_merchant_001")

    assert result.report_result is not None
    assert result.report_result["to_npc_id"] == "npc_hunter_001"
    assert result.report_result["accepted"] is True


def test_low_confidence_repeated_report_is_stored_as_rumor() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        upsert_npc_belief(
            connection,
            "npc_guard_001",
            NpcBelief(
                belief_id="belief_guard_secondhand_monster",
                source_type="npc_report",
                source_id="msg_secondhand_monster",
                topic_hint="monster_threat",
                claim="Someone said a monster is circling the village gate.",
                confidence=45,
                truth_status="unverified",
                created_at_tick=90,
                expires_at_tick=220,
            ),
        )
        connection.execute(
            """
            UPDATE npc_state
            SET location_id = ?
            WHERE npc_id = ?
            """,
            ("village_gate", "npc_hunter_001"),
        )
        connection.execute(
            """
            UPDATE npc_state
            SET current_task_json = ?,
                runtime_flags_json = ?
            WHERE npc_id = ?
            """,
            (
                '{"task_type":"report","target_id":"npc_hunter_001","location_id":"village_gate","priority":80,"interruptible":true}',
                '{"is_critical_npc":false,"priority_tier":"normal","thought_cooldown_ticks":20,"last_thought_tick":130,"last_plan_tick":100}',
                "npc_guard_001",
            ),
        )
        connection.commit()

        result = execute_current_task_for_npc(connection, "npc_guard_001")
        hunter_beliefs = list_belief_records(connection, "npc_hunter_001")

    assert result.report_result is not None
    assert result.report_result["accepted"] is True
    assert result.report_result["rumor"] is True
    assert "rumor" in result.report_result["reply"]
    assert hunter_beliefs[0].source_type == "rumor"


def test_multiple_sources_boost_same_topic_report_credibility() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        upsert_npc_belief(
            connection,
            "npc_guard_001",
            NpcBelief(
                belief_id="belief_guard_secondhand_gate_food",
                source_type="npc_report",
                source_id="msg_guard_food",
                topic_hint="food_shortage",
                claim="Someone said food supplies are running low at the gate.",
                confidence=40,
                truth_status="unverified",
                created_at_tick=90,
                expires_at_tick=220,
            ),
        )
        upsert_npc_belief(
            connection,
            "npc_hunter_001",
            NpcBelief(
                belief_id="belief_hunter_prior_food_hint",
                source_type="player_utterance",
                source_id="msg_player_food_hint",
                topic_hint="food_shortage",
                claim="The player warned that food supplies are thin.",
                confidence=38,
                truth_status="unverified",
                created_at_tick=88,
                expires_at_tick=220,
            ),
        )
        connection.execute(
            """
            UPDATE npc_state
            SET location_id = ?
            WHERE npc_id = ?
            """,
            ("village_gate", "npc_hunter_001"),
        )
        connection.execute(
            """
            UPDATE npc_state
            SET current_task_json = ?,
                runtime_flags_json = ?
            WHERE npc_id = ?
            """,
            (
                '{"task_type":"report","target_id":"npc_hunter_001","location_id":"village_gate","priority":80,"interruptible":true}',
                '{"is_critical_npc":false,"priority_tier":"normal","thought_cooldown_ticks":20,"last_thought_tick":130,"last_plan_tick":100}',
                "npc_guard_001",
            ),
        )
        connection.commit()

        result = execute_current_task_for_npc(connection, "npc_guard_001")

    assert result.report_result is not None
    assert result.report_result["credibility"] >= 45
    assert result.report_result["accepted"] is True


def test_report_task_uses_receiver_relationship_to_filter_belief() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        upsert_npc_belief(
            connection,
            "npc_merchant_001",
            NpcBelief(
                belief_id="belief_merchant_low_trust_warning",
                source_type="player_utterance",
                source_id="msg_low_trust_warning",
                topic_hint="monster_threat",
                claim="There is a monster near the village gate.",
                confidence=40,
                truth_status="unverified",
                created_at_tick=90,
                expires_at_tick=200,
            ),
        )
        connection.execute(
            """
            UPDATE relationships
            SET trust = ?, favor = ?, hostility = ?
            WHERE npc_id = ? AND target_id = ?
            """,
            (-30, -20, 80, "npc_guard_001", "npc_merchant_001"),
        )
        connection.execute(
            """
            UPDATE npc_state
            SET current_task_json = ?,
                message_queue_json = ?,
                runtime_flags_json = ?
            WHERE npc_id = ?
            """,
            (
                '{"task_type":"report","target_id":"npc_guard_001","location_id":"village_gate","priority":92,"interruptible":true}',
                '[{"message_id":"msg_low_trust_warning","message_type":"player_utterance","from_id":"player_001","priority":60,"created_at_tick":90,"content":"There is a monster near the village gate.","topic_hint":"monster_threat","credibility":40}]',
                '{"is_critical_npc":true,"priority_tier":"highest","thought_cooldown_ticks":20,"last_thought_tick":130,"last_plan_tick":100}',
                "npc_merchant_001",
            ),
        )
        connection.commit()

        result = execute_current_task_for_npc(connection, "npc_merchant_001")
        guard_beliefs = list_belief_records(connection, "npc_guard_001")
        guard_memories = list_memory_records(connection, "npc_guard_001", include_expired=True)
        guard_messages_json = connection.execute(
            "SELECT message_queue_json FROM npc_state WHERE npc_id = ?",
            ("npc_guard_001",),
        ).fetchone()[0]

    guard_messages = json.loads(guard_messages_json)
    assert result.report_result is not None
    assert result.report_result["accepted"] is False
    assert result.report_result["target_belief_id"] is None
    assert guard_beliefs == []
    assert guard_messages[0]["message_type"] == "npc_report"
    assert guard_messages[0]["from_id"] == "npc_merchant_001"
    assert any("credibility" in memory.summary for memory in guard_memories)


def test_confirmed_npc_report_increases_receiver_trust_in_reporter() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        receive_player_utterance(
            connection,
            "npc_merchant_001",
            PlayerUtteranceRequest(
                speaker_id="player_001",
                content="A suspicious stranger came to the village gate.",
                created_at_tick=90,
                message_id="msg_player_to_merchant_report_trust",
            ),
        )
        connection.execute(
            """
            UPDATE npc_state
            SET current_task_json = ?,
                runtime_flags_json = ?
            WHERE npc_id = ?
            """,
            (
                '{"task_type":"report","target_id":"npc_guard_001","location_id":"village_gate","priority":92,"interruptible":true}',
                '{"is_critical_npc":true,"priority_tier":"highest","thought_cooldown_ticks":20,"last_thought_tick":130,"last_plan_tick":100}',
                "npc_merchant_001",
            ),
        )
        execute_current_task_for_npc(connection, "npc_merchant_001")
        guard_belief = list_belief_records(connection, "npc_guard_001")[0]
        connection.execute(
            """
            UPDATE npc_state
            SET current_task_json = ?,
                runtime_flags_json = ?
            WHERE npc_id = ?
            """,
            (
                '{"task_type":"investigate","target_id":"%s","location_id":"village_gate","priority":80,"interruptible":true}' % guard_belief.belief_id,
                '{"is_critical_npc":false,"priority_tier":"normal","thought_cooldown_ticks":20,"last_thought_tick":150,"last_plan_tick":130}',
                "npc_guard_001",
            ),
        )
        process_world_event(
            connection,
            {
                "event_id": "evt_confirm_reported_suspicious_arrival",
                "event_type": "suspicious_arrival",
                "actor_id": "npc_stranger_001",
                "target_id": None,
                "location_id": "village_gate",
                "payload": {},
                "importance": 55,
                "created_at_tick": 140,
            },
        )

        result = execute_current_task_for_npc(connection, "npc_guard_001")
        relationship = connection.execute(
            """
            SELECT favor, trust, hostility
            FROM relationships
            WHERE npc_id = ? AND target_id = ?
            """,
            ("npc_guard_001", "npc_merchant_001"),
        ).fetchone()

    assert result.belief_verification is not None
    assert result.belief_verification.truth_status == "confirmed"
    assert result.belief_verification.relationship_update["target_id"] == "npc_merchant_001"
    assert relationship == (7, 16, 0)


def test_investigate_confirms_belief_when_matching_world_event_exists() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        upsert_npc_belief(
            connection,
            "npc_guard_001",
            NpcBelief(
                belief_id="belief_guard_monster_gate",
                source_type="player_utterance",
                source_id="msg_monster_gate",
                topic_hint="monster_threat",
                claim="There is a monster near the village gate.",
                confidence=62,
                truth_status="unverified",
                created_at_tick=90,
                expires_at_tick=200,
            ),
        )
        connection.execute(
            """
            UPDATE npc_state
            SET current_task_json = ?,
                message_queue_json = ?,
                runtime_flags_json = ?
            WHERE npc_id = ?
            """,
            (
                '{"task_type":"investigate","target_id":"belief_guard_monster_gate","location_id":"village_gate","priority":80,"interruptible":true}',
                '[{"message_id":"msg_monster_gate","message_type":"player_utterance","from_id":"player_001","priority":78,"created_at_tick":90,"content":"There is a monster near the village gate.","topic_hint":"monster_threat","credibility":62}]',
                '{"is_critical_npc":true,"thought_cooldown_ticks":20,"last_thought_tick":130}',
                "npc_guard_001",
            ),
        )
        process_world_event(
            connection,
            {
                "event_id": "evt_monster_gate_verify",
                "event_type": "monster_appeared",
                "actor_id": "monster_wolf_001",
                "target_id": None,
                "location_id": "village_gate",
                "payload": {},
                "importance": 70,
                "created_at_tick": 120,
            },
        )

        result = execute_current_task_for_npc(connection, "npc_guard_001")
        beliefs = list_belief_records(connection, "npc_guard_001", include_expired=True)
        memories = list_memory_records(connection, "npc_guard_001", current_tick=130, include_expired=True)
        player_relationship = connection.execute(
            """
            SELECT trust, hostility
            FROM relationships
            WHERE npc_id = ? AND target_id = ?
            """,
            ("npc_guard_001", "player_001"),
        ).fetchone()

    verified_belief = next(belief for belief in beliefs if belief.belief_id == "belief_guard_monster_gate")
    assert result.belief_verification is not None
    assert result.belief_verification.truth_status == "confirmed"
    assert result.belief_verification.evidence_event_ids == ["evt_monster_gate_verify"]
    assert result.belief_verification.follow_up_task["task_type"] == "patrol"
    assert result.next_current_task["task_type"] == "patrol"
    assert result.next_current_task["location_id"] == "village_gate"
    assert verified_belief.truth_status == "confirmed"
    assert verified_belief.confidence == 82
    assert any(memory.memory_id == "mem_npc_guard_001_belief_guard_monster_gate_confirmed" for memory in memories)
    assert player_relationship == (6, 0)


def test_investigate_disproves_belief_when_location_observation_finds_no_evidence() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        upsert_npc_belief(
            connection,
            "npc_guard_001",
            NpcBelief(
                belief_id="belief_guard_suspicious_gate",
                source_type="player_utterance",
                source_id="msg_suspicious_gate",
                topic_hint="suspicious_arrival",
                claim="A suspicious stranger is hiding by the gate.",
                confidence=60,
                truth_status="unverified",
                created_at_tick=90,
                expires_at_tick=200,
            ),
        )
        connection.execute(
            """
            UPDATE npc_state
            SET current_task_json = ?,
                message_queue_json = ?,
                runtime_flags_json = ?
            WHERE npc_id = ?
            """,
            (
                '{"task_type":"investigate","target_id":"belief_guard_suspicious_gate","location_id":"village_gate","priority":80,"interruptible":true}',
                '[{"message_id":"msg_suspicious_gate","message_type":"player_utterance","from_id":"player_001","priority":62,"created_at_tick":90,"content":"A suspicious stranger is hiding by the gate.","topic_hint":"suspicious_arrival","credibility":60}]',
                '{"is_critical_npc":true,"thought_cooldown_ticks":20,"last_thought_tick":130}',
                "npc_guard_001",
            ),
        )
        connection.commit()

        result = execute_current_task_for_npc(connection, "npc_guard_001")
        beliefs = list_belief_records(connection, "npc_guard_001", include_expired=True)
        memories = list_memory_records(connection, "npc_guard_001", current_tick=130, include_expired=True)
        player_relationship = connection.execute(
            """
            SELECT favor, trust, hostility
            FROM relationships
            WHERE npc_id = ? AND target_id = ?
            """,
            ("npc_guard_001", "player_001"),
        ).fetchone()

    verified_belief = next(belief for belief in beliefs if belief.belief_id == "belief_guard_suspicious_gate")
    assert result.belief_verification is not None
    assert result.belief_verification.truth_status == "disproven"
    assert result.belief_verification.evidence_event_ids == []
    assert result.belief_verification.follow_up_task["task_type"] == "patrol"
    assert result.next_current_task["task_type"] == "patrol"
    assert result.next_current_task["location_id"] == "village_gate"
    assert verified_belief.truth_status == "disproven"
    assert verified_belief.confidence == 25
    assert any(memory.memory_id == "mem_npc_guard_001_belief_guard_suspicious_gate_disproven" for memory in memories)
    assert player_relationship == (-2, -8, 2)


def test_investigation_expiration_handles_tick_behind_belief_creation() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        upsert_npc_belief(
            connection,
            "npc_guard_001",
            NpcBelief(
                belief_id="belief_guard_future_tick_suspicious",
                source_type="player_utterance",
                source_id="msg_future_tick_suspicious",
                topic_hint="suspicious_arrival",
                claim="A suspicious stranger is hiding by the gate.",
                confidence=60,
                truth_status="unverified",
                created_at_tick=610,
                expires_at_tick=800,
            ),
        )
        connection.execute(
            """
            UPDATE npc_state
            SET current_task_json = ?,
                message_queue_json = ?,
                runtime_flags_json = ?
            WHERE npc_id = ?
            """,
            (
                '{"task_type":"investigate","target_id":"belief_guard_future_tick_suspicious","location_id":"village_gate","priority":80,"interruptible":true}',
                '[{"message_id":"msg_future_tick_suspicious","message_type":"player_utterance","from_id":"player_001","priority":62,"created_at_tick":610,"content":"A suspicious stranger is hiding by the gate.","topic_hint":"suspicious_arrival","credibility":60}]',
                '{"is_critical_npc":true,"thought_cooldown_ticks":20,"last_thought_tick":2}',
                "npc_guard_001",
            ),
        )
        connection.commit()

        result = execute_current_task_for_npc(connection, "npc_guard_001")
        verified_belief = next(
            belief
            for belief in list_belief_records(connection, "npc_guard_001", include_expired=True)
            if belief.belief_id == "belief_guard_future_tick_suspicious"
        )

    assert result.belief_verification is not None
    assert result.belief_verification.truth_status == "disproven"
    assert verified_belief.expires_at_tick == 850


def test_investigate_confirms_suspicious_arrival_from_matching_event() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        upsert_npc_belief(
            connection,
            "npc_guard_001",
            NpcBelief(
                belief_id="belief_guard_suspicious_arrival",
                source_type="player_utterance",
                source_id="msg_suspicious_arrival",
                topic_hint="suspicious_arrival",
                claim="A suspicious merchant is near the village gate.",
                confidence=64,
                truth_status="unverified",
                created_at_tick=90,
                expires_at_tick=200,
            ),
        )
        connection.execute(
            """
            UPDATE npc_state
            SET current_task_json = ?,
                message_queue_json = ?,
                runtime_flags_json = ?
            WHERE npc_id = ?
            """,
            (
                '{"task_type":"investigate","target_id":"belief_guard_suspicious_arrival","location_id":"village_gate","priority":80,"interruptible":true}',
                '[{"message_id":"msg_suspicious_arrival","message_type":"player_utterance","from_id":"player_001","priority":62,"created_at_tick":90,"content":"A suspicious merchant is near the village gate.","topic_hint":"suspicious_arrival","credibility":64}]',
                '{"is_critical_npc":true,"thought_cooldown_ticks":20,"last_thought_tick":130}',
                "npc_guard_001",
            ),
        )
        process_world_event(
            connection,
            {
                "event_id": "evt_suspicious_arrival_verify",
                "event_type": "suspicious_arrival",
                "actor_id": "npc_merchant_001",
                "target_id": None,
                "location_id": "village_gate",
                "payload": {"related_ids": ["npc_guard_001"]},
                "importance": 55,
                "created_at_tick": 120,
            },
        )

        result = execute_current_task_for_npc(connection, "npc_guard_001")
        beliefs = list_belief_records(connection, "npc_guard_001", include_expired=True)

    verified_belief = next(belief for belief in beliefs if belief.belief_id == "belief_guard_suspicious_arrival")
    assert result.belief_verification is not None
    assert result.belief_verification.truth_status == "confirmed"
    assert result.belief_verification.evidence_event_ids == ["evt_suspicious_arrival_verify"]
    assert result.belief_verification.follow_up_task is None
    assert verified_belief.truth_status == "confirmed"
    assert verified_belief.confidence == 84


def test_investigate_confirms_suspicious_arrival_from_recent_prior_event() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        process_world_event(
            connection,
            {
                "event_id": "evt_suspicious_arrival_prior",
                "event_type": "suspicious_arrival",
                "actor_id": "npc_merchant_001",
                "target_id": None,
                "location_id": "village_gate",
                "payload": {"related_ids": ["npc_guard_001"]},
                "importance": 55,
                "created_at_tick": 86,
            },
        )
        upsert_npc_belief(
            connection,
            "npc_guard_001",
            NpcBelief(
                belief_id="belief_guard_suspicious_arrival_recent_prior",
                source_type="player_utterance",
                source_id="msg_suspicious_arrival_recent_prior",
                topic_hint="suspicious_arrival",
                claim="A suspicious merchant was near the village gate.",
                confidence=64,
                truth_status="unverified",
                created_at_tick=90,
                expires_at_tick=200,
            ),
        )
        connection.execute(
            """
            UPDATE npc_state
            SET current_task_json = ?,
                message_queue_json = ?,
                runtime_flags_json = ?
            WHERE npc_id = ?
            """,
            (
                '{"task_type":"investigate","target_id":"belief_guard_suspicious_arrival_recent_prior","location_id":"village_gate","priority":80,"interruptible":true}',
                '[{"message_id":"msg_suspicious_arrival_recent_prior","message_type":"player_utterance","from_id":"player_001","priority":62,"created_at_tick":90,"content":"A suspicious merchant was near the village gate.","topic_hint":"suspicious_arrival","credibility":64}]',
                '{"is_critical_npc":true,"thought_cooldown_ticks":20,"last_thought_tick":130}',
                "npc_guard_001",
            ),
        )
        connection.commit()

        result = execute_current_task_for_npc(connection, "npc_guard_001")

    assert result.belief_verification is not None
    assert result.belief_verification.truth_status == "confirmed"
    assert result.belief_verification.evidence_event_ids == ["evt_suspicious_arrival_prior"]


def test_disproven_player_claim_reduces_next_utterance_credibility() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        initial_result = receive_player_utterance(
            connection,
            "npc_guard_001",
            PlayerUtteranceRequest(
                speaker_id="player_001",
                content="A suspicious stranger is hiding by the gate.",
                created_at_tick=90,
                message_id="msg_initial_suspicious_gate",
            ),
        )
        connection.execute(
            """
            UPDATE npc_state
            SET current_task_json = ?,
                runtime_flags_json = ?
            WHERE npc_id = ?
            """,
            (
                '{"task_type":"investigate","target_id":"belief_npc_guard_001_msg_initial_suspicious_gate","location_id":"village_gate","priority":80,"interruptible":true}',
                '{"is_critical_npc":true,"thought_cooldown_ticks":20,"last_thought_tick":130}',
                "npc_guard_001",
            ),
        )
        connection.commit()

        execute_current_task_for_npc(connection, "npc_guard_001")
        next_result = receive_player_utterance(
            connection,
            "npc_guard_001",
            PlayerUtteranceRequest(
                speaker_id="player_001",
                content="A suspicious merchant is by the market.",
                created_at_tick=140,
                message_id="msg_second_suspicious_market",
            ),
        )

    assert initial_result is not None
    assert next_result is not None
    assert next_result.credibility < initial_result.credibility


def test_gather_task_harvests_resource_node_into_inventory() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        connection.execute(
            """
            UPDATE npc_state
            SET current_task_json = ?,
                runtime_flags_json = ?
            WHERE npc_id = ?
            """,
            (
                '{"task_type":"gather","target_id":null,"location_id":"forest_edge","priority":80,"interruptible":true}',
                '{"is_critical_npc":true,"priority_tier":"high","thought_cooldown_ticks":20,"last_thought_tick":130,"last_plan_tick":100}',
                "npc_hunter_001",
            ),
        )
        connection.commit()

        before_resources = list_world_resource_nodes(connection, location_id="forest_edge", include_depleted=True)
        result = execute_current_task_for_npc(connection, "npc_hunter_001")
        after_resources = list_world_resource_nodes(connection, location_id="forest_edge", include_depleted=True)
        inventory = list_inventory_records(connection, "npc_hunter_001")

    before_total = sum(node.available_quantity for node in before_resources)
    after_total = sum(node.available_quantity for node in after_resources)
    assert result.world_effects is not None
    assert result.world_effects["harvested_quantity"] >= 1
    assert after_total < before_total
    assert any(item.item_type in {"berries", "herbs"} for item in inventory)


def test_hunt_task_consumes_world_monster_and_adds_loot_inventory() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        process_world_event(
            connection,
            {
                "event_id": "evt_hunt_visible_monster",
                "event_type": "monster_appeared",
                "actor_id": "monster_hunt_target",
                "target_id": None,
                "location_id": "forest_edge",
                "payload": {"monster_kind": "wolf", "monster_id": "monster_hunt_target", "count": 1},
                "importance": 65,
                "created_at_tick": 120,
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
                '{"task_type":"hunt","target_id":"monster_hunt_target","location_id":"forest_edge","priority":95,"interruptible":true}',
                '{"is_critical_npc":true,"priority_tier":"high","thought_cooldown_ticks":20,"last_thought_tick":130,"last_plan_tick":100}',
                "npc_hunter_001",
            ),
        )
        connection.commit()

        result = execute_current_task_for_npc(connection, "npc_hunter_001")
        entities = list_world_entities(connection, location_id="forest_edge", include_inactive=True)
        inventory = list_inventory_records(connection, "npc_hunter_001")
        slain_rows = connection.execute(
            "SELECT event_type FROM events WHERE event_id = ?",
            ("evt_npc_hunter_001_monster_slain_130",),
        ).fetchall()

    hunted_entity = next(entity for entity in entities if entity.entity_id == "monster_hunt_target")
    assert result.world_effects is not None
    assert result.world_effects["entity_id"] == "monster_hunt_target"
    assert result.world_effects["success"] is True
    assert result.world_effects["loot"]["meat"] >= 1
    assert hunted_entity.state == "removed"
    assert any(item.item_type == "meat" and item.quantity >= 2 for item in inventory)
    assert any(item.item_type == "trophy" for item in inventory)
    assert slain_rows == [("monster_slain",)]


def test_hunt_task_can_fail_when_npc_lacks_combat_capability() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        process_world_event(
            connection,
            {
                "event_id": "evt_hunt_weak_actor_monster",
                "event_type": "monster_appeared",
                "actor_id": "monster_weak_actor_target",
                "target_id": None,
                "location_id": "market",
                "payload": {"monster_kind": "wolf", "monster_id": "monster_weak_actor_target", "count": 1},
                "importance": 80,
                "created_at_tick": 120,
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
                '{"task_type":"hunt","target_id":"monster_weak_actor_target","location_id":"market","priority":95,"interruptible":true}',
                '{"is_critical_npc":true,"priority_tier":"highest","thought_cooldown_ticks":20,"last_thought_tick":130,"last_plan_tick":100}',
                "npc_merchant_001",
            ),
        )
        connection.commit()

        result = execute_current_task_for_npc(connection, "npc_merchant_001")
        entities = list_world_entities(connection, location_id="market", include_inactive=True)
        inventory = list_inventory_records(connection, "npc_merchant_001")

    hunted_entity = next(entity for entity in entities if entity.entity_id == "monster_weak_actor_target")
    assert result.world_effects is not None
    assert result.world_effects["success"] is False
    assert hunted_entity.state == "stalking"
    assert not any(item.item_type == "trophy" for item in inventory)
