import os

from pydantic import field_validator

from app.models import StrictSchemaModel


class SimulationRuntimeConfig(StrictSchemaModel):
    parallel_execution_preview_enabled: bool = True
    execution_max_workers: int = 0
    parallel_planning_enabled: bool = True
    plan_max_workers: int = 0
    serialize_tick_requests: bool = True
    tick_reentry_mode: str = "reject"

    @field_validator("tick_reentry_mode")
    @classmethod
    def validate_tick_reentry_mode(cls, value: str) -> str:
        if value in {"block", "reject"}:
            return value
        return "reject"

    def resolved_execution_workers(self) -> int | None:
        if not self.parallel_execution_preview_enabled:
            return 1
        if self.execution_max_workers <= 0:
            return None
        return self.execution_max_workers

    def resolved_plan_workers(self) -> int | None:
        if not self.parallel_planning_enabled:
            return 1
        if self.plan_max_workers <= 0:
            return None
        return self.plan_max_workers


def load_simulation_runtime_config() -> SimulationRuntimeConfig:
    return SimulationRuntimeConfig(
        parallel_execution_preview_enabled=_env_flag("SIMULATION_PARALLEL_EXECUTION_PREVIEW", default=True),
        execution_max_workers=_env_int("SIMULATION_EXECUTION_MAX_WORKERS", default=0),
        parallel_planning_enabled=_env_flag("SIMULATION_PARALLEL_PLANNING", default=True),
        plan_max_workers=_env_int("SIMULATION_PLAN_MAX_WORKERS", default=0),
        serialize_tick_requests=_env_flag("SIMULATION_SERIALIZE_TICKS", default=True),
        tick_reentry_mode=_env_text("SIMULATION_TICK_REENTRY_MODE", default="reject"),
    )


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_text(name: str, default: str) -> str:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw
