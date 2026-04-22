import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import app.simulation_engine as simulation_engine_module
from app.simulation_engine import SimulationBusyError, SimulationEngine
from app.simulation_runtime import SimulationRuntimeConfig, load_simulation_runtime_config
from app.simulation_tick import SimulationTickRequest


def test_simulation_engine_passes_runtime_worker_limit(monkeypatch) -> None:
    recorded = {}

    def fake_run_simulation_tick(connection, request, execution_workers=None, plan_workers=None):
        recorded["connection"] = connection
        recorded["request"] = request
        recorded["execution_workers"] = execution_workers
        recorded["plan_workers"] = plan_workers
        return {"ok": True}

    monkeypatch.setattr(simulation_engine_module, "run_simulation_tick", fake_run_simulation_tick)
    engine = SimulationEngine(
        runtime_config=SimulationRuntimeConfig(
            parallel_execution_preview_enabled=True,
            execution_max_workers=3,
            parallel_planning_enabled=True,
            plan_max_workers=4,
        )
    )

    with sqlite3.connect(":memory:") as connection:
        result = engine.run_tick(connection, SimulationTickRequest(current_tick=120))

    assert result == {"ok": True}
    assert recorded["execution_workers"] == 3
    assert recorded["plan_workers"] == 4


def test_simulation_runtime_can_disable_parallel_planning(monkeypatch) -> None:
    monkeypatch.setenv("SIMULATION_PARALLEL_PLANNING", "0")
    monkeypatch.setenv("SIMULATION_PLAN_MAX_WORKERS", "8")
    monkeypatch.setenv("SIMULATION_PARALLEL_EXECUTION_PREVIEW", "0")
    monkeypatch.setenv("SIMULATION_EXECUTION_MAX_WORKERS", "6")
    monkeypatch.setenv("SIMULATION_TICK_REENTRY_MODE", "block")

    config = load_simulation_runtime_config()

    assert config.parallel_planning_enabled is False
    assert config.resolved_plan_workers() == 1
    assert config.parallel_execution_preview_enabled is False
    assert config.resolved_execution_workers() == 1
    assert config.tick_reentry_mode == "block"


def test_simulation_engine_rejects_tick_reentry_by_default(monkeypatch) -> None:
    first_started = threading.Event()
    release_first = threading.Event()

    def fake_run_simulation_tick(connection, request, execution_workers=None, plan_workers=None):
        first_started.set()
        release_first.wait(timeout=1)
        return {"tick": request.current_tick}

    monkeypatch.setattr(simulation_engine_module, "run_simulation_tick", fake_run_simulation_tick)
    engine = SimulationEngine(
        runtime_config=SimulationRuntimeConfig(
            parallel_planning_enabled=True,
            plan_max_workers=4,
            serialize_tick_requests=True,
            tick_reentry_mode="reject",
        )
    )

    with sqlite3.connect(":memory:", check_same_thread=False) as connection:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first_future = executor.submit(engine.run_tick, connection, SimulationTickRequest(current_tick=120))
            assert first_started.wait(timeout=1)
            second_future = executor.submit(engine.run_tick, connection, SimulationTickRequest(current_tick=121))
            release_first.set()

            assert first_future.result()["tick"] == 120
            try:
                second_future.result()
                assert False, "Expected SimulationBusyError"
            except SimulationBusyError as exc:
                assert str(exc) == "simulation tick already running"


def test_simulation_engine_can_block_tick_reentry(monkeypatch) -> None:
    active_count = 0
    max_active_count = 0
    state_lock = threading.Lock()

    def fake_run_simulation_tick(connection, request, execution_workers=None, plan_workers=None):
        nonlocal active_count, max_active_count
        with state_lock:
            active_count += 1
            max_active_count = max(max_active_count, active_count)
        time.sleep(0.1)
        with state_lock:
            active_count -= 1
        return {"tick": request.current_tick}

    monkeypatch.setattr(simulation_engine_module, "run_simulation_tick", fake_run_simulation_tick)
    engine = SimulationEngine(
        runtime_config=SimulationRuntimeConfig(
            parallel_planning_enabled=True,
            plan_max_workers=4,
            serialize_tick_requests=True,
            tick_reentry_mode="block",
        )
    )

    with sqlite3.connect(":memory:", check_same_thread=False) as connection:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda tick: engine.run_tick(connection, SimulationTickRequest(current_tick=tick)),
                    [120, 121],
                )
            )

    assert [item["tick"] for item in results] == [120, 121]
    assert max_active_count == 1


def test_simulation_engine_can_disable_tick_serialization(monkeypatch) -> None:
    active_count = 0
    max_active_count = 0
    state_lock = threading.Lock()

    def fake_run_simulation_tick(connection, request, execution_workers=None, plan_workers=None):
        nonlocal active_count, max_active_count
        with state_lock:
            active_count += 1
            max_active_count = max(max_active_count, active_count)
        time.sleep(0.1)
        with state_lock:
            active_count -= 1
        return {"tick": request.current_tick}

    monkeypatch.setattr(simulation_engine_module, "run_simulation_tick", fake_run_simulation_tick)
    engine = SimulationEngine(
        runtime_config=SimulationRuntimeConfig(
            parallel_planning_enabled=True,
            plan_max_workers=4,
            serialize_tick_requests=False,
        )
    )

    with sqlite3.connect(":memory:", check_same_thread=False) as connection:
        with ThreadPoolExecutor(max_workers=2) as executor:
            list(
                executor.map(
                    lambda tick: engine.run_tick(connection, SimulationTickRequest(current_tick=tick)),
                    [120, 121],
                )
            )

    assert max_active_count == 2


def test_simulation_runtime_falls_back_to_reject_for_invalid_reentry_mode(monkeypatch) -> None:
    monkeypatch.setenv("SIMULATION_TICK_REENTRY_MODE", "queue_latest")

    config = load_simulation_runtime_config()

    assert config.tick_reentry_mode == "reject"
