import json
import sqlite3

from app.action_planner import plan_next_action_for_npc
from app.dialogue_processor import PlayerUtteranceRequest, receive_player_utterance
from app.models import NpcBelief
from app.state_repository import upsert_npc_belief
from scripts.init_sqlite import DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR, initialize_connection


def test_plan_next_action_queues_top_candidate_when_not_interrupting() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        result = plan_next_action_for_npc(connection, "npc_hunter_001")
        task_queue_json = connection.execute(
            "SELECT task_queue_json FROM npc_state WHERE npc_id = ?",
            ("npc_hunter_001",),
        ).fetchone()[0]
        task_queue = json.loads(task_queue_json)

    assert result.mode == "queued"
    assert result.selected_task["task_type"] == "gather"
    assert any(task["task_id"] == result.selected_task["task_id"] for task in task_queue)


def test_plan_next_action_interrupts_when_threat_requires_it() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        connection.execute(
            """
            UPDATE npc_state
            SET message_queue_json = ?
            WHERE npc_id = ?
            """,
            (
                '[{"message_id":"msg_threat_001","message_type":"threat_alert","from_id":"npc_hunter_001","priority":90,"created_at_tick":130}]',
                "npc_guard_001",
            ),
        )
        connection.commit()

        result = plan_next_action_for_npc(connection, "npc_guard_001")
        current_task_json, task_queue_json = connection.execute(
            "SELECT current_task_json, task_queue_json FROM npc_state WHERE npc_id = ?",
            ("npc_guard_001",),
        ).fetchone()
        current_task = json.loads(current_task_json)
        task_queue = json.loads(task_queue_json)

    assert result.mode == "interrupted"
    assert current_task["task_type"] == "flee"
    assert any(task["status"] == "paused" for task in task_queue)


def test_plan_next_action_queues_urgent_need_when_switch_benefit_is_too_small() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        connection.execute(
            """
            UPDATE npc_state
            SET needs_json = ?,
                current_task_json = ?
            WHERE npc_id = ?
            """,
            (
                '{"energy":58,"hunger":80,"safety":62,"social":25}',
                '{"task_type":"hunt","target_id":null,"location_id":"forest_edge","priority":95,"interruptible":true}',
                "npc_hunter_001",
            ),
        )
        connection.commit()

        result = plan_next_action_for_npc(connection, "npc_hunter_001")
        current_task_json, task_queue_json = connection.execute(
            "SELECT current_task_json, task_queue_json FROM npc_state WHERE npc_id = ?",
            ("npc_hunter_001",),
        ).fetchone()
        current_task = json.loads(current_task_json)
        task_queue = json.loads(task_queue_json)

    assert result.mode == "queued"
    assert "switching benefit was too small" in result.decision_reason
    assert current_task["task_type"] == "hunt"
    assert any(task["task_type"] == "gather" for task in task_queue)
    assert not any(task["status"] == "paused" for task in task_queue)


def test_plan_next_action_targets_unverified_belief_for_investigation() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        upsert_npc_belief(
            connection,
            "npc_guard_001",
            NpcBelief(
                belief_id="belief_guard_suspicious_market",
                source_type="player_utterance",
                source_id="msg_suspicious_market",
                topic_hint="suspicious_arrival",
                claim="A suspicious merchant entered the market.",
                confidence=66,
                truth_status="unverified",
                created_at_tick=20,
                expires_at_tick=200,
            ),
        )
        connection.commit()

        result = plan_next_action_for_npc(connection, "npc_guard_001")

    assert result.selected_task["task_type"] == "investigate"
    assert result.selected_task["target_id"] == "belief_guard_suspicious_market"


def test_merchant_plans_to_report_security_belief_to_guard() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        receive_player_utterance(
            connection,
            "npc_merchant_001",
            PlayerUtteranceRequest(
                speaker_id="player_001",
                content="A suspicious stranger came to the village gate.",
                created_at_tick=210,
                message_id="msg_merchant_security_claim",
            ),
        )

        result = plan_next_action_for_npc(connection, "npc_merchant_001")
        current_task_json = connection.execute(
            "SELECT current_task_json FROM npc_state WHERE npc_id = ?",
            ("npc_merchant_001",),
        ).fetchone()[0]
        current_task = json.loads(current_task_json)

    assert result.selected_task["task_type"] == "report"
    assert result.selected_task["target_id"] == "npc_guard_001"
    assert current_task["task_type"] == "report"
