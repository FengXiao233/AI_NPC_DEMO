import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.models import AgentState, ThoughtResult


SEED_DIR = Path(__file__).resolve().parents[1] / "seeds" / "npcs"


def test_all_npc_seeds_parse_as_agent_state() -> None:
    seed_paths = sorted(SEED_DIR.glob("*.json"))

    parsed_states = [
        AgentState.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for path in seed_paths
    ]

    assert {state.npc_id for state in parsed_states} == {
        "npc_guard_001",
        "npc_hunter_001",
        "npc_merchant_001",
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
