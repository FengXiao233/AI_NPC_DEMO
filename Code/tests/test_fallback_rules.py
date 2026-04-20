import json
from pathlib import Path

from app.fallback_rules import build_fallback_thought
from app.models import AgentState, MemorySummary, Message, NpcBelief, ThoughtResult


SEED_DIR = Path(__file__).resolve().parents[1] / "seeds" / "npcs"


def load_agent_state(seed_name: str) -> AgentState:
    return AgentState.model_validate(json.loads((SEED_DIR / seed_name).read_text(encoding="utf-8")))


def test_fallback_thought_uses_hunger_for_hunter() -> None:
    agent_state = load_agent_state("npc_hunter_001.json")

    thought = build_fallback_thought(agent_state)

    assert isinstance(thought, ThoughtResult)
    assert thought.primary_goal == "get_food"
    assert thought.emotional_state == "tense"
    assert thought.candidate_actions[0].action_type == "gather"
    assert [action.score for action in thought.candidate_actions] == sorted(
        [action.score for action in thought.candidate_actions],
        reverse=True,
    )


def test_fallback_thought_uses_threat_message_before_hunger() -> None:
    agent_state = load_agent_state("npc_guard_001.json")
    agent_state.message_queue.append(
        Message.model_validate(
            {
                "message_id": "msg_threat_001",
                "message_type": "threat_alert",
                "from_id": "npc_hunter_001",
                "priority": 90,
                "created_at_tick": 130,
            }
        )
    )

    thought = build_fallback_thought(agent_state)

    assert thought.primary_goal == "avoid_threat"
    assert thought.interrupt_decision.should_interrupt is True
    assert thought.interrupt_decision.reason == "threat_alert"
    assert thought.candidate_actions[0].action_type == "flee"


def test_fallback_thought_turns_helpful_player_memory_into_social_adjustment() -> None:
    agent_state = load_agent_state("npc_merchant_001.json")

    thought = build_fallback_thought(agent_state)

    assert thought.primary_goal == "trade"
    assert [
        adjustment
        for adjustment in thought.social_adjustments
        if adjustment.target_id == "player_001" and adjustment.trust_delta > 0
    ]


def test_fallback_thought_ignores_expired_memories() -> None:
    agent_state = load_agent_state("npc_guard_001.json")
    agent_state.runtime_flags.last_thought_tick = 200
    agent_state.memory_summary = [
        MemorySummary(
            memory_id="mem_expired_danger",
            summary="A monster attacked the gate.",
            importance=95,
            related_ids=["village_gate"],
            created_at_tick=10,
            expires_at_tick=100,
        )
    ]

    thought = build_fallback_thought(agent_state)

    assert thought.emotional_state == "calm"


def test_fallback_thought_uses_social_pressure_before_role_routine() -> None:
    agent_state = load_agent_state("npc_merchant_001.json")
    agent_state.needs.social = 80
    agent_state.memory_summary = []

    thought = build_fallback_thought(agent_state)

    assert thought.primary_goal == "maintain_relationship"
    assert thought.emotional_state == "tense"
    assert thought.interrupt_decision.should_interrupt is True
    assert thought.interrupt_decision.reason == "social_request"
    assert thought.candidate_actions[0].action_type == "talk"


def test_merchant_food_and_trade_actions_stay_in_market() -> None:
    agent_state = load_agent_state("npc_merchant_001.json")
    agent_state.needs.hunger = 80

    food_thought = build_fallback_thought(agent_state)
    assert food_thought.primary_goal == "get_food"
    assert food_thought.candidate_actions[0].action_type == "gather"
    assert food_thought.candidate_actions[0].location_id == "market"

    agent_state.needs.hunger = 30
    trade_thought = build_fallback_thought(agent_state)
    assert trade_thought.primary_goal == "trade"
    assert trade_thought.candidate_actions[0].action_type == "trade"
    assert trade_thought.candidate_actions[0].location_id == "market"


def test_fallback_thought_investigates_credible_suspicious_player_utterance() -> None:
    agent_state = load_agent_state("npc_guard_001.json")
    agent_state.message_queue.append(
        Message.model_validate(
            {
                "message_id": "msg_suspicious_arrival_001",
                "message_type": "player_utterance",
                "from_id": "player_001",
                "priority": 62,
                "created_at_tick": 210,
                "content": "村口来了一个很奇怪的商人。",
                "topic_hint": "suspicious_arrival",
                "credibility": 58,
            }
        )
    )

    thought = build_fallback_thought(agent_state)

    assert thought.primary_goal == "investigate"
    assert thought.candidate_actions[0].action_type == "investigate"
    assert thought.candidate_actions[0].target_id == "player_001"


def test_fallback_thought_treats_credible_monster_utterance_as_threat_inclination() -> None:
    agent_state = load_agent_state("npc_guard_001.json")
    agent_state.message_queue.append(
        Message.model_validate(
            {
                "message_id": "msg_monster_claim_001",
                "message_type": "player_utterance",
                "from_id": "player_001",
                "priority": 78,
                "created_at_tick": 211,
                "content": "村口有怪物。",
                "topic_hint": "monster_threat",
                "credibility": 60,
            }
        )
    )

    thought = build_fallback_thought(agent_state)

    assert thought.primary_goal == "avoid_threat"
    assert thought.emotional_state == "tense"
    assert thought.candidate_actions[0].action_type == "flee"


def test_fallback_thought_uses_npc_belief_as_subjective_fact() -> None:
    agent_state = load_agent_state("npc_guard_001.json")
    agent_state.message_queue = []
    agent_state.beliefs = [
        NpcBelief(
            belief_id="belief_guard_suspicious_001",
            source_type="player_utterance",
            source_id="msg_suspicious_001",
            topic_hint="suspicious_arrival",
            claim="A suspicious stranger entered the village.",
            confidence=70,
            truth_status="unverified",
            created_at_tick=220,
            expires_at_tick=300,
        )
    ]

    thought = build_fallback_thought(agent_state)

    assert thought.primary_goal == "investigate"
    assert thought.candidate_actions[0].action_type == "investigate"


def test_fallback_thought_does_not_reinvestigate_confirmed_suspicious_belief() -> None:
    agent_state = load_agent_state("npc_guard_001.json")
    agent_state.message_queue = []
    agent_state.beliefs = [
        NpcBelief(
            belief_id="belief_guard_suspicious_confirmed",
            source_type="player_utterance",
            source_id="msg_suspicious_confirmed",
            topic_hint="suspicious_arrival",
            claim="A suspicious stranger entered the village.",
            confidence=85,
            truth_status="confirmed",
            created_at_tick=220,
            expires_at_tick=300,
        )
    ]

    thought = build_fallback_thought(agent_state)

    assert thought.primary_goal == "patrol"
    assert thought.candidate_actions[0].action_type == "patrol"
