import sqlite3

from pydantic import Field

from app.dialogue_history import build_dialogue_context_payload, store_dialogue_exchange
from app.dialogue_interpreter import DialogueInterpreter, UtteranceInterpretation, configured_llm_interpreter
from app.models import AgentState, MemorySummary, Message, NpcBelief, StrictSchemaModel
from app.state_repository import load_agent_state, store_memory_record, update_npc_message_queue, upsert_npc_belief
from scripts.init_sqlite import dump_json


class PlayerUtteranceRequest(StrictSchemaModel):
    speaker_id: str
    content: str = Field(min_length=1, max_length=500)
    created_at_tick: int = Field(ge=0)
    message_id: str | None = None


class PlayerUtteranceResult(StrictSchemaModel):
    npc_id: str
    accepted: bool
    credibility: int = Field(ge=0, le=100)
    topic_hint: str | None
    interpretation: UtteranceInterpretation
    queued_message: Message
    belief: NpcBelief | None
    npc_reply: str
    forwarded_to_npc_ids: list[str] = Field(default_factory=list)
    notes: str


TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "monster_threat": ("monster", "goblin", "wolf", "orc", "怪物", "哥布林", "狼", "兽人", "袭击"),
    "suspicious_arrival": ("stranger", "suspicious", "disguise", "merchant", "奇怪", "可疑", "伪装", "陌生人", "商人"),
    "food_shortage": ("food", "hungry", "shortage", "grain", "食物", "饥饿", "短缺", "粮食"),
    "help_request": ("help", "rescue", "hurt", "stuck", "帮", "救", "受伤", "困住"),
}

TOPIC_PRIORITY = {
    "monster_threat": 78,
    "suspicious_arrival": 62,
    "food_shortage": 48,
    "help_request": 66,
}


def receive_player_utterance(
    connection: sqlite3.Connection,
    npc_id: str,
    request: PlayerUtteranceRequest,
    interpreter: DialogueInterpreter | None = None,
) -> PlayerUtteranceResult | None:
    agent_state = load_agent_state(connection, npc_id)
    if agent_state is None:
        return None

    dialogue_context = build_dialogue_context_payload(connection, npc_id, request.speaker_id)
    interpretation = interpret_player_utterance(agent_state, request, dialogue_context, interpreter)
    topic_hint = interpretation.topic_hint
    credibility = clamp(
        estimate_credibility(agent_state, request.speaker_id, topic_hint) + interpretation.confidence_delta,
        0,
        100,
    )
    priority = estimate_priority(topic_hint, credibility, urgency=interpretation.urgency)
    message = Message(
        message_id=request.message_id or f"msg_{npc_id}_{request.created_at_tick}_player_utterance",
        message_type="player_utterance",
        from_id=request.speaker_id,
        priority=priority,
        created_at_tick=request.created_at_tick,
        content=request.content,
        topic_hint=topic_hint,
        credibility=credibility,
    )

    queued_messages = append_or_replace_message(agent_state, message)
    update_npc_message_queue(
        connection,
        npc_id,
        [item.model_dump(mode="json") for item in queued_messages],
    )
    belief = (
        build_belief_from_utterance(npc_id, message, interpretation)
        if should_form_belief(message, interpretation)
        else None
    )
    if belief is not None:
        upsert_npc_belief(connection, npc_id, belief)
    npc_reply = build_npc_reply(agent_state, interpretation, belief)
    dialogue_memory = build_memory_from_key_dialogue(agent_state, message, interpretation, npc_reply)
    if dialogue_memory is not None:
        store_memory_record(connection, npc_id, dialogue_memory)
    store_dialogue_exchange(
        connection,
        npc_id=npc_id,
        speaker_id=request.speaker_id,
        npc_label=agent_state.name,
        player_content=request.content,
        npc_reply=npc_reply,
        created_at_tick=request.created_at_tick,
        exchange_id=message.message_id,
    )
    complete_matching_talk_task(connection, agent_state, request.speaker_id)
    connection.commit()

    return PlayerUtteranceResult(
        npc_id=npc_id,
        accepted=credibility >= 35 or topic_hint is not None,
        credibility=credibility,
        topic_hint=topic_hint,
        interpretation=interpretation,
        queued_message=message,
        belief=belief,
        npc_reply=npc_reply,
        forwarded_to_npc_ids=[],
        notes=f"Player utterance interpreted by {interpretation.source}; no objective world event was created.",
    )


def interpret_player_utterance(
    agent_state: AgentState,
    request: PlayerUtteranceRequest,
    dialogue_context: dict | None = None,
    interpreter: DialogueInterpreter | None = None,
) -> UtteranceInterpretation:
    selected_interpreter = interpreter or configured_llm_interpreter()
    if selected_interpreter is not None:
        try:
            return selected_interpreter.interpret(
                agent_state,
                request.speaker_id,
                request.content,
                request.created_at_tick,
                dialogue_context,
            )
        except Exception:
            pass
    return rule_interpret_player_utterance(request.content)


def rule_interpret_player_utterance(content: str) -> UtteranceInterpretation:
    topic_hint = infer_topic_hint(content)
    should_create_belief = topic_hint is not None
    return UtteranceInterpretation(
        utterance_type="claim" if should_create_belief else "unknown",
        should_create_belief=should_create_belief,
        topic_hint=topic_hint,
        claim=content if should_create_belief else "",
        confidence_delta=0,
        urgency=TOPIC_PRIORITY.get(topic_hint or "", 35),
        speaker_intent="inform" if should_create_belief else "unknown",
        target_id=None,
        location_id=None,
        recommended_action=recommended_action_for_topic(topic_hint),
        reply_text="I heard you. I will treat that as a claim to verify." if should_create_belief else "I hear you.",
        reason="Keyword fallback interpretation.",
        source="rule",
    )


def build_npc_reply(
    agent_state: AgentState,
    interpretation: UtteranceInterpretation,
    belief: NpcBelief | None,
) -> str:
    reply = interpretation.reply_text.strip()
    if reply:
        return reply
    if belief is not None:
        return f"I will treat that as unverified information and consider what to do next."
    if interpretation.topic_hint is not None:
        return "I heard the concern, but I am not confident enough to treat it as a belief yet."
    if agent_state.role == "guard":
        return "I hear you. Keep it brief; I am on watch."
    if agent_state.role == "merchant":
        return "I hear you. If this concerns trade or trouble, be specific."
    if agent_state.role == "hunter":
        return "I hear you. If there is danger near the woods, tell me clearly."
    return "I hear you."


def infer_topic_hint(content: str) -> str | None:
    lowered = content.lower()
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return topic
    return None


def estimate_credibility(agent_state: AgentState, speaker_id: str, topic_hint: str | None) -> int:
    relationship = next(
        (item for item in agent_state.relationships if item.target_id == speaker_id),
        None,
    )
    score = 35
    if relationship is not None:
        score += int(relationship.trust * 0.35)
        score += int(relationship.favor * 0.15)
        score -= int(relationship.hostility * 0.25)

    score += agent_state.base_attributes.perception
    score += agent_state.personality.curiosity - max(agent_state.personality.prudence - 5, 0)

    if topic_hint in {"monster_threat", "suspicious_arrival"}:
        score += agent_state.personality.prudence
    if topic_hint == "help_request":
        score += agent_state.personality.kindness

    return clamp(score, 0, 100)


def estimate_priority(topic_hint: str | None, credibility: int, urgency: int = 35) -> int:
    base_priority = TOPIC_PRIORITY.get(topic_hint or "", 35)
    base_priority = max(base_priority, urgency)
    if credibility < 30:
        base_priority -= 15
    elif credibility >= 65:
        base_priority += 10
    return clamp(base_priority, 0, 100)


def append_or_replace_message(agent_state: AgentState, message: Message) -> list[Message]:
    messages = [
        existing
        for existing in agent_state.message_queue
        if existing.message_id != message.message_id
    ]
    messages.append(message)
    return sorted(messages, key=lambda item: (item.priority, item.created_at_tick), reverse=True)[:10]


def complete_matching_talk_task(
    connection: sqlite3.Connection,
    agent_state: AgentState,
    speaker_id: str,
) -> None:
    current_task = agent_state.current_task.model_dump(mode="json")
    if current_task.get("task_type") != "talk":
        return
    target_id = current_task.get("target_id")
    if target_id not in {None, speaker_id}:
        return

    task_queue = [task.model_dump(mode="json") for task in agent_state.task_queue]
    next_current_task, remaining_queue = pop_next_dialogue_task(agent_state.location_id, task_queue)
    connection.execute(
        """
        UPDATE npc_state
        SET current_task_json = ?,
            task_queue_json = ?
        WHERE npc_id = ?
        """,
        (
            dump_json(next_current_task),
            dump_json(remaining_queue),
            agent_state.npc_id,
        ),
    )


def pop_next_dialogue_task(
    location_id: str,
    task_queue: list[dict],
) -> tuple[dict, list[dict]]:
    if not task_queue:
        return idle_dialogue_task(location_id), []
    next_task = max(task_queue, key=lambda task: task["priority"])
    remaining_queue = [task for task in task_queue if task["task_id"] != next_task["task_id"]]
    return queued_dialogue_task_to_current_task(next_task), remaining_queue


def queued_dialogue_task_to_current_task(task: dict) -> dict:
    return {
        "task_type": task["task_type"],
        "target_id": task["target_id"],
        "location_id": task["location_id"],
        "priority": task["priority"],
        "interruptible": task["interruptible"],
    }


def idle_dialogue_task(location_id: str) -> dict:
    return {
        "task_type": "idle",
        "target_id": None,
        "location_id": location_id,
        "priority": 0,
        "interruptible": True,
    }


def should_form_belief(message: Message, interpretation: UtteranceInterpretation) -> bool:
    return (
        interpretation.should_create_belief
        and message.topic_hint is not None
        and (message.credibility or 0) >= 35
    )


def build_memory_from_key_dialogue(
    agent_state: AgentState,
    message: Message,
    interpretation: UtteranceInterpretation,
    npc_reply: str,
) -> MemorySummary | None:
    importance = dialogue_memory_importance(message, interpretation)
    if importance < 55:
        return None

    summary = truncate_memory_summary(
        f"Player told {agent_state.name}: {message.content or ''} "
        f"{agent_state.name} replied: {npc_reply}"
    )
    related_ids = [
        message.from_id,
        *(item for item in [message.topic_hint, interpretation.target_id, interpretation.location_id] if item),
    ]
    return MemorySummary(
        memory_id=f"mem_{agent_state.npc_id}_{message.message_id}_dialogue",
        summary=summary,
        importance=importance,
        related_ids=list(dict.fromkeys(related_ids)),
        created_at_tick=message.created_at_tick,
        expires_at_tick=message.created_at_tick + 120 + importance * 5,
    )


def dialogue_memory_importance(message: Message, interpretation: UtteranceInterpretation) -> int:
    importance = max(message.priority, interpretation.urgency)
    if interpretation.should_create_belief:
        importance += 10
    if message.topic_hint is not None:
        importance += 8
    if interpretation.recommended_action is not None:
        importance += 6
    if (message.credibility or 0) >= 65:
        importance += 5
    return clamp(importance, 0, 100)


def truncate_memory_summary(summary: str, limit: int = 300) -> str:
    normalized = " ".join(summary.strip().split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def build_belief_from_utterance(
    npc_id: str,
    message: Message,
    interpretation: UtteranceInterpretation | None = None,
    source_type: str = "player_utterance",
) -> NpcBelief:
    claim = ""
    if interpretation is not None:
        claim = interpretation.claim.strip()
    if not claim:
        claim = message.content or ""
    return NpcBelief(
        belief_id=f"belief_{npc_id}_{message.message_id}",
        source_type=source_type,
        source_id=message.message_id,
        topic_hint=message.topic_hint,
        claim=claim,
        confidence=message.credibility or 0,
        truth_status="unverified",
        created_at_tick=message.created_at_tick,
        expires_at_tick=message.created_at_tick + belief_lifetime(message),
    )


def recommended_action_for_topic(topic_hint: str | None) -> str | None:
    if topic_hint in {"monster_threat", "suspicious_arrival"}:
        return "investigate"
    if topic_hint == "food_shortage":
        return "gather"
    if topic_hint == "help_request":
        return "help"
    return None


def belief_lifetime(message: Message) -> int:
    if message.topic_hint == "monster_threat":
        return 80
    if message.topic_hint == "suspicious_arrival":
        return 60
    if message.topic_hint == "food_shortage":
        return 100
    return 50


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))
