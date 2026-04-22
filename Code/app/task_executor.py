import json
import json
import sqlite3
from typing import Any

from pydantic import Field

from app.belief_verifier import (
    BeliefVerificationPreview,
    BeliefVerificationResult,
    commit_belief_verification_preview,
    preview_investigation_task,
    select_belief_for_investigation,
)
from app.dialogue_history import store_npc_dialogue_exchange
from app.dialogue_processor import append_or_replace_message, build_belief_from_utterance
from app.models import AgentState, MemorySummary, Message, NpcBelief, StoredEventRecord, StrictSchemaModel
from app.event_processor import process_world_event
from app.state_repository import (
    find_event_records_by_topic,
    load_agent_state,
    store_memory_record,
    update_npc_message_queue,
    upsert_npc_belief,
)
from app.world_state import materialize_task_world_effects
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
    world_effects: dict[str, Any] | None = None


class TaskExecutionContext(StrictSchemaModel):
    investigation_evidence: list[StoredEventRecord] = Field(default_factory=list)
    report_target_state: AgentState | None = None
    report_candidate_states: list[AgentState] = Field(default_factory=list)
    talk_target_state: AgentState | None = None


class ReportDeliveryPreview(StrictSchemaModel):
    target_npc_id: str
    message_queue: list[dict[str, Any]]
    target_belief: NpcBelief | None = None
    target_memory: MemorySummary
    result: dict[str, Any]


class TaskExecutionPreview(StrictSchemaModel):
    npc_id: str
    executed_task: dict[str, Any]
    next_current_task: dict[str, Any]
    needs: dict[str, int]
    location_id: str
    task_queue: list[dict[str, Any]]
    belief_verification: BeliefVerificationResult | None = None
    report_result: dict[str, Any] | None = None
    world_effects: dict[str, Any] | None = None
    belief_verification_preview: BeliefVerificationPreview | None = None
    report_delivery: ReportDeliveryPreview | None = None


def execute_current_task_for_npc(connection: sqlite3.Connection, npc_id: str) -> TaskExecutionResult | None:
    agent_state = load_agent_state(connection, npc_id)
    if agent_state is None:
        return None

    execution_context = build_task_execution_context(connection, agent_state)
    preview = preview_task_execution(agent_state, execution_context)
    commit_task_execution_preview(connection, preview)
    connection.commit()
    return task_execution_result_from_preview(preview)


def build_task_execution_context(
    connection: sqlite3.Connection,
    agent_state: AgentState,
) -> TaskExecutionContext:
    current_task = agent_state.current_task.model_dump(mode="json")
    context = TaskExecutionContext()
    if current_task["task_type"] == "investigate":
        belief = select_belief_for_investigation(agent_state, current_task)
        if belief is not None:
            context.investigation_evidence = find_event_records_by_topic(
                connection,
                belief.topic_hint,
                current_task.get("location_id") or agent_state.location_id,
                belief.created_at_tick,
            )
    elif current_task["task_type"] == "report":
        target_npc_id = current_task.get("target_id") or SECURITY_REPORT_TARGET_NPC_ID
        context.report_target_state = load_agent_state(connection, target_npc_id)
        context.report_candidate_states = [
            state
            for row in connection.execute("SELECT npc_id FROM npc_state ORDER BY npc_id").fetchall()
            if (state := load_agent_state(connection, row[0])) is not None and state.npc_id != agent_state.npc_id
        ]
    elif current_task["task_type"] == "talk" and current_task.get("target_id") is not None:
        context.talk_target_state = load_agent_state(connection, current_task["target_id"])
    return context


def preview_task_execution(
    agent_state: AgentState,
    execution_context: TaskExecutionContext | None = None,
) -> TaskExecutionPreview:
    context = execution_context or TaskExecutionContext()
    executed_task = agent_state.current_task.model_dump(mode="json")
    needs = agent_state.needs.model_dump(mode="json")
    location_id = agent_state.location_id

    can_execute_task = can_execute_current_task(agent_state, executed_task, context)
    if can_execute_task:
        needs, location_id = apply_task_effects(executed_task, needs, location_id)
    belief_verification_preview = None
    if executed_task["task_type"] == "investigate":
        belief_verification_preview = preview_investigation_task(
            agent_state,
            executed_task,
            context.investigation_evidence,
        )
    report_delivery = None
    if executed_task["task_type"] == "report":
        report_delivery = preview_report_task(agent_state, executed_task, context.report_target_state, context.report_candidate_states)
    task_queue = [task.model_dump(mode="json") for task in agent_state.task_queue]
    if belief_verification_preview is not None and belief_verification_preview.result.follow_up_task is not None:
        task_queue.append(belief_verification_preview.result.follow_up_task)
    next_current_task, remaining_queue = pop_next_task_for_state(agent_state, location_id, task_queue)

    return TaskExecutionPreview(
        npc_id=agent_state.npc_id,
        executed_task=executed_task,
        next_current_task=next_current_task,
        needs=needs,
        location_id=location_id,
        task_queue=remaining_queue,
        belief_verification=(
            belief_verification_preview.result if belief_verification_preview is not None else None
        ),
        report_result=report_delivery.result if report_delivery is not None else None,
        belief_verification_preview=belief_verification_preview,
        report_delivery=report_delivery,
    )


def commit_task_execution_preview(
    connection: sqlite3.Connection,
    preview: TaskExecutionPreview,
) -> None:
    update_npc_execution_state(
        connection,
        preview.npc_id,
        needs=preview.needs,
        location_id=preview.location_id,
        current_task=preview.next_current_task,
        task_queue=preview.task_queue,
    )
    updated_state = load_agent_state(connection, preview.npc_id)
    if updated_state is not None:
        preview.world_effects = materialize_task_world_effects(
            connection,
            preview.npc_id,
            preview.executed_task["task_type"],
            preview.location_id,
            updated_state.runtime_flags.last_thought_tick,
            target_id=preview.executed_task.get("target_id"),
        ) or None
        if preview.world_effects is not None:
            apply_world_effect_needs(connection, preview)
        if (
            preview.executed_task["task_type"] == "hunt"
            and preview.world_effects is not None
            and preview.world_effects.get("entity_type") == "monster"
            and preview.world_effects.get("defeated") is True
        ):
            process_world_event(
                connection,
                {
                    "event_id": f"evt_{preview.npc_id}_monster_slain_{updated_state.runtime_flags.last_thought_tick}",
                    "event_type": "monster_slain",
                    "actor_id": preview.npc_id,
                    "target_id": preview.world_effects["entity_id"],
                    "location_id": preview.location_id,
                    "payload": {
                        "loot": ["meat", "trophy"],
                        "monster_kind": "monster",
                    },
                    "importance": 56,
                    "created_at_tick": updated_state.runtime_flags.last_thought_tick,
                },
            )
    if preview.belief_verification_preview is not None:
        commit_belief_verification_preview(connection, preview.belief_verification_preview)
    if preview.report_delivery is None:
        return
    update_npc_message_queue(
        connection,
        preview.report_delivery.target_npc_id,
        preview.report_delivery.message_queue,
    )
    store_memory_record(
        connection,
        preview.report_delivery.target_npc_id,
        preview.report_delivery.target_memory,
    )
    if preview.report_delivery.target_belief is not None:
        upsert_npc_belief(
            connection,
            preview.report_delivery.target_npc_id,
            preview.report_delivery.target_belief,
        )
    exchange_id = preview.report_delivery.result["forwarded_message_id"]
    store_npc_dialogue_exchange(
        connection,
        npc_id=preview.report_delivery.target_npc_id,
        speaker_id=preview.report_delivery.result["from_npc_id"],
        speaker_label=preview.report_delivery.result["from_npc_name"],
        listener_label=preview.report_delivery.result["to_npc_name"],
        speaker_content=preview.report_delivery.result["utterance"],
        listener_reply=preview.report_delivery.result["reply"],
        created_at_tick=preview.report_delivery.result["created_at_tick"],
        exchange_id=exchange_id,
    )


def task_execution_result_from_preview(preview: TaskExecutionPreview) -> TaskExecutionResult:
    return TaskExecutionResult(
        npc_id=preview.npc_id,
        executed_task=preview.executed_task,
        next_current_task=preview.next_current_task,
        needs=preview.needs,
        location_id=preview.location_id,
        belief_verification=preview.belief_verification,
        report_result=preview.report_result,
        world_effects=preview.world_effects,
    )


def apply_world_effect_needs(connection: sqlite3.Connection, preview: TaskExecutionPreview) -> None:
    if preview.world_effects is None:
        return
    needs_delta = preview.world_effects.get("needs_delta")
    if isinstance(needs_delta, dict) and needs_delta:
        preview.needs = apply_needs_delta(preview.needs, needs_delta)
        write_npc_needs(connection, preview.npc_id, preview.needs)
        refresh_recovered_need_routine(connection, preview)

    target_needs_delta = preview.world_effects.get("target_needs_delta")
    target_npc_id = preview.world_effects.get("target_npc_id")
    if (
        isinstance(target_needs_delta, dict)
        and target_needs_delta
        and isinstance(target_npc_id, str)
        and target_npc_id != preview.npc_id
    ):
        row = connection.execute(
            "SELECT needs_json FROM npc_state WHERE npc_id = ?",
            (target_npc_id,),
        ).fetchone()
        if row is None:
            return
        target_needs = apply_needs_delta(json.loads(row[0]), target_needs_delta)
        write_npc_needs(connection, target_npc_id, target_needs)


def refresh_recovered_need_routine(connection: sqlite3.Connection, preview: TaskExecutionPreview) -> None:
    if preview.executed_task["task_type"] not in {"eat", "heal"}:
        return
    if preview.next_current_task["task_type"] != preview.executed_task["task_type"]:
        return
    updated_state = load_agent_state(connection, preview.npc_id)
    if updated_state is None:
        return
    next_current_task = routine_task(updated_state, preview.location_id)
    if next_current_task["task_type"] == preview.next_current_task["task_type"]:
        return
    preview.next_current_task = next_current_task
    connection.execute(
        """
        UPDATE npc_state
        SET current_task_json = ?
        WHERE npc_id = ?
        """,
        (
            dump_json(next_current_task),
            preview.npc_id,
        ),
    )


def apply_needs_delta(needs: dict[str, int], needs_delta: dict[str, Any]) -> dict[str, int]:
    updated_needs = dict(needs)
    for need_name, raw_delta in needs_delta.items():
        if need_name not in updated_needs:
            continue
        try:
            delta = int(raw_delta)
        except (TypeError, ValueError):
            continue
        updated_needs[need_name] = clamp_need(updated_needs[need_name] + delta)
    return updated_needs


def write_npc_needs(connection: sqlite3.Connection, npc_id: str, needs: dict[str, int]) -> None:
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


def apply_task_effects(
    task: dict[str, Any],
    needs: dict[str, int],
    location_id: str,
) -> tuple[dict[str, int], str]:
    task_type = task["task_type"]
    next_location_id = task["location_id"] or location_id

    if task_type == "gather":
        needs["hunger"] = clamp_need(needs["hunger"] + 4)
        needs["energy"] = clamp_need(needs["energy"] - 7)
        location_id = next_location_id
    elif task_type == "rest":
        needs["energy"] = clamp_need(needs["energy"] + 25)
        needs["hunger"] = clamp_need(needs["hunger"] + 3)
        location_id = next_location_id
    elif task_type == "flee":
        needs["safety"] = clamp_need(needs["safety"] + 25)
        needs["energy"] = clamp_need(needs["energy"] - 12)
        needs["hunger"] = clamp_need(needs["hunger"] + 5)
        location_id = next_location_id
    elif task_type == "patrol":
        needs["safety"] = clamp_need(needs["safety"] + 5)
        needs["energy"] = clamp_need(needs["energy"] - 5)
        needs["hunger"] = clamp_need(needs["hunger"] + 2)
        location_id = next_location_id
    elif task_type == "hunt":
        needs["hunger"] = clamp_need(needs["hunger"] + 6)
        needs["energy"] = clamp_need(needs["energy"] - 13)
        needs["safety"] = clamp_need(needs["safety"] - 2)
        location_id = next_location_id
    elif task_type == "eat":
        needs["energy"] = clamp_need(needs["energy"] - 1)
        location_id = next_location_id
    elif task_type == "talk":
        needs["social"] = clamp_need(needs["social"] - 10)
        needs["energy"] = clamp_need(needs["energy"] - 2)
        needs["hunger"] = clamp_need(needs["hunger"] + 1)
    elif task_type == "chat":
        needs["social"] = clamp_need(needs["social"] - 4)
        needs["hunger"] = clamp_need(needs["hunger"] + 1)
    elif task_type == "trade":
        needs["hunger"] = clamp_need(needs["hunger"] + 2)
        needs["energy"] = clamp_need(needs["energy"] - 4)
        needs["social"] = clamp_need(needs["social"] - 3)
        location_id = next_location_id
    elif task_type == "plant":
        needs["hunger"] = clamp_need(needs["hunger"] + 4)
        needs["energy"] = clamp_need(needs["energy"] - 8)
        location_id = next_location_id
    elif task_type == "forge":
        needs["hunger"] = clamp_need(needs["hunger"] + 5)
        needs["energy"] = clamp_need(needs["energy"] - 10)
        location_id = next_location_id
    elif task_type == "heal":
        needs["hunger"] = clamp_need(needs["hunger"] + 2)
        needs["energy"] = clamp_need(needs["energy"] - 5)
        needs["social"] = clamp_need(needs["social"] - 3)
        location_id = next_location_id
    elif task_type == "help":
        needs["social"] = clamp_need(needs["social"] - 5)
        needs["energy"] = clamp_need(needs["energy"] - 8)
        needs["hunger"] = clamp_need(needs["hunger"] + 3)
        location_id = next_location_id
    elif task_type == "investigate":
        needs["energy"] = clamp_need(needs["energy"] - 6)
        needs["safety"] = clamp_need(needs["safety"] - 3)
        needs["hunger"] = clamp_need(needs["hunger"] + 2)
        location_id = next_location_id
    elif task_type == "report":
        needs["social"] = clamp_need(needs["social"] - 6)
        needs["energy"] = clamp_need(needs["energy"] - 3)
        needs["hunger"] = clamp_need(needs["hunger"] + 1)
        location_id = next_location_id

    return needs, location_id


def can_execute_current_task(
    agent_state: AgentState,
    task: dict[str, Any],
    context: TaskExecutionContext,
) -> bool:
    if task["task_type"] != "talk":
        return True
    target_id = task.get("target_id")
    if target_id is None or not str(target_id).startswith("npc_"):
        return True
    return context.talk_target_state is not None and context.talk_target_state.location_id == agent_state.location_id


def preview_report_task(
    agent_state: AgentState,
    task: dict[str, Any],
    target_state: AgentState | None,
    candidate_states: list[AgentState] | None = None,
) -> ReportDeliveryPreview | None:
    target_state = select_report_target(agent_state, task, target_state, candidate_states or [])
    if target_state is None:
        return None
    target_npc_id = target_state.npc_id

    belief = select_reportable_belief(agent_state, task)
    if belief is None:
        return None

    credibility = report_credibility_for_target(
        agent_state,
        target_state,
        belief,
        report_location_id=task.get("location_id") or agent_state.location_id,
    )
    credibility = apply_repeated_topic_boost(target_state, belief, credibility)
    forwarded_message = Message(
        message_id=f"msg_{target_npc_id}_{agent_state.runtime_flags.last_thought_tick}_report_{belief.belief_id}",
        message_type="npc_report",
        from_id=agent_state.npc_id,
        priority=min(100, credibility + 16),
        created_at_tick=agent_state.runtime_flags.last_thought_tick,
        content=f"{agent_state.name} reported a claim: {belief.claim}",
        topic_hint=belief.topic_hint,
        credibility=credibility,
    )
    target_messages = append_or_replace_message(target_state, forwarded_message)
    accepted = credibility >= 35
    is_rumor = 25 <= credibility < 55
    target_belief = (
        build_belief_from_utterance(
            target_npc_id,
            forwarded_message,
            source_type="rumor" if is_rumor else "npc_report",
        )
        if accepted
        else None
    )
    utterance = render_report_utterance(agent_state, target_state, belief)
    reply = render_report_reply(target_state, agent_state, credibility, is_rumor)
    target_memory = MemorySummary(
        memory_id=f"mem_{target_npc_id}_{forwarded_message.message_id}",
        summary=(
            f"{target_state.name} heard {agent_state.name}'s {'rumor' if is_rumor else 'report'} "
            f"with credibility {credibility}: {belief.claim}"
        ),
        importance=min(100, max(45, credibility + 10)),
        related_ids=list(dict.fromkeys(item for item in [agent_state.npc_id, belief.belief_id, belief.topic_hint] if item)),
        created_at_tick=agent_state.runtime_flags.last_thought_tick,
        expires_at_tick=agent_state.runtime_flags.last_thought_tick + 600,
    )
    return ReportDeliveryPreview(
        target_npc_id=target_npc_id,
        message_queue=[item.model_dump(mode="json") for item in target_messages],
        target_belief=target_belief,
        target_memory=target_memory,
        result={
            "from_npc_id": agent_state.npc_id,
            "to_npc_id": target_npc_id,
            "belief_id": belief.belief_id,
            "forwarded_message_id": forwarded_message.message_id,
            "target_belief_id": target_belief.belief_id if target_belief is not None else None,
            "topic_hint": belief.topic_hint,
            "credibility": credibility,
            "accepted": accepted,
            "rumor": is_rumor,
            "utterance": utterance,
            "reply": reply,
            "from_npc_name": agent_state.name,
            "to_npc_name": target_state.name,
            "created_at_tick": agent_state.runtime_flags.last_thought_tick,
        },
    )


def select_report_target(
    agent_state: AgentState,
    task: dict[str, Any],
    explicit_target_state: AgentState | None,
    candidate_states: list[AgentState],
) -> AgentState | None:
    if task.get("target_id") is not None:
        return explicit_target_state
    candidates = [state for state in candidate_states if state.npc_id != agent_state.npc_id]
    if not candidates:
        return explicit_target_state
    return max(candidates, key=lambda state: report_target_score(agent_state, state, task))


def report_target_score(source_state: AgentState, target_state: AgentState, task: dict[str, Any]) -> int:
    relationship = next(
        (item for item in source_state.relationships if item.target_id == target_state.npc_id),
        None,
    )
    score = 0
    if source_state.location_id == target_state.location_id:
        score += 35
    if target_state.role == "guard":
        score += 20
    if target_state.role in {"hunter", "merchant"}:
        score += 8
    if relationship is not None:
        score += int(relationship.trust * 0.4)
        score += int(relationship.favor * 0.2)
        score -= int(relationship.hostility * 0.5)
    score += int(task.get("priority", 0) * 0.1)
    return score


def select_reportable_belief(agent_state: AgentState, task: dict[str, Any]):
    target_id = task.get("target_id")
    candidates = [
        belief
        for belief in agent_state.beliefs
        if belief.truth_status in {"unverified", "confirmed"}
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


def report_credibility_for_target(
    source_state: AgentState,
    target_state: AgentState,
    belief: NpcBelief,
    report_location_id: str | None = None,
) -> int:
    relationship = next(
        (item for item in target_state.relationships if item.target_id == source_state.npc_id),
        None,
    )
    credibility = belief.confidence
    if belief.source_type in {"npc_report", "rumor"}:
        credibility -= 10
    source_location_id = report_location_id or source_state.location_id
    if source_location_id != target_state.location_id:
        credibility -= 12
    if relationship is not None:
        credibility += int(relationship.trust * 0.25)
        credibility += int(relationship.favor * 0.10)
        credibility -= int(relationship.hostility * 0.35)
    if belief.truth_status == "confirmed":
        credibility += 12
    return clamp_need(credibility)


def apply_repeated_topic_boost(target_state: AgentState, belief: NpcBelief, credibility: int) -> int:
    if belief.topic_hint is None:
        return credibility
    existing_sources = {
        existing.source_id
        for existing in target_state.beliefs
        if existing.topic_hint == belief.topic_hint and existing.source_id != belief.source_id
    }
    if not existing_sources:
        return credibility
    return clamp_need(credibility + min(20, 8 + len(existing_sources) * 4))


def render_report_utterance(source_state: AgentState, target_state: AgentState, belief: NpcBelief) -> str:
    return f"{target_state.name}, I need you to hear this: {belief.claim}"


def render_report_reply(target_state: AgentState, source_state: AgentState, credibility: int, is_rumor: bool) -> str:
    if credibility >= 65:
        return f"I trust this enough to act on it, {source_state.name}."
    if is_rumor:
        return f"I will treat that as a rumor for now, {source_state.name}, and look for another source."
    return f"I heard you, {source_state.name}, but I do not trust this enough yet."


def pop_next_task(agent_state: AgentState) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    task_queue = [task.model_dump(mode="json") for task in agent_state.task_queue]
    return pop_next_task_for_state(agent_state, agent_state.location_id, task_queue)


def pop_next_task_for_state(
    agent_state: AgentState,
    location_id: str,
    task_queue: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not task_queue:
        return routine_task(agent_state, location_id), []
    return pop_next_task_from_queue(location_id, task_queue)


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


def routine_task(agent_state: AgentState, location_id: str) -> dict[str, Any]:
    role = getattr(agent_state.role, "value", str(agent_state.role))
    profession = agent_state.profession.split(":", 1)[0] if agent_state.profession != "villager" else role
    identity = getattr(agent_state.identity, "value", str(agent_state.identity))
    if agent_state.needs.hunger >= 70 or (agent_state.needs.hunger >= 60 and has_food_in_inventory(agent_state)):
        return {
            "task_type": "eat",
            "target_id": None,
            "location_id": location_id,
            "priority": 70,
            "interruptible": True,
        }
    if agent_state.needs.health <= 55 and profession == "physician":
        return {
            "task_type": "heal",
            "target_id": agent_state.npc_id,
            "location_id": location_id,
            "priority": 68,
            "interruptible": True,
        }
    if agent_state.needs.energy <= 25:
        return {
            "task_type": "rest",
            "target_id": None,
            "location_id": "inn",
            "priority": 25,
            "interruptible": True,
        }
    if profession == "farmer":
        return {
            "task_type": "plant",
            "target_id": None,
            "location_id": "village_square",
            "priority": 40,
            "interruptible": True,
        }
    if profession == "blacksmith":
        return {
            "task_type": "forge",
            "target_id": None,
            "location_id": "village_square",
            "priority": 40,
            "interruptible": True,
        }
    if profession == "physician":
        return {
            "task_type": "help",
            "target_id": None,
            "location_id": "village_square",
            "priority": 32,
            "interruptible": True,
        }
    if profession == "village_chief":
        return {
            "task_type": "patrol",
            "target_id": None,
            "location_id": "village_square",
            "priority": 34,
            "interruptible": True,
        }
    if profession == "guard":
        return {
            "task_type": "patrol",
            "target_id": None,
            "location_id": location_id or "village_gate",
            "priority": 35,
            "interruptible": True,
        }
    if profession == "hunter":
        return {
            "task_type": "hunt",
            "target_id": None,
            "location_id": "forest_edge",
            "priority": 35,
            "interruptible": True,
        }
    if profession == "merchant":
        return {
            "task_type": "trade",
            "target_id": None,
            "location_id": "market",
            "priority": 32,
            "interruptible": True,
        }
    if identity == "monster" or role == "monster":
        return {
            "task_type": "hunt",
            "target_id": None,
            "location_id": location_id,
            "priority": 45,
            "interruptible": True,
        }
    if agent_state.needs.hunger >= 65:
        return {
            "task_type": "gather",
            "target_id": None,
            "location_id": "forest_edge",
            "priority": 30,
            "interruptible": True,
        }
    return {
        "task_type": "patrol",
        "target_id": None,
        "location_id": location_id,
        "priority": 20,
        "interruptible": True,
    }


def has_food_in_inventory(agent_state: AgentState) -> bool:
    food_types = {"rations", "meat", "berries", "grain", "meal"}
    return any(item.item_type in food_types and item.quantity > 0 for item in agent_state.inventory)


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
