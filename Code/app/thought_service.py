from app.fallback_rules import build_fallback_thought
from app.models import AgentState, StrictSchemaModel, ThoughtResult
from app.thought_provider import ThoughtProvider, configured_llm_thought_provider


class ThoughtRoute(StrictSchemaModel):
    mode: str
    reason: str


def generate_thought(agent_state: AgentState, provider: ThoughtProvider | None = None) -> ThoughtResult:
    route = choose_thought_route(agent_state, provider)
    thought = build_fallback_thought(agent_state)

    if route.mode == "model":
        selected_provider = provider or configured_llm_thought_provider()
        if selected_provider is not None:
            try:
                model_thought = selected_provider.think(agent_state, thought)
                return model_thought.model_copy(
                    update={
                        "notes": trim_notes(f"{model_thought.notes} route=model"),
                    }
                )
            except Exception as exc:
                return thought.model_copy(
                    update={
                        "notes": trim_notes(
                            f"{thought.notes} route=fallback; reason=model_thought_failed: "
                            f"{exc.__class__.__name__}"
                        ),
                    }
                )

    return thought.model_copy(
        update={
            "notes": trim_notes(f"{thought.notes} route={route.mode}; reason={route.reason}"),
        }
    )


def choose_thought_route(agent_state: AgentState, provider: ThoughtProvider | None = None) -> ThoughtRoute:
    if should_consider_model_thought(agent_state):
        if provider is not None or configured_llm_thought_provider() is not None:
            return ThoughtRoute(
                mode="model",
                reason="critical or high-importance state selected for model thought",
            )
        return ThoughtRoute(
            mode="fallback",
            reason="model-worthy state detected, but model thought provider is not configured",
        )
    return ThoughtRoute(
        mode="fallback",
        reason="routine state uses cheap deterministic thought",
    )


def should_consider_model_thought(agent_state: AgentState) -> bool:
    tier = agent_state.runtime_flags.priority_tier

    # Tier representatives:
    # - highest: merchant, for social/economic/player-facing dialogue
    # - high: hunter, for field intel and danger response
    # - normal: guard, for security escalation only
    if tier == "highest":
        return should_use_model_for_highest_tier(agent_state)
    if tier == "high":
        return should_use_model_for_high_tier(agent_state)
    return should_use_model_for_normal_tier(agent_state)


def should_use_model_for_highest_tier(agent_state: AgentState) -> bool:
    if has_recent_player_message(agent_state, minimum_priority=35):
        return True
    if has_recent_message(agent_state, minimum_priority=55):
        return True
    if has_recent_unverified_belief(agent_state, minimum_confidence=45):
        return True
    if any(memory.importance >= 60 for memory in agent_state.memory_summary):
        return True
    if has_player_pressure(agent_state):
        return True
    return False


def should_use_model_for_high_tier(agent_state: AgentState) -> bool:
    if has_recent_message(
        agent_state,
        minimum_priority=65,
        allowed_topics={"monster_threat", "suspicious_arrival", "help_request"},
    ):
        return True
    if has_recent_message(
        agent_state,
        minimum_priority=45,
        allowed_message_types={"warning", "threat_alert", "help_request"},
    ):
        return True
    if has_recent_player_message(agent_state, minimum_priority=50):
        return True
    if has_recent_unverified_belief(
        agent_state,
        minimum_confidence=55,
        allowed_topics={"monster_threat", "suspicious_arrival", "help_request"},
    ):
        return True
    if any(memory.importance >= 75 for memory in agent_state.memory_summary):
        return True
    return False


def should_use_model_for_normal_tier(agent_state: AgentState) -> bool:
    if agent_state.current_task.task_type in {"investigate", "report"}:
        return True
    if has_high_importance_memory(agent_state):
        return True
    if has_recent_message(
        agent_state,
        minimum_priority=80,
        allowed_topics={"monster_threat", "suspicious_arrival", "help_request"},
    ):
        return True
    if has_recent_unverified_belief(
        agent_state,
        minimum_confidence=65,
        allowed_topics={"monster_threat", "suspicious_arrival"},
    ):
        return True
    return False


def has_high_importance_memory(agent_state: AgentState) -> bool:
    return any(memory.importance >= 70 for memory in agent_state.memory_summary)


def has_player_pressure(agent_state: AgentState) -> bool:
    player_related_memory = any(
        any(related_id.startswith("player_") for related_id in memory.related_ids)
        and memory.importance >= 60
        for memory in agent_state.memory_summary
    )
    player_message = has_recent_player_message(agent_state, minimum_priority=35)
    return player_related_memory or player_message


def has_recent_message(
    agent_state: AgentState,
    minimum_priority: int = 0,
    allowed_topics: set[str] | None = None,
    allowed_message_types: set[str] | None = None,
    within_ticks: int = 40,
) -> bool:
    for message in recent_messages(agent_state, within_ticks):
        if message.priority < minimum_priority:
            continue
        if allowed_topics is not None and message.topic_hint not in allowed_topics:
            continue
        if allowed_message_types is not None and message.message_type not in allowed_message_types:
            continue
        return True
    return False


def has_recent_player_message(
    agent_state: AgentState,
    minimum_priority: int = 0,
    within_ticks: int = 40,
) -> bool:
    return any(
        message.from_id.startswith("player_") and message.priority >= minimum_priority
        for message in recent_messages(agent_state, within_ticks)
    )


def has_recent_unverified_belief(
    agent_state: AgentState,
    minimum_confidence: int = 0,
    allowed_topics: set[str] | None = None,
    within_ticks: int = 60,
) -> bool:
    current_tick = agent_state.runtime_flags.last_thought_tick
    earliest_tick = max(0, current_tick - within_ticks)
    for belief in agent_state.beliefs:
        if belief.truth_status != "unverified":
            continue
        if belief.confidence < minimum_confidence:
            continue
        if belief.created_at_tick > current_tick or belief.created_at_tick < earliest_tick:
            continue
        if allowed_topics is not None and belief.topic_hint not in allowed_topics:
            continue
        return True
    return False


def recent_messages(agent_state: AgentState, within_ticks: int) -> list:
    current_tick = agent_state.runtime_flags.last_thought_tick
    earliest_tick = max(0, current_tick - within_ticks)
    return [
        message
        for message in agent_state.message_queue
        if earliest_tick <= message.created_at_tick <= current_tick
    ]


def trim_notes(notes: str) -> str:
    return notes[:160]
