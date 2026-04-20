import json
import sqlite3
from typing import Any

from app.belief_verifier import BeliefVerificationResult, verify_investigation_task
from app.dialogue_processor import append_or_replace_message, build_belief_from_utterance
from app.models import AgentState, Message, StrictSchemaModel
from app.state_repository import load_agent_state, update_npc_message_queue, upsert_npc_belief
from scripts.init_sqlite import dump_json

SECURITY_REPORT_TARGET_NPC_ID = "npc_guard_001"


class TaskExecutionResult(StrictSchemaModel):
    npc_id: str
    executed_task: dict[str, Any]
    next_current_task: dict[str, Any]
    needs: dict[str, int]
    location_id: str
    belief_verification: BeliefVerificationResult | None = None
    report_result: dict[str, Any] | None = None


def execute_current_task_for_npc(connection: sqlite3.Connection, npc_id: str) -> TaskExecutionResult | None:
    agent_state = load_agent_state(connection, npc_id)
    if agent_state is None:
        return None

    executed_task = agent_state.current_task.model_dump(mode="json")
    needs = agent_state.needs.model_dump(mode="json")
    location_id = agent_state.location_id

    needs, location_id = apply_task_effects(executed_task, needs, location_id)
    belief_verification = None
    if executed_task["task_type"] == "investigate":
        belief_verification = verify_investigation_task(connection, agent_state, executed_task)
    report_result = None
    if executed_task["task_type"] == "report":
        report_result = execute_report_task(connection, agent_state, executed_task)
    task_queue = [task.model_dump(mode="json") for task in agent_state.task_queue]
    if belief_verification is not None and belief_verification.follow_up_task is not None:
        task_queue.append(belief_verification.follow_up_task)
    next_current_task, remaining_queue = pop_next_task_from_queue(location_id, task_queue)

    update_npc_execution_state(
        connection,
        npc_id,
        needs=needs,
        location_id=location_id,
        current_task=next_current_task,
        task_queue=remaining_queue,
    )
    connection.commit()

    return TaskExecutionResult(
        npc_id=npc_id,
        executed_task=executed_task,
        next_current_task=next_current_task,
        needs=needs,
        location_id=location_id,
        belief_verification=belief_verification,
        report_result=report_result,
    )


def apply_task_effects(
    task: dict[str, Any],
    needs: dict[str, int],
    location_id: str,
) -> tuple[dict[str, int], str]:
    task_type = task["task_type"]
    next_location_id = task["location_id"] or location_id

    if task_type == "gather":
        needs["hunger"] = clamp_need(needs["hunger"] - 20)
        needs["energy"] = clamp_need(needs["energy"] - 5)
        location_id = next_location_id
    elif task_type == "rest":
        needs["energy"] = clamp_need(needs["energy"] + 25)
        needs["hunger"] = clamp_need(needs["hunger"] + 5)
        location_id = next_location_id
    elif task_type == "flee":
        needs["safety"] = clamp_need(needs["safety"] + 25)
        needs["energy"] = clamp_need(needs["energy"] - 10)
        location_id = next_location_id
    elif task_type == "patrol":
        needs["safety"] = clamp_need(needs["safety"] + 5)
        needs["energy"] = clamp_need(needs["energy"] - 5)
        location_id = next_location_id
    elif task_type == "hunt":
        needs["hunger"] = clamp_need(needs["hunger"] - 15)
        needs["energy"] = clamp_need(needs["energy"] - 10)
        location_id = next_location_id
    elif task_type == "talk":
        needs["social"] = clamp_need(needs["social"] - 10)
        needs["energy"] = clamp_need(needs["energy"] - 2)
        needs["hunger"] = clamp_need(needs["hunger"] + 1)
    elif task_type == "trade":
        needs["hunger"] = clamp_need(needs["hunger"] + 3)
        needs["energy"] = clamp_need(needs["energy"] - 3)
        needs["social"] = clamp_need(needs["social"] - 4)
        location_id = next_location_id
    elif task_type == "help":
        needs["social"] = clamp_need(needs["social"] - 5)
        needs["energy"] = clamp_need(needs["energy"] - 8)
        location_id = next_location_id
    elif task_type == "investigate":
        needs["energy"] = clamp_need(needs["energy"] - 6)
        needs["safety"] = clamp_need(needs["safety"] - 3)
        location_id = next_location_id
    elif task_type == "report":
        needs["social"] = clamp_need(needs["social"] - 6)
        needs["energy"] = clamp_need(needs["energy"] - 3)
        location_id = next_location_id

    return needs, location_id


def execute_report_task(
    connection: sqlite3.Connection,
    agent_state: AgentState,
    task: dict[str, Any],
) -> dict[str, Any] | None:
    target_npc_id = task.get("target_id") or SECURITY_REPORT_TARGET_NPC_ID
    target_state = load_agent_state(connection, target_npc_id)
    if target_state is None:
        return None

    belief = select_reportable_belief(agent_state, task)
    if belief is None:
        return None

    source_message = next(
        (message for message in agent_state.message_queue if message.message_id == belief.source_id),
        None,
    )
    original_speaker_id = source_message.from_id if source_message is not None else agent_state.npc_id
    forwarded_message = Message(
        message_id=f"msg_{target_npc_id}_{agent_state.runtime_flags.last_thought_tick}_report_{belief.belief_id}",
        message_type="player_utterance",
        from_id=original_speaker_id,
        priority=min(100, belief.confidence + 16),
        created_at_tick=agent_state.runtime_flags.last_thought_tick,
        content=f"{agent_state.name} reported a claim: {belief.claim}",
        topic_hint=belief.topic_hint,
        credibility=belief.confidence,
    )
    target_messages = append_or_replace_message(target_state, forwarded_message)
    update_npc_message_queue(
        connection,
        target_npc_id,
        [item.model_dump(mode="json") for item in target_messages],
    )
    target_belief = build_belief_from_utterance(target_npc_id, forwarded_message)
    upsert_npc_belief(connection, target_npc_id, target_belief)
    return {
        "from_npc_id": agent_state.npc_id,
        "to_npc_id": target_npc_id,
        "belief_id": belief.belief_id,
        "forwarded_message_id": forwarded_message.message_id,
        "target_belief_id": target_belief.belief_id,
        "topic_hint": belief.topic_hint,
    }


def select_reportable_belief(agent_state: AgentState, task: dict[str, Any]):
    target_id = task.get("target_id")
    candidates = [
        belief
        for belief in agent_state.beliefs
        if belief.truth_status == "unverified"
        and belief.confidence >= 35
        and (belief.expires_at_tick is None or belief.expires_at_tick > agent_state.runtime_flags.last_thought_tick)
    ]
    if target_id is not None:
        for belief in candidates:
            if target_id in {belief.belief_id, belief.topic_hint}:
                return belief
    if not candidates:
        return None
    return max(candidates, key=lambda belief: (belief.confidence, belief.created_at_tick))


def pop_next_task(agent_state: AgentState) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    task_queue = [task.model_dump(mode="json") for task in agent_state.task_queue]
    return pop_next_task_from_queue(agent_state.location_id, task_queue)


def pop_next_task_from_queue(location_id: str, task_queue: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not task_queue:
        return idle_task(location_id), []

    next_task = max(task_queue, key=lambda task: task["priority"])
    remaining_queue = [task for task in task_queue if task["task_id"] != next_task["task_id"]]
    return queued_task_to_current_task(next_task), remaining_queue


def queued_task_to_current_task(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_type": task["task_type"],
        "target_id": task["target_id"],
        "location_id": task["location_id"],
        "priority": task["priority"],
        "interruptible": task["interruptible"],
    }


def idle_task(location_id: str) -> dict[str, Any]:
    return {
        "task_type": "idle",
        "target_id": None,
        "location_id": location_id,
        "priority": 0,
        "interruptible": True,
    }


def update_npc_execution_state(
    connection: sqlite3.Connection,
    npc_id: str,
    needs: dict[str, int],
    location_id: str,
    current_task: dict[str, Any],
    task_queue: list[dict[str, Any]],
) -> None:
    connection.execute(
        """
        UPDATE npc_state
        SET needs_json = ?,
            location_id = ?,
            current_task_json = ?,
            task_queue_json = ?
        WHERE npc_id = ?
        """,
        (
            dump_json(needs),
            location_id,
            dump_json(current_task),
            dump_json(task_queue),
            npc_id,
        ),
    )


def clamp_need(value: int) -> int:
    return max(0, min(value, 100))
