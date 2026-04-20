import json
from pathlib import Path

from app.models import AgentState
from app.thought_provider import (
    LlmThoughtProvider,
    build_thought_context,
    configured_llm_thought_provider,
    extract_model_text,
    normalize_thought_payload,
    parse_json_object,
)
from app.fallback_rules import build_fallback_thought


SEED_DIR = Path(__file__).resolve().parents[1] / "seeds" / "npcs"


def load_agent_state(seed_name: str) -> AgentState:
    return AgentState.model_validate(json.loads((SEED_DIR / seed_name).read_text(encoding="utf-8")))


def test_thought_provider_builds_responses_payload() -> None:
    agent_state = load_agent_state("npc_guard_001.json")
    baseline = build_fallback_thought(agent_state)
    provider = LlmThoughtProvider(
        api_key="test-key",
        model="doubao-seed-2-0-mini-260215",
        base_url="https://ark.cn-beijing.volces.com/api/v3/responses",
        api_style="responses",
    )

    payload = provider._build_payload(agent_state, baseline)

    assert payload["model"] == "doubao-seed-2-0-mini-260215"
    assert payload["input"][0]["role"] == "system"
    assert payload["input"][1]["role"] == "user"
    assert payload["input"][1]["content"][0]["type"] == "input_text"
    assert payload["max_output_tokens"] == 1200
    assert payload["thinking"] == {"type": "disabled"}
    assert "messages" not in payload


def test_thought_context_includes_baseline_and_hard_rules() -> None:
    agent_state = load_agent_state("npc_guard_001.json")
    baseline = build_fallback_thought(agent_state)

    context = build_thought_context(agent_state, baseline)

    assert context["npc_state"]["npc_id"] == "npc_guard_001"
    assert context["baseline_rule_thought"]["primary_goal"] == baseline.primary_goal
    assert "Objective world_event creation is forbidden here." in context["hard_rules"]


def test_extract_model_text_skips_responses_reasoning_items() -> None:
    response_payload = {
        "output": [
            {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "Thinking..."}],
            },
            {
                "type": "message",
                "content": [{"type": "output_text", "text": '{"primary_goal":"patrol"}'}],
            },
        ]
    }

    assert extract_model_text(response_payload) == '{"primary_goal":"patrol"}'


def test_parse_json_object_accepts_markdown_fence() -> None:
    parsed = parse_json_object('```json\n{"primary_goal":"patrol"}\n```')

    assert parsed == {"primary_goal": "patrol"}


def test_normalize_thought_payload_repairs_common_model_schema_drift() -> None:
    agent_state = load_agent_state("npc_guard_001.json")
    baseline = build_fallback_thought(agent_state)
    payload = {
        "primary_goal": "investigate",
        "emotional_state": "tense",
        "risk_attitude": 2,
        "interrupt_decision": {"should_interrupt": True, "reason": "threat_alert", "priority_delta": 22},
        "target_focus": [
            {"target_id": "belief_example", "focus_type": "information", "attention_score": 62}
        ],
        "candidate_actions": [
            {
                "action_type": "investigate",
                "target_id": "north_gate",
                "location_id": "village_gate",
                "score": 82,
                "reason": "Verify the reported suspicious masked stranger at north gate.",
            }
        ],
        "social_adjustments": [{"target_id": "player_001", "favor_delta": 3, "trust_delta": 2}],
        "notes": "Prioritize verification.",
    }

    normalized = normalize_thought_payload(payload, baseline)

    assert normalized["target_focus"][0]["focus_type"] == "event"
    assert normalized["social_adjustments"][0]["hostility_delta"] == 0
    assert normalized["social_adjustments"][0]["reason"]


def test_configured_thought_provider_requires_explicit_enable(monkeypatch) -> None:
    monkeypatch.delenv("ENABLE_LLM_THOUGHT", raising=False)
    monkeypatch.setenv("ARK_API_KEY", "ark-test-key")

    assert configured_llm_thought_provider() is None


def test_configured_thought_provider_uses_dialogue_ark_settings(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_LLM_THOUGHT", "1")
    monkeypatch.setenv("ARK_API_KEY", "ark-test-key")
    monkeypatch.setenv("LLM_DIALOGUE_MODEL", "doubao-seed-2-0-mini-260215")
    monkeypatch.setenv("LLM_API_STYLE", "responses")
    monkeypatch.setenv("LLM_RESPONSES_URL", "https://ark.cn-beijing.volces.com/api/v3/responses")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "45")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    provider = configured_llm_thought_provider()

    assert provider is not None
    assert provider.api_style == "responses"
    assert provider.base_url == "https://ark.cn-beijing.volces.com/api/v3/responses"
    assert provider.model == "doubao-seed-2-0-mini-260215"
    assert provider.timeout_seconds == 45
