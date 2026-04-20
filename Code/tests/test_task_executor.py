import json
import sqlite3

from app.event_processor import process_world_event
from app.models import NpcBelief
from app.dialogue_processor import PlayerUtteranceRequest, receive_player_utterance
from app.state_repository import list_belief_records, list_memory_records, upsert_npc_belief
from app.task_executor import execute_current_task_for_npc
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
    assert needs["hunger"] == 48
    assert needs["energy"] == 53
    assert current_task["task_type"] == "rest"
    assert task_queue == []


def test_execute_current_task_sets_idle_when_queue_is_empty() -> None:
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

    assert json.loads(current_task_json)["task_type"] == "idle"


def test_trade_consumes_energy_and_increases_hunger_pressure() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        result = execute_current_task_for_npc(connection, "npc_merchant_001")

    assert result.executed_task["task_type"] == "trade"
    assert result.needs["energy"] == 73
    assert result.needs["hunger"] == 33
    assert result.needs["social"] == 51


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

    assert result.executed_task["task_type"] == "report"
    assert result.report_result is not None
    assert result.report_result["to_npc_id"] == "npc_guard_001"
    assert guard_beliefs[0].topic_hint == "suspicious_arrival"
    assert guard_beliefs[0].truth_status == "unverified"


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
