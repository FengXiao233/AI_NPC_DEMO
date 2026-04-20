import json
from pathlib import Path

from app.models import AgentState, CandidateAction, MemorySummary, ThoughtResult
from app.thought_service import choose_thought_route, generate_thought


SEED_DIR = Path(__file__).resolve().parents[1] / "seeds" / "npcs"


def load_agent_state(seed_name: str) -> AgentState:
    return AgentState.model_validate(json.loads((SEED_DIR / seed_name).read_text(encoding="utf-8")))


class StaticThoughtProvider:
    def __init__(self, thought: ThoughtResult) -> None:
        self.thought = thought

    def think(self, *_args):
        return self.thought


class FailingThoughtProvider:
    def think(self, *_args):
        raise RuntimeError("model unavailable")


def make_model_worthy_state() -> AgentState:
    agent_state = load_agent_state("npc_guard_001.json")
    agent_state.memory_summary.append(
        MemorySummary(
            memory_id="mem_model_worthy_player_betrayal",
            summary="The player betrayed a guard during a monster attack.",
            importance=90,
            related_ids=["player_001", "monster_wolf_001"],
            created_at_tick=200,
            expires_at_tick=500,
        )
    )
    return agent_state


def test_routine_state_uses_fallback_route(monkeypatch) -> None:
    monkeypatch.delenv("ENABLE_LLM_THOUGHT", raising=False)
    agent_state = load_agent_state("npc_hunter_001.json")

    route = choose_thought_route(agent_state)
    thought = generate_thought(agent_state)

    assert route.mode == "fallback"
    assert "routine state" in route.reason
    assert "route=fallback" in thought.notes


def test_model_worthy_state_uses_fallback_when_provider_is_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("ENABLE_LLM_THOUGHT", raising=False)
    agent_state = make_model_worthy_state()

    route = choose_thought_route(agent_state)
    thought = generate_thought(agent_state)

    assert route.mode == "fallback"
    assert "model-worthy" in route.reason
    assert thought.candidate_actions
    assert "model-worthy" in thought.notes


def test_model_worthy_state_can_use_injected_model_provider(monkeypatch) -> None:
    monkeypatch.delenv("ENABLE_LLM_THOUGHT", raising=False)
    agent_state = make_model_worthy_state()
    baseline = generate_thought(agent_state)
    model_thought = baseline.model_copy(
        update={
            "primary_goal": "investigate",
            "emotional_state": "curious",
            "candidate_actions": [
                CandidateAction(
                    action_type="investigate",
                    target_id="player_001",
                    location_id="village_gate",
                    score=88,
                    reason="Model wants to verify the player's report.",
                ),
            ],
            "notes": "Model selected investigation.",
        }
    )

    route = choose_thought_route(agent_state, provider=StaticThoughtProvider(model_thought))
    thought = generate_thought(agent_state, provider=StaticThoughtProvider(model_thought))

    assert route.mode == "model"
    assert thought.primary_goal == "investigate"
    assert thought.emotional_state == "curious"
    assert thought.candidate_actions[0].score == 88
    assert "route=model" in thought.notes


def test_model_thought_failure_falls_back_to_rules(monkeypatch) -> None:
    monkeypatch.delenv("ENABLE_LLM_THOUGHT", raising=False)
    agent_state = make_model_worthy_state()

    thought = generate_thought(agent_state, provider=FailingThoughtProvider())

    assert thought.candidate_actions
    assert "route=fallback" in thought.notes
    assert "model_thought_failed" in thought.notes
