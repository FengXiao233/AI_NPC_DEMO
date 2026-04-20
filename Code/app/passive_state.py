import sqlite3

from app.state_repository import load_agent_state
from scripts.init_sqlite import dump_json


PASSIVE_NEED_DRIFT = {
    "hunger": 2,
    "energy": -1,
    "social": 1,
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
