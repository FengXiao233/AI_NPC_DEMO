import json
import sqlite3
import time

import app.simulation_tick as simulation_tick_module
from app.action_planner import ActionPlanResult
from app.fallback_rules import build_fallback_thought
from app.simulation_tick import SimulationTickRequest, run_simulation_tick
from scripts.init_sqlite import DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR, initialize_connection


SEEDED_NPC_IDS = {
    "npc_blacksmith_001",
    "npc_farmer_001",
    "npc_guard_001",
    "npc_hunter_001",
    "npc_merchant_001",
    "npc_physician_001",
    "npc_village_chief_001",
}


def test_simulation_tick_executes_and_plans_selected_npcs() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        result = run_simulation_tick(
            connection,
            SimulationTickRequest(current_tick=120, npc_ids=["npc_hunter_001"]),
        )
        needs_json, current_task_json, task_queue_json, runtime_flags_json = connection.execute(
            """
            SELECT needs_json, current_task_json, task_queue_json, runtime_flags_json
            FROM npc_state
            WHERE npc_id = ?
            """,
            ("npc_hunter_001",),
        ).fetchone()

    needs = json.loads(needs_json)
    current_task = json.loads(current_task_json)
    task_queue = json.loads(task_queue_json)
    runtime_flags = json.loads(runtime_flags_json)

    assert result.current_tick == 120
    assert result.npc_results[0].execution_result.executed_task["task_type"] == "hunt"
    assert result.npc_results[0].plan_result.mode == "interrupted"
    assert needs["hunger"] == 77
    assert result.npc_results[0].passive_needs["hunger"] == 71
    assert current_task["task_type"] == "eat"
    assert any(task["task_type"] == "trade" and task["status"] == "paused" for task in task_queue)
    assert runtime_flags["last_thought_tick"] == 120


def test_simulation_tick_runs_all_npcs_when_ids_are_omitted() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        result = run_simulation_tick(
            connection,
            SimulationTickRequest(current_tick=120),
        )

    assert {npc_result.npc_id for npc_result in result.npc_results} == SEEDED_NPC_IDS


def test_merchant_trading_does_not_collapse_hunger_pressure_to_zero() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        for tick in range(101, 121):
            run_simulation_tick(
                connection,
                SimulationTickRequest(current_tick=tick, npc_ids=["npc_merchant_001"]),
            )

        needs_json = connection.execute(
            "SELECT needs_json FROM npc_state WHERE npc_id = ?",
            ("npc_merchant_001",),
        ).fetchone()[0]

    needs = json.loads(needs_json)
    assert needs["hunger"] > 30
    assert needs["energy"] < 76


def test_simulation_tick_does_not_replan_for_stale_messages_every_tick() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        connection.execute(
            """
            UPDATE npc_state
            SET current_task_json = ?,
                message_queue_json = ?,
                runtime_flags_json = ?
            WHERE npc_id = ?
            """,
            (
                '{"task_type":"trade","target_id":null,"location_id":"market","priority":55,"interruptible":true}',
                '[{"message_id":"msg_old_player","message_type":"player_utterance","from_id":"player_001","priority":48,"created_at_tick":100,"content":"Hello again.","topic_hint":null,"credibility":50}]',
                '{"is_critical_npc":true,"priority_tier":"highest","thought_cooldown_ticks":20,"last_thought_tick":120,"last_plan_tick":120}',
                "npc_merchant_001",
            ),
        )

        result = run_simulation_tick(
            connection,
            SimulationTickRequest(current_tick=121, npc_ids=["npc_merchant_001"]),
        )
        runtime_flags_json = connection.execute(
            "SELECT runtime_flags_json FROM npc_state WHERE npc_id = ?",
            ("npc_merchant_001",),
        ).fetchone()[0]

    runtime_flags = json.loads(runtime_flags_json)

    assert result.npc_results[0].plan_result is None
    assert runtime_flags["last_thought_tick"] == 121
    assert runtime_flags["last_plan_tick"] == 120


def test_simulation_tick_planning_stage_runs_in_parallel(monkeypatch) -> None:
    def slow_plan(agent_state):
        time.sleep(0.2)
        return (
            ActionPlanResult(
                npc_id=agent_state.npc_id,
                mode="none",
                selected_task=None,
                decision_reason="test slow plan",
                thought=build_fallback_thought(agent_state),
            ),
            200.0,
        )

    monkeypatch.setattr(simulation_tick_module, "build_plan_result_for_state", slow_plan)

    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        start = time.perf_counter()
        result = run_simulation_tick(
            connection,
            SimulationTickRequest(
                current_tick=121,
                npc_ids=["npc_guard_001", "npc_hunter_001", "npc_merchant_001"],
            ),
            plan_workers=3,
        )
        elapsed = time.perf_counter() - start

    assert len(result.npc_results) == 3
    assert all(item.plan_result is not None for item in result.npc_results)
    assert elapsed < 0.45


def test_simulation_tick_execution_preview_stage_runs_in_parallel(monkeypatch) -> None:
    original_preview = simulation_tick_module.preview_task_execution

    def slow_preview(agent_state, execution_context):
        time.sleep(0.2)
        return original_preview(agent_state, execution_context)

    monkeypatch.setattr(simulation_tick_module, "preview_task_execution", slow_preview)
    monkeypatch.setattr(
        simulation_tick_module,
        "build_plan_results_parallel",
        lambda agent_states, plan_workers=None: ({}, {}, 0),
    )

    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        start = time.perf_counter()
        result = run_simulation_tick(
            connection,
            SimulationTickRequest(
                current_tick=121,
                npc_ids=["npc_guard_001", "npc_hunter_001", "npc_merchant_001"],
                include_profile=True,
            ),
            execution_workers=3,
        )
        elapsed = time.perf_counter() - start

    assert len(result.npc_results) == 3
    assert result.profile is not None
    assert result.profile.execution_worker_count == 3
    assert elapsed < 0.45


def test_simulation_tick_can_return_profile_timings() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        result = run_simulation_tick(
            connection,
            SimulationTickRequest(current_tick=120, npc_ids=["npc_hunter_001"], include_profile=True),
            execution_workers=1,
            plan_workers=1,
        )

    assert result.profile is not None
    assert result.profile.total_ms >= 0
    assert result.profile.execution_worker_count == 1
    assert result.profile.plan_worker_count == 1
    assert result.profile.npc_profiles[0].npc_id == "npc_hunter_001"


def test_simulation_tick_can_refresh_world_and_generate_visible_events() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        connection.execute(
            """
            UPDATE world_resource_nodes
            SET available_quantity = ?, last_harvested_tick = ?
            WHERE node_id = ?
            """,
            (1, 150, "res_forest_berries"),
        )
        connection.commit()

        result = run_simulation_tick(
            connection,
            SimulationTickRequest(
                current_tick=180,
                npc_ids=["npc_guard_001", "npc_hunter_001", "npc_merchant_001"],
                enable_world_updates=True,
            ),
        )
        entity_rows = connection.execute(
            "SELECT entity_id, entity_type FROM world_entities ORDER BY entity_id"
        ).fetchall()

    assert result.world_update is not None
    assert result.world_update.generated_event_ids == [
        "evt_random_monster_180",
        "evt_random_traveler_180",
    ]
    assert any(item.node_id == "res_forest_berries" for item in result.world_update.refreshed_resources)
    assert any(entity_type == "monster" for _, entity_type in entity_rows)
    assert any(entity_type == "traveler" for _, entity_type in entity_rows)
