import sqlite3
from threading import Lock

from app.simulation_runtime import SimulationRuntimeConfig, load_simulation_runtime_config
from app.simulation_tick import SimulationTickRequest, SimulationTickResult, run_simulation_tick


class SimulationBusyError(RuntimeError):
    pass


class SimulationEngine:
    def __init__(self, runtime_config: SimulationRuntimeConfig | None = None) -> None:
        self.runtime_config = runtime_config or load_simulation_runtime_config()
        self._tick_lock = Lock()

    def run_tick(
        self,
        connection: sqlite3.Connection,
        request: SimulationTickRequest,
    ) -> SimulationTickResult:
        if not self.runtime_config.serialize_tick_requests:
            return self._run_tick_unlocked(connection, request)
        if self.runtime_config.tick_reentry_mode == "reject":
            if not self._tick_lock.acquire(blocking=False):
                raise SimulationBusyError("simulation tick already running")
            try:
                return self._run_tick_unlocked(connection, request)
            finally:
                self._tick_lock.release()
        with self._tick_lock:
            return self._run_tick_unlocked(connection, request)

    def _run_tick_unlocked(
        self,
        connection: sqlite3.Connection,
        request: SimulationTickRequest,
    ) -> SimulationTickResult:
        return run_simulation_tick(
            connection,
            request,
            execution_workers=self.runtime_config.resolved_execution_workers(),
            plan_workers=self.runtime_config.resolved_plan_workers(),
        )


_default_engine: SimulationEngine | None = None
_default_engine_lock = Lock()


def get_default_simulation_engine() -> SimulationEngine:
    global _default_engine
    if _default_engine is None:
        with _default_engine_lock:
            if _default_engine is None:
                _default_engine = SimulationEngine()
    return _default_engine


def reset_default_simulation_engine() -> None:
    global _default_engine
    _default_engine = None
