import sqlite3
from typing import Any

from app.models import AgentState, MemorySummary, NpcBelief, StoredEventRecord, StrictSchemaModel
from app.relationship_effects import upsert_relationship
from app.state_repository import (
    find_event_records_by_topic,
    store_memory_record,
    update_npc_belief_truth_status,
)


class BeliefVerificationResult(StrictSchemaModel):
    belief_id: str
    npc_id: str
    previous_status: str
    truth_status: str
    confidence: int
    evidence_event_ids: list[str]
    memory_id: str
    follow_up_task: dict[str, Any] | None = None
    relationship_update: dict[str, Any] | None = None
    notes: str


class BeliefVerificationPreview(StrictSchemaModel):
    result: BeliefVerificationResult
    expires_at_tick: int | None = None
    memory: MemorySummary


def verify_investigation_task(
    connection: sqlite3.Connection,
    agent_state: AgentState,
    task: dict[str, Any],
) -> BeliefVerificationResult | None:
    belief = select_belief_for_investigation(agent_state, task)
    if belief is None:
        return None

    evidence_events = find_event_records_by_topic(
        connection,
        belief.topic_hint,
        task.get("location_id") or agent_state.location_id,
        belief.created_at_tick,
    )
    preview = preview_investigation_task(agent_state, task, evidence_events)
    if preview is None:
        return None
    commit_belief_verification_preview(connection, preview)
    return preview.result


def preview_investigation_task(
    agent_state: AgentState,
    task: dict[str, Any],
    evidence_events: list[StoredEventRecord],
) -> BeliefVerificationPreview | None:
    belief = select_belief_for_investigation(agent_state, task)
    if belief is None or belief.truth_status != "unverified":
        return None

    investigation_location = task.get("location_id") or agent_state.location_id
    current_tick = agent_state.runtime_flags.last_thought_tick
    if evidence_events:
        truth_status = "confirmed"
        confidence = min(100, max(belief.confidence + 20, 75))
        evidence_ids = [event.event_id for event in evidence_events]
        notes = "Investigation found matching objective world events."
    else:
        truth_status = "disproven"
        confidence = max(0, belief.confidence - 35)
        evidence_ids = []
        notes = "Investigation found no matching objective evidence at the checked location."

    expires_at_tick = belief_expiration_tick(
        belief,
        current_tick,
        lifetime_ticks=600 if truth_status == "confirmed" else 240,
    )
    memory = build_verification_memory(
        agent_state,
        belief,
        truth_status=truth_status,
        evidence_event_ids=evidence_ids,
        location_id=investigation_location,
        current_tick=current_tick,
    )
    relationship_update = build_source_relationship_update(
        agent_state,
        belief,
        truth_status,
    )
    follow_up_task = build_follow_up_task(
        agent_state,
        belief,
        truth_status=truth_status,
        location_id=investigation_location,
        current_tick=current_tick,
    )
    return BeliefVerificationPreview(
        result=BeliefVerificationResult(
            belief_id=belief.belief_id,
            npc_id=agent_state.npc_id,
            previous_status=belief.truth_status,
            truth_status=truth_status,
            confidence=confidence,
            evidence_event_ids=evidence_ids,
            memory_id=memory.memory_id,
            follow_up_task=follow_up_task,
            relationship_update=relationship_update,
            notes=notes,
        ),
        expires_at_tick=expires_at_tick,
        memory=memory,
    )


def commit_belief_verification_preview(
    connection: sqlite3.Connection,
    preview: BeliefVerificationPreview,
) -> None:
    update_npc_belief_truth_status(
        connection,
        preview.result.belief_id,
        truth_status=preview.result.truth_status,
        confidence=preview.result.confidence,
        expires_at_tick=preview.expires_at_tick,
    )
    store_memory_record(connection, preview.result.npc_id, preview.memory)

    relationship_update = preview.result.relationship_update
    if relationship_update is None:
        return
    upsert_relationship(
        connection,
        npc_id=relationship_update["npc_id"],
        target_id=relationship_update["target_id"],
        favor_delta=relationship_update["favor_delta"],
        trust_delta=relationship_update["trust_delta"],
        hostility_delta=relationship_update["hostility_delta"],
    )


def select_belief_for_investigation(agent_state: AgentState, task: dict[str, Any]) -> NpcBelief | None:
    target_id = task.get("target_id")
    active_unverified = [
        belief
        for belief in agent_state.beliefs
        if belief.truth_status == "unverified"
        and (belief.expires_at_tick is None or belief.expires_at_tick > agent_state.runtime_flags.last_thought_tick)
    ]
    if target_id is not None:
        for belief in active_unverified:
            if target_id in {belief.belief_id, belief.source_id, belief.topic_hint}:
                return belief

    if not active_unverified:
        return None
    return max(active_unverified, key=lambda belief: (belief.confidence, belief.created_at_tick))


def belief_expiration_tick(belief: NpcBelief, current_tick: int, lifetime_ticks: int) -> int:
    return max(current_tick, belief.created_at_tick) + lifetime_ticks


def build_verification_memory(
    agent_state: AgentState,
    belief: NpcBelief,
    truth_status: str,
    evidence_event_ids: list[str],
    location_id: str | None,
    current_tick: int,
) -> MemorySummary:
    if truth_status == "confirmed":
        summary = f"Investigation confirmed: {belief.claim}"
        importance = min(100, belief.confidence + 15)
    else:
        summary = f"Investigation disproved: {belief.claim}"
        importance = min(100, max(45, belief.confidence))

    related_ids = [belief.belief_id, belief.source_id, *evidence_event_ids]
    if location_id is not None:
        related_ids.append(location_id)

    return MemorySummary(
        memory_id=f"mem_{agent_state.npc_id}_{belief.belief_id}_{truth_status}",
        summary=summary,
        importance=importance,
        related_ids=list(dict.fromkeys(related_ids)),
        created_at_tick=current_tick,
        expires_at_tick=current_tick + 900,
    )


def build_follow_up_task(
    agent_state: AgentState,
    belief: NpcBelief,
    truth_status: str,
    location_id: str | None,
    current_tick: int,
) -> dict[str, Any] | None:
    if truth_status == "disproven":
        if belief.topic_hint == "suspicious_arrival" and agent_state.role == "guard":
            return queued_task(
                agent_state,
                current_tick,
                task_type="patrol",
                target_id=None,
                location_id=location_id or agent_state.location_id,
                priority=55,
                suffix="resume_patrol",
            )
        return None

    if belief.topic_hint == "monster_threat":
        if agent_state.role == "guard":
            return queued_task(
                agent_state,
                current_tick,
                task_type="patrol",
                target_id=None,
                location_id=location_id or agent_state.location_id,
                priority=86,
                suffix="secure_area",
            )
        if agent_state.role == "hunter":
            return queued_task(
                agent_state,
                current_tick,
                task_type="hunt",
                target_id=None,
                location_id=location_id or "forest_edge",
                priority=84,
                suffix="hunt_threat",
            )
        return queued_task(
            agent_state,
            current_tick,
            task_type="flee",
            target_id=None,
            location_id="village_square",
            priority=82,
            suffix="seek_safety",
        )

    if belief.topic_hint == "food_shortage":
        task_type = "trade" if agent_state.role == "merchant" else "gather"
        return queued_task(
            agent_state,
            current_tick,
            task_type=task_type,
            target_id=None,
            location_id=location_id or agent_state.location_id,
            priority=72,
            suffix="respond_food_shortage",
        )

    return None


def queued_task(
    agent_state: AgentState,
    current_tick: int,
    task_type: str,
    target_id: str | None,
    location_id: str | None,
    priority: int,
    suffix: str,
) -> dict[str, Any]:
    return {
        "task_id": f"task_{agent_state.npc_id}_{current_tick}_{suffix}",
        "task_type": task_type,
        "target_id": target_id,
        "location_id": location_id,
        "priority": priority,
        "interruptible": True,
        "source": "message",
        "status": "queued",
    }


def build_source_relationship_update(
    agent_state: AgentState,
    belief: NpcBelief,
    truth_status: str,
) -> dict[str, Any] | None:
    if belief.source_type not in {"player_utterance", "npc_report", "rumor"}:
        return None

    source_message = next(
        (message for message in agent_state.message_queue if message.message_id == belief.source_id),
        None,
    )
    if source_message is None:
        return None

    if truth_status == "confirmed":
        deltas = {"favor_delta": 2, "trust_delta": 6, "hostility_delta": -1}
    else:
        deltas = {"favor_delta": -2, "trust_delta": -8, "hostility_delta": 2}

    return {
        "npc_id": agent_state.npc_id,
        "target_id": source_message.from_id,
        **deltas,
    }
