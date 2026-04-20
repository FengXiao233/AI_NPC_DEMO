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
    if agent_state.runtime_flags.is_critical_npc and has_high_importance_memory(agent_state):
        return True
    if any(memory.importance >= 80 for memory in agent_state.memory_summary):
        return True
    if any(message.priority >= 80 for message in agent_state.message_queue):
        return True
    if has_player_pressure(agent_state):
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
    player_message = any(message.from_id.startswith("player_") for message in agent_state.message_queue)
    return player_related_memory or player_message


def trim_notes(notes: str) -> str:
    return notes[:160]
