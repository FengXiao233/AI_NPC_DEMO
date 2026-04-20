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
    "talk": "talk",
    "help": "help",
    "patrol": "patrol",
    "gather": "gather",
    "hunt": "hunt",
    "flee": "flee",
    "trade": "trade",
    "investigate": "investigate",
    "warn": "talk",
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

    thought = generate_thought(agent_state)
    selected_action = select_candidate_action(thought)
    if selected_action is None:
        return ActionPlanResult(
            npc_id=npc_id,
            mode="none",
            selected_task=None,
            decision_reason="No executable candidate action was available.",
            thought=thought,
        )

    selected_task = action_to_queued_task(agent_state, thought, selected_action)
    decision = decide_task_application(agent_state, thought, selected_task)
    mode = apply_selected_task(connection, agent_state, decision, selected_task)
    connection.commit()

    return ActionPlanResult(
        npc_id=npc_id,
        mode=mode,
        selected_task=selected_task,
        decision_reason=decision["reason"],
        thought=thought,
    )


def select_candidate_action(thought: ThoughtResult) -> CandidateAction | None:
    for candidate_action in thought.candidate_actions:
        if candidate_action.action_type in ACTION_TO_TASK_TYPE:
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
    decision: dict[str, Any],
    selected_task: dict[str, Any],
) -> str:
    task_queue = [task.model_dump(mode="json") for task in agent_state.task_queue]

    if decision["mode"] == "interrupted":
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

    if has_equivalent_task(task_queue, selected_task):
        return "unchanged"

    task_queue.append(selected_task)
    update_npc_tasks(
        connection,
        agent_state.npc_id,
        current_task=agent_state.current_task.model_dump(mode="json"),
        task_queue=dedupe_task_queue(task_queue),
    )
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
