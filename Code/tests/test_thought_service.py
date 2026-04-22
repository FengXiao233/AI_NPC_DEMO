import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.models import AgentState, ThoughtResult
from app.thought_service import should_consider_model_thought


SEED_DIR = Path(__file__).resolve().parents[1] / "seeds" / "npcs"


def load_seed_agent_state(seed_name: str) -> AgentState:
    return AgentState.model_validate(json.loads((SEED_DIR / seed_name).read_text(encoding="utf-8")))


def test_all_npc_seeds_parse_as_agent_state() -> None:
    seed_paths = sorted(SEED_DIR.glob("*.json"))

    parsed_states = [
        AgentState.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for path in seed_paths
    ]

    assert {state.npc_id for state in parsed_states} == {
        "npc_blacksmith_001",
        "npc_farmer_001",
        "npc_guard_001",
        "npc_hunter_001",
        "npc_merchant_001",
        "npc_physician_001",
        "npc_village_chief_001",
    }


def test_thought_endpoint_returns_thought_result_for_seed_states() -> None:
    client = TestClient(app)

    for seed_path in sorted(SEED_DIR.glob("*.json")):
        response = client.post(
            "/thought",
            json=json.loads(seed_path.read_text(encoding="utf-8")),
        )

        assert response.status_code == 200
        thought_result = ThoughtResult.model_validate(response.json())
        scores = [action.score for action in thought_result.candidate_actions]
        assert scores == sorted(scores, reverse=True)


def test_merchant_highest_tier_uses_model_for_player_contact() -> None:
    agent_state = load_seed_agent_state("npc_merchant_001.json")

    assert should_consider_model_thought(agent_state) is True


def test_hunter_high_tier_uses_model_for_field_warning() -> None:
    agent_state = load_seed_agent_state("npc_hunter_001.json")
    agent_state.runtime_flags.last_thought_tick = 120

    assert should_consider_model_thought(agent_state) is True


def test_guard_normal_tier_skips_model_for_routine_patrol_chat() -> None:
    agent_state = load_seed_agent_state("npc_guard_001.json")
    agent_state.message_queue = [
        message.model_copy(update={"from_id": "player_001", "priority": 40, "topic_hint": None})
        for message in agent_state.message_queue
    ]

    assert should_consider_model_thought(agent_state) is False
