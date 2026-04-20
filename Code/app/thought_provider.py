import json
import os
import urllib.request
from typing import Protocol

from app.models import AgentState, ThoughtResult


ALLOWED_ACTION_TYPES = {
    "idle",
    "rest",
    "move",
    "talk",
    "help",
    "patrol",
    "gather",
    "hunt",
    "flee",
    "trade",
    "investigate",
    "warn",
    "report",
}
ALLOWED_EMOTIONAL_STATES = {"calm", "tense", "afraid", "angry", "curious", "hopeful", "frustrated"}
ALLOWED_FOCUS_TYPES = {"person", "location", "object", "event"}
ALLOWED_INTERRUPT_REASONS = {
    "none",
    "urgent_need",
    "threat_alert",
    "social_request",
    "better_opportunity",
    "emotional_reaction",
}
ALLOWED_PRIMARY_GOALS = {
    "survive",
    "rest",
    "get_food",
    "patrol",
    "trade",
    "seek_help",
    "help_other",
    "hunt",
    "avoid_threat",
    "maintain_relationship",
    "investigate",
    "report",
}


class ThoughtProvider(Protocol):
    def think(self, agent_state: AgentState, baseline_thought: ThoughtResult) -> ThoughtResult:
        ...


class LlmThoughtProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        api_style: str = "responses",
        timeout_seconds: float = 45.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.api_style = api_style
        self.timeout_seconds = timeout_seconds

    def think(self, agent_state: AgentState, baseline_thought: ThoughtResult) -> ThoughtResult:
        payload = self._build_payload(agent_state, baseline_thought)
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base_url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
        content_text = extract_model_text(response_payload)
        parsed = parse_json_object(content_text)
        parsed = normalize_thought_payload(parsed, baseline_thought)
        thought = ThoughtResult.model_validate(parsed)
        return thought.model_copy(update={"notes": trim_notes(f"{thought.notes} source=llm_thought")})

    def _build_payload(self, agent_state: AgentState, baseline_thought: ThoughtResult) -> dict:
        context = build_thought_context(agent_state, baseline_thought)
        system_prompt = (
            "You are the thought layer for a key NPC in an AI social RPG simulation. "
            "Return only one raw JSON object matching the provided ThoughtResult schema. "
            "Your output is only an inclination; ActionPlanner rules will decide final task execution. "
            "Do not create objective world events. Do not invent new enum values."
        )
        user_prompt = json.dumps(context, ensure_ascii=False)
        if self.api_style == "responses":
            return {
                "model": self.model,
                "input": [
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": system_prompt}],
                    },
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": user_prompt}],
                    },
                ],
                "temperature": 0.25,
                "max_output_tokens": 1200,
                "thinking": {"type": "disabled"},
            }
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.25,
            "response_format": {"type": "json_object"},
        }


def build_thought_context(agent_state: AgentState, baseline_thought: ThoughtResult) -> dict:
    current_tick = agent_state.runtime_flags.last_thought_tick
    return {
        "npc_state": agent_state.model_dump(mode="json"),
        "recent_changes": {
            "messages": [
                message.model_dump(mode="json")
                for message in agent_state.message_queue
                if message.created_at_tick >= max(0, current_tick - 120)
            ][:8],
            "memories": [
                memory.model_dump(mode="json")
                for memory in agent_state.memory_summary
                if memory.created_at_tick >= max(0, current_tick - 240)
            ][:8],
            "beliefs": [
                belief.model_dump(mode="json")
                for belief in agent_state.beliefs
                if belief.created_at_tick >= max(0, current_tick - 240)
            ][:8],
        },
        "baseline_rule_thought": baseline_thought.model_dump(mode="json"),
        "schema": {
            "primary_goal": "survive|rest|get_food|patrol|trade|seek_help|help_other|hunt|avoid_threat|maintain_relationship|investigate|report",
            "emotional_state": "calm|tense|afraid|angry|curious|hopeful|frustrated",
            "risk_attitude": "integer -100..100",
            "interrupt_decision": {
                "should_interrupt": "boolean",
                "reason": "none|urgent_need|threat_alert|social_request|better_opportunity|emotional_reaction",
                "priority_delta": "integer",
            },
            "target_focus": "0..3 items with target_id, focus_type person|location|object|event, attention_score 0..100",
            "candidate_actions": "1..5 sorted by score descending. action_type must be idle|rest|move|talk|help|patrol|gather|hunt|flee|trade|investigate|warn|report",
            "social_adjustments": "relationship deltas only; do not mutate state directly",
            "notes": "short reason, <=160 chars",
        },
        "hard_rules": [
            "Player utterances can only influence npc_belief and thought inclinations.",
            "Objective world_event creation is forbidden here.",
            "Use investigate/report/warn/talk/etc. as candidate actions; TaskExecutor performs effects later.",
            "If should_interrupt is false, interrupt reason must be none.",
            "Candidate action scores must be sorted descending.",
        ],
    }


def extract_model_text(response_payload: dict) -> str:
    if "choices" in response_payload:
        return response_payload["choices"][0]["message"]["content"]
    output_text = response_payload.get("output_text")
    if isinstance(output_text, str) and output_text:
        return output_text
    for output_item in response_payload.get("output", []):
        if output_item.get("type") != "message":
            continue
        for content_item in output_item.get("content", []):
            if content_item.get("type") != "output_text":
                continue
            text = content_item.get("text")
            if isinstance(text, str) and text:
                return text
    raise ValueError("LLM thought response did not contain text output")


def parse_json_object(content_text: str) -> dict:
    stripped = content_text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return json.loads(stripped)


def normalize_thought_payload(payload: dict, baseline_thought: ThoughtResult) -> dict:
    baseline = baseline_thought.model_dump(mode="json")
    normalized = dict(payload)

    if normalized.get("primary_goal") not in ALLOWED_PRIMARY_GOALS:
        normalized["primary_goal"] = baseline["primary_goal"]
    if normalized.get("emotional_state") not in ALLOWED_EMOTIONAL_STATES:
        normalized["emotional_state"] = baseline["emotional_state"]
    normalized["risk_attitude"] = clamp_int(normalized.get("risk_attitude", baseline["risk_attitude"]), -100, 100)
    normalized["interrupt_decision"] = normalize_interrupt_decision(
        normalized.get("interrupt_decision"),
        baseline["interrupt_decision"],
    )
    normalized["target_focus"] = normalize_target_focus(normalized.get("target_focus", []))
    normalized["candidate_actions"] = normalize_candidate_actions(
        normalized.get("candidate_actions", []),
        baseline["candidate_actions"],
    )
    normalized["social_adjustments"] = normalize_social_adjustments(normalized.get("social_adjustments", []))
    normalized["notes"] = trim_notes(str(normalized.get("notes") or baseline["notes"]))
    return normalized


def normalize_interrupt_decision(value, baseline: dict) -> dict:
    decision = dict(value) if isinstance(value, dict) else dict(baseline)
    decision["should_interrupt"] = bool(decision.get("should_interrupt", baseline["should_interrupt"]))
    if decision.get("reason") not in ALLOWED_INTERRUPT_REASONS:
        decision["reason"] = baseline["reason"]
    if decision["should_interrupt"] is False:
        decision["reason"] = "none"
    decision["priority_delta"] = clamp_int(decision.get("priority_delta", baseline["priority_delta"]), -100, 100)
    return decision


def normalize_target_focus(value) -> list[dict]:
    focus_items = value if isinstance(value, list) else []
    normalized = []
    for item in focus_items:
        if not isinstance(item, dict) or not item.get("target_id"):
            continue
        focus_type = item.get("focus_type")
        if focus_type not in ALLOWED_FOCUS_TYPES:
            focus_type = infer_focus_type(str(item["target_id"]))
        normalized.append(
            {
                "target_id": str(item["target_id"])[:120],
                "focus_type": focus_type,
                "attention_score": clamp_int(item.get("attention_score", 50), 0, 100),
            }
        )
    return normalized[:3]


def normalize_candidate_actions(value, baseline: list[dict]) -> list[dict]:
    action_items = value if isinstance(value, list) else []
    normalized = []
    for item in action_items:
        if not isinstance(item, dict) or item.get("action_type") not in ALLOWED_ACTION_TYPES:
            continue
        normalized.append(
            {
                "action_type": item["action_type"],
                "target_id": item.get("target_id"),
                "location_id": item.get("location_id"),
                "score": clamp_int(item.get("score", 50), 0, 100),
                "reason": str(item.get("reason") or "Model suggested this action.")[:120],
            }
        )
    if not normalized:
        normalized = list(baseline)
    return sorted(normalized, key=lambda action: action["score"], reverse=True)[:5]


def normalize_social_adjustments(value) -> list[dict]:
    adjustment_items = value if isinstance(value, list) else []
    normalized = []
    for item in adjustment_items:
        if not isinstance(item, dict) or not item.get("target_id"):
            continue
        normalized.append(
            {
                "target_id": str(item["target_id"])[:120],
                "favor_delta": clamp_int(item.get("favor_delta", 0), -20, 20),
                "trust_delta": clamp_int(item.get("trust_delta", 0), -20, 20),
                "hostility_delta": clamp_int(item.get("hostility_delta", 0), -20, 20),
                "reason": str(item.get("reason") or "Model inferred a social attitude shift.")[:160],
            }
        )
    return normalized


def infer_focus_type(target_id: str) -> str:
    if target_id.startswith("npc_") or target_id.startswith("player_"):
        return "person"
    if target_id.startswith("belief_") or target_id.startswith("event_"):
        return "event"
    if "gate" in target_id or "market" in target_id or "forest" in target_id or "village" in target_id:
        return "location"
    return "object"


def clamp_int(value, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(maximum, number))


def configured_llm_thought_provider() -> LlmThoughtProvider | None:
    if os.getenv("ENABLE_LLM_THOUGHT", "").lower() not in {"1", "true", "yes"}:
        return None
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or os.getenv("ARK_API_KEY")
    if not api_key:
        return None
    model = os.getenv("LLM_THOUGHT_MODEL") or os.getenv("LLM_DIALOGUE_MODEL", "gpt-4.1-mini")
    api_style = os.getenv("LLM_THOUGHT_API_STYLE") or os.getenv("LLM_API_STYLE", "chat_completions")
    api_style = api_style.lower()
    if api_style == "responses":
        base_url = os.getenv("LLM_THOUGHT_RESPONSES_URL") or os.getenv(
            "LLM_RESPONSES_URL",
            "https://ark.cn-beijing.volces.com/api/v3/responses",
        )
    else:
        base_url = os.getenv("LLM_THOUGHT_CHAT_COMPLETIONS_URL") or os.getenv(
            "LLM_CHAT_COMPLETIONS_URL",
            "https://api.openai.com/v1/chat/completions",
        )
    timeout_seconds = float(os.getenv("LLM_THOUGHT_TIMEOUT_SECONDS") or os.getenv("LLM_TIMEOUT_SECONDS", "45"))
    return LlmThoughtProvider(
        api_key=api_key,
        model=model,
        base_url=base_url,
        api_style=api_style,
        timeout_seconds=timeout_seconds,
    )


def trim_notes(notes: str) -> str:
    return notes[:160]
