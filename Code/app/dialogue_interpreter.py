import json
import os
import urllib.request
from typing import Protocol

from pydantic import Field, field_validator

from app.models import AgentState, StrictSchemaModel


ALLOWED_TOPIC_HINTS = {"monster_threat", "suspicious_arrival", "food_shortage", "help_request"}
ALLOWED_UTTERANCE_TYPES = {"claim", "request", "threat", "trade", "greeting", "question", "deception", "unknown"}


class UtteranceInterpretation(StrictSchemaModel):
    utterance_type: str = Field(default="unknown", max_length=40)
    should_create_belief: bool
    topic_hint: str | None = Field(default=None, max_length=80)
    claim: str = Field(default="", max_length=500)
    confidence_delta: int = Field(default=0, ge=-30, le=30)
    urgency: int = Field(default=35, ge=0, le=100)
    speaker_intent: str = Field(default="unknown", max_length=80)
    target_id: str | None = Field(default=None, max_length=120)
    location_id: str | None = Field(default=None, max_length=120)
    recommended_action: str | None = Field(default=None, max_length=80)
    reply_text: str = Field(default="", max_length=240)
    reason: str = Field(default="", max_length=240)
    source: str = "rule"

    @field_validator("utterance_type")
    @classmethod
    def validate_utterance_type(cls, value: str) -> str:
        return value if value in ALLOWED_UTTERANCE_TYPES else "unknown"

    @field_validator("topic_hint")
    @classmethod
    def validate_topic_hint(cls, value: str | None) -> str | None:
        if value in ALLOWED_TOPIC_HINTS:
            return value
        return None


class DialogueInterpreter(Protocol):
    def interpret(
        self,
        agent_state: AgentState,
        speaker_id: str,
        content: str,
        created_at_tick: int,
    ) -> UtteranceInterpretation:
        ...


class LlmDialogueInterpreter:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1/chat/completions",
        api_style: str = "chat_completions",
        timeout_seconds: float = 12.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.api_style = api_style
        self.timeout_seconds = timeout_seconds

    def interpret(
        self,
        agent_state: AgentState,
        speaker_id: str,
        content: str,
        created_at_tick: int,
    ) -> UtteranceInterpretation:
        payload = self._build_payload(agent_state, speaker_id, content, created_at_tick)
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
        content_text = self._extract_response_text(response_payload)
        parsed = json.loads(content_text)
        parsed["source"] = "llm"
        return UtteranceInterpretation.model_validate(parsed)

    def _build_payload(
        self,
        agent_state: AgentState,
        speaker_id: str,
        content: str,
        created_at_tick: int,
    ) -> dict:
        context = self._build_context(agent_state, speaker_id, content, created_at_tick)
        system_prompt = (
            "You interpret player utterances for an AI NPC social simulation. "
            "Return only one raw JSON object matching the requested schema. "
            "You may propose an NPC subjective belief, but you must never create objective world events. "
            "Also write a short in-character NPC reply to the player."
        )
        user_prompt = json.dumps(context, ensure_ascii=False)
        if self.api_style == "responses":
            return {
                "model": self.model,
                "input": [
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "input_text",
                                "text": system_prompt,
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": user_prompt,
                            }
                        ],
                    },
                ],
                "temperature": 0.2,
                "max_output_tokens": 800,
                "thinking": {"type": "disabled"},
            }
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        return payload

    def _build_context(
        self,
        agent_state: AgentState,
        speaker_id: str,
        content: str,
        created_at_tick: int,
    ) -> dict:
        return {
            "npc": {
                "npc_id": agent_state.npc_id,
                "name": agent_state.name,
                "role": agent_state.role,
                "location_id": agent_state.location_id,
                "needs": agent_state.needs.model_dump(mode="json"),
                "current_task": agent_state.current_task.model_dump(mode="json"),
            },
            "speaker_id": speaker_id,
            "utterance": content,
            "created_at_tick": created_at_tick,
            "active_beliefs": [
                belief.model_dump(mode="json")
                for belief in agent_state.beliefs[:5]
            ],
            "relationships": [
                relationship.model_dump(mode="json")
                for relationship in agent_state.relationships
            ],
            "allowed_topic_hints": sorted(ALLOWED_TOPIC_HINTS),
            "schema": {
                "utterance_type": "claim|request|threat|trade|greeting|question|deception|unknown",
                "should_create_belief": "boolean",
                "topic_hint": "monster_threat|suspicious_arrival|food_shortage|help_request|null",
                "claim": "string, empty if no belief",
                "confidence_delta": "integer -30..30 applied after relationship credibility",
                "urgency": "integer 0..100",
                "speaker_intent": "short string",
                "target_id": "string|null",
                "location_id": "string|null",
                "recommended_action": "string|null",
                "reply_text": "short in-character NPC reply, <=240 chars. Mention uncertainty for unverified claims.",
                "reason": "short string",
            },
            "reply_rules": [
                "Reply as the target NPC, not as a narrator.",
                "If the utterance is a verifiable event claim, acknowledge it as unverified information.",
                "Do not say the claim is objectively true unless it is already confirmed in active_beliefs.",
                "If the utterance is casual conversation, answer naturally without creating a belief.",
            ],
        }

    def _extract_response_text(self, response_payload: dict) -> str:
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
        raise ValueError("LLM response did not contain text output")


def configured_llm_interpreter() -> LlmDialogueInterpreter | None:
    if os.getenv("ENABLE_LLM_DIALOGUE", "").lower() not in {"1", "true", "yes"}:
        return None
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or os.getenv("ARK_API_KEY")
    if not api_key:
        return None
    model = os.getenv("LLM_DIALOGUE_MODEL", "gpt-4.1-mini")
    api_style = os.getenv("LLM_API_STYLE", "").lower()
    if not api_style:
        if os.getenv("LLM_RESPONSES_URL"):
            api_style = "responses"
        elif os.getenv("ARK_API_KEY") and not os.getenv("LLM_CHAT_COMPLETIONS_URL"):
            api_style = "responses"
        else:
            api_style = "chat_completions"
    if api_style == "responses":
        base_url = os.getenv("LLM_RESPONSES_URL", "https://ark.cn-beijing.volces.com/api/v3/responses")
    else:
        base_url = os.getenv("LLM_CHAT_COMPLETIONS_URL", "https://api.openai.com/v1/chat/completions")
    timeout_seconds = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
    return LlmDialogueInterpreter(
        api_key=api_key,
        model=model,
        base_url=base_url,
        api_style=api_style,
        timeout_seconds=timeout_seconds,
    )
