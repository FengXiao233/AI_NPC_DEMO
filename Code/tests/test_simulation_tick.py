import json
import sqlite3

from app.simulation_tick import SimulationTickRequest, run_simulation_tick
from scripts.init_sqlite import DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR, initialize_connection


def test_simulation_tick_executes_and_plans_selected_npcs() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        result = run_simulation_tick(
            connection,
            SimulationTickRequest(current_tick=120, npc_ids=["npc_hunter_001"]),
        )
        needs_json, task_queue_json, runtime_flags_json = connection.execute(
            """
            SELECT needs_json, task_queue_json, runtime_flags_json
            FROM npc_state
            WHERE npc_id = ?
            """,
            ("npc_hunter_001",),
        ).fetchone()

    needs = json.loads(needs_json)
    task_queue = json.loads(task_queue_json)
    runtime_flags = json.loads(runtime_flags_json)

    assert result.current_tick == 120
    assert result.npc_results[0].execution_result.executed_task["task_type"] == "hunt"
    assert result.npc_results[0].plan_result.mode == "queued"
    assert needs["hunger"] == 55
    assert result.npc_results[0].passive_needs["hunger"] == 70
    assert any(task["task_type"] == "hunt" for task in task_queue)
    assert runtime_flags["last_thought_tick"] == 120


def test_simulation_tick_runs_all_npcs_when_ids_are_omitted() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        result = run_simulation_tick(
            connection,
            SimulationTickRequest(current_tick=120),
        )

    assert {npc_result.npc_id for npc_result in result.npc_results} == {
        "npc_guard_001",
        "npc_hunter_001",
        "npc_merchant_001",
    }


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
