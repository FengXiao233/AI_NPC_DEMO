import json
import sqlite3
from typing import Any

from app.models import AgentState, CandidateAction, StrictSchemaModel, ThoughtResult
from app.state_repository import load_agent_state
from app.thought_service import generate_thought
from scripts.init_sqlite import dump_json


ACTION_TO_TASK_TYPE = {
    "idle": "idle",
    "rest": "rest",
    "move": "patrol",
    "chat": "chat",
    "talk": "talk",
    "help": "help",
    "patrol": "patrol",
    "gather": "gather",
    "hunt": "hunt",
    "eat": "eat",
    "flee": "flee",
    "trade": "trade",
    "plant": "plant",
    "forge": "forge",
    "heal": "heal",
    "investigate": "investigate",
    "warn": "chat",
    "report": "report",
}


class ActionPlanResult(StrictSchemaModel):
    npc_id: str
    mode: str
    selected_task: dict[str, Any] | None
    decision_reason: str
    thought: ThoughtResult


def plan_next_action_for_npc(connection: sqlite3.Connection, npc_id: str) -> ActionPlanResult | None:
    agent_state = load_agent_state(connection, npc_id)
    if agent_state is None:
        return None

    plan_result = plan_action_for_state(agent_state)
    commit_action_plan(connection, agent_state, plan_result)
    connection.commit()
    return plan_result


def plan_action_for_state(agent_state: AgentState, thought: ThoughtResult | None = None) -> ActionPlanResult:
    selected_thought = thought or generate_thought(agent_state)
    selected_action = select_candidate_action(agent_state, selected_thought)
    if selected_action is None:
        return ActionPlanResult(
            npc_id=agent_state.npc_id,
            mode="none",
            selected_task=None,
            decision_reason="No executable candidate action was available.",
            thought=selected_thought,
        )

    selected_task = action_to_queued_task(agent_state, selected_thought, selected_action)
    decision = decide_task_application(agent_state, selected_thought, selected_task)
    mode = preview_selected_task_application(agent_state, decision, selected_task)
    return ActionPlanResult(
        npc_id=agent_state.npc_id,
        mode=mode,
        selected_task=selected_task,
        decision_reason=decision["reason"],
        thought=selected_thought,
    )


def commit_action_plan(
    connection: sqlite3.Connection,
    agent_state: AgentState,
    plan_result: ActionPlanResult,
) -> None:
    if plan_result.selected_task is None or plan_result.mode in {"none", "unchanged"}:
        return
    apply_selected_task(connection, agent_state, plan_result.mode, plan_result.selected_task)


def select_candidate_action(agent_state: AgentState, thought: ThoughtResult) -> CandidateAction | None:
    for candidate_action in thought.candidate_actions:
        if candidate_action.action_type not in ACTION_TO_TASK_TYPE:
            continue
        if ACTION_TO_TASK_TYPE[candidate_action.action_type] == "talk" and not can_talk_to_target(agent_state, candidate_action.target_id):
            continue
        return candidate_action
    return None


def action_to_queued_task(
    agent_state: AgentState,
    thought: ThoughtResult,
    action: CandidateAction,
) -> dict[str, Any]:
    tick = agent_state.runtime_flags.last_thought_tick
    task_type = ACTION_TO_TASK_TYPE[action.action_type]
    priority = min(action.score + thought.interrupt_decision.priority_delta, 100)
    return {
        "task_id": f"task_{agent_state.npc_id}_{tick}_{task_type}",
        "task_type": task_type,
        "target_id": action.target_id,
        "location_id": action.location_id,
        "priority": priority,
        "interruptible": True,
        "source": "thought",
        "status": "queued",
    }


def apply_selected_task(
    connection: sqlite3.Connection,
    agent_state: AgentState,
    mode: str,
    selected_task: dict[str, Any],
) -> str:
    if selected_task["task_type"] == "chat":
        deliver_chat_message(connection, agent_state, selected_task)
        return "messaged"
    if selected_task["task_type"] == "talk":
        deliver_talk_request(connection, agent_state, selected_task)
        return "requested"

    task_queue = [task.model_dump(mode="json") for task in agent_state.task_queue]

    if mode == "interrupted":
        paused_task = agent_state.current_task.model_dump(mode="json")
        if paused_task["task_type"] != "idle":
            task_queue.append(
                {
                    "task_id": f"task_{agent_state.npc_id}_{agent_state.runtime_flags.last_thought_tick}_paused",
                    **paused_task,
                    "source": "thought",
                    "status": "paused",
                }
            )
        update_npc_tasks(
            connection,
            agent_state.npc_id,
            current_task=queued_task_to_current_task(selected_task),
            task_queue=dedupe_task_queue(task_queue),
        )
        return "interrupted"

    if mode == "unchanged" or has_equivalent_task(task_queue, selected_task):
        return "unchanged"

    task_queue.append(selected_task)
    update_npc_tasks(
        connection,
        agent_state.npc_id,
        current_task=agent_state.current_task.model_dump(mode="json"),
        task_queue=dedupe_task_queue(task_queue),
    )
    return "queued"


def preview_selected_task_application(
    agent_state: AgentState,
    decision: dict[str, Any],
    selected_task: dict[str, Any],
) -> str:
    if selected_task["task_type"] == "chat":
        return "messaged"
    if selected_task["task_type"] == "talk":
        return "requested"
    if decision["mode"] == "interrupted":
        return "interrupted"
    task_queue = [task.model_dump(mode="json") for task in agent_state.task_queue]
    if has_equivalent_task(task_queue, selected_task):
        return "unchanged"
    return "queued"


def decide_task_application(
    agent_state: AgentState,
    thought: ThoughtResult,
    selected_task: dict[str, Any],
) -> dict[str, Any]:
    if not thought.interrupt_decision.should_interrupt:
        return {
            "mode": "queued",
            "reason": "Thought suggested a task but did not request interruption.",
        }

    if not agent_state.current_task.interruptible:
        return {
            "mode": "queued",
            "reason": "Current task is not interruptible; selected task was queued.",
        }

    current_priority = agent_state.current_task.priority
    selected_priority = selected_task["priority"]
    priority_margin = selected_priority - current_priority
    reason = thought.interrupt_decision.reason

    if reason == "threat_alert":
        return {
            "mode": "interrupted",
            "reason": "Threat alert is allowed to interrupt immediately.",
        }

    if reason == "urgent_need" and priority_margin >= 15:
        return {
            "mode": "interrupted",
            "reason": "Urgent need exceeded current task priority by the switch threshold.",
        }

    if reason == "social_request" and priority_margin >= 25:
        return {
            "mode": "interrupted",
            "reason": "Social request exceeded current task priority by the switch threshold.",
        }

    return {
        "mode": "queued",
        "reason": "System rules rejected interruption because switching benefit was too small.",
    }


def queued_task_to_current_task(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_type": task["task_type"],
        "target_id": task["target_id"],
        "location_id": task["location_id"],
        "priority": task["priority"],
        "interruptible": task["interruptible"],
    }


def update_npc_tasks(
    connection: sqlite3.Connection,
    npc_id: str,
    current_task: dict[str, Any],
    task_queue: list[dict[str, Any]],
) -> None:
    connection.execute(
        """
        UPDATE npc_state
        SET current_task_json = ?,
            task_queue_json = ?
        WHERE npc_id = ?
        """,
        (
            dump_json(current_task),
            dump_json(task_queue),
            npc_id,
        ),
    )


def deliver_chat_message(
    connection: sqlite3.Connection,
    agent_state: AgentState,
    selected_task: dict[str, Any],
) -> None:
    target_id = selected_task.get("target_id")
    if target_id is None:
        return
    append_target_message(
        connection,
        target_id,
        {
            "message_id": f"msg_{target_id}_{agent_state.runtime_flags.last_thought_tick}_chat_{agent_state.npc_id}",
            "message_type": "chat",
            "from_id": agent_state.npc_id,
            "priority": selected_task["priority"],
            "created_at_tick": agent_state.runtime_flags.last_thought_tick,
            "content": f"{agent_state.name} chatted briefly while continuing their current task.",
            "topic_hint": None,
            "credibility": None,
        },
    )


def deliver_talk_request(
    connection: sqlite3.Connection,
    agent_state: AgentState,
    selected_task: dict[str, Any],
) -> None:
    target_id = selected_task.get("target_id")
    if target_id is None or not can_talk_to_target(agent_state, target_id, connection):
        return
    append_target_message(
        connection,
        target_id,
        {
            "message_id": f"msg_{target_id}_{agent_state.runtime_flags.last_thought_tick}_talk_request_{agent_state.npc_id}",
            "message_type": "talk_request",
            "from_id": agent_state.npc_id,
            "priority": selected_task["priority"],
            "created_at_tick": agent_state.runtime_flags.last_thought_tick,
            "content": f"{agent_state.name} wants to start a focused talk.",
            "topic_hint": None,
            "credibility": None,
        },
    )


def append_target_message(
    connection: sqlite3.Connection,
    target_id: str,
    message: dict[str, Any],
) -> None:
    row = connection.execute(
        "SELECT message_queue_json FROM npc_state WHERE npc_id = ?",
        (target_id,),
    ).fetchone()
    if row is None:
        return
    messages = [
        existing
        for existing in json.loads(row[0])
        if existing.get("message_id") != message["message_id"]
    ]
    messages.append(message)
    messages = sorted(messages, key=lambda item: (item["priority"], item["created_at_tick"]), reverse=True)[:10]
    connection.execute(
        "UPDATE npc_state SET message_queue_json = ? WHERE npc_id = ?",
        (dump_json(messages), target_id),
    )


def can_talk_to_target(
    agent_state: AgentState,
    target_id: str | None,
    connection: sqlite3.Connection | None = None,
) -> bool:
    if target_id is None:
        return False
    for relationship in agent_state.relationships:
        if relationship.target_id == target_id and not target_id.startswith("npc_"):
            return True
    if connection is None:
        return True
    row = connection.execute(
        "SELECT location_id FROM npc_state WHERE npc_id = ?",
        (target_id,),
    ).fetchone()
    if row is None:
        return False
    target_location = row[0]
    return target_location == agent_state.location_id


def dedupe_task_queue(task_queue: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_task_id = {}
    for task in task_queue:
        by_task_id[task["task_id"]] = task
    return list(by_task_id.values())


def has_equivalent_task(task_queue: list[dict[str, Any]], selected_task: dict[str, Any]) -> bool:
    return any(
        task["task_type"] == selected_task["task_type"]
        and task.get("target_id") == selected_task.get("target_id")
        and task.get("location_id") == selected_task.get("location_id")
        and task.get("status") == selected_task.get("status")
        for task in task_queue
    )
