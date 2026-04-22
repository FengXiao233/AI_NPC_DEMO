import sqlite3

from app.state_repository import load_agent_state
from scripts.init_sqlite import dump_json


PASSIVE_NEED_DRIFT = {
    "hunger": 3,
    "energy": -1,
    "social": 2,
}


def apply_passive_state_drift(
    connection: sqlite3.Connection,
    npc_id: str,
) -> dict[str, int] | None:
    agent_state = load_agent_state(connection, npc_id)
    if agent_state is None:
        return None

    needs = agent_state.needs.model_dump(mode="json")
    for need_name, delta in PASSIVE_NEED_DRIFT.items():
        needs[need_name] = clamp_need(needs[need_name] + delta)
    if needs["hunger"] >= 85:
        needs["health"] = clamp_need(needs["health"] - 3)
    elif needs["hunger"] >= 70:
        needs["health"] = clamp_need(needs["health"] - 1)
    if needs["safety"] <= 25:
        needs["health"] = clamp_need(needs["health"] - 1)

    connection.execute(
        """
        UPDATE npc_state
        SET needs_json = ?
        WHERE npc_id = ?
        """,
        (
            dump_json(needs),
            npc_id,
        ),
    )
    return needs


def clamp_need(value: int) -> int:
    return max(0, min(value, 100))
