import sqlite3

from app.dialogue_interpreter import (
    LlmDialogueInterpreter,
    UtteranceInterpretation,
    configured_llm_interpreter,
)
from app.dialogue_processor import PlayerUtteranceRequest, receive_player_utterance
from app.state_repository import list_belief_records, list_event_records, load_agent_state
from scripts.init_sqlite import DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR, initialize_connection


class StaticInterpreter:
    def __init__(self, interpretation: UtteranceInterpretation) -> None:
        self.interpretation = interpretation

    def interpret(self, *_args):
        return self.interpretation


def test_receive_player_utterance_queues_claim_on_target_npc() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        result = receive_player_utterance(
            connection,
            "npc_guard_001",
            PlayerUtteranceRequest(
                speaker_id="player_001",
                content="A suspicious merchant came to the village gate.",
                created_at_tick=210,
            ),
        )
        agent_state = load_agent_state(connection, "npc_guard_001")

    assert result is not None
    assert result.accepted is True
    assert result.topic_hint == "suspicious_arrival"
    assert result.queued_message.message_type == "player_utterance"
    assert result.queued_message.content == "A suspicious merchant came to the village gate."
    assert result.belief is not None
    assert result.belief.truth_status == "unverified"
    assert result.belief.topic_hint == "suspicious_arrival"
    assert result.npc_reply != ""
    assert agent_state is not None
    assert agent_state.message_queue[0].topic_hint == "suspicious_arrival"
    assert agent_state.message_queue[0].from_id == "player_001"
    assert agent_state.beliefs[0].topic_hint == "suspicious_arrival"


def test_player_utterance_creates_npc_belief_but_not_world_event() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        result = receive_player_utterance(
            connection,
            "npc_guard_001",
            PlayerUtteranceRequest(
                speaker_id="player_001",
                content="There is a monster near the gate.",
                created_at_tick=211,
            ),
        )
        beliefs = list_belief_records(connection, "npc_guard_001")
        events = list_event_records(connection)

    assert result is not None
    assert result.topic_hint == "monster_threat"
    assert beliefs[0].topic_hint == "monster_threat"
    assert beliefs[0].truth_status == "unverified"
    assert events == []


def test_merchant_forms_suspicious_arrival_belief_without_direct_forwarding() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        result = receive_player_utterance(
            connection,
            "npc_merchant_001",
            PlayerUtteranceRequest(
                speaker_id="player_001",
                content="A suspicious stranger came to the village gate.",
                created_at_tick=212,
                message_id="msg_player_to_merchant_suspicious",
            ),
        )
        merchant_state = load_agent_state(connection, "npc_merchant_001")
        guard_state = load_agent_state(connection, "npc_guard_001")
        merchant_beliefs = list_belief_records(connection, "npc_merchant_001")
        guard_beliefs = list_belief_records(connection, "npc_guard_001")
        events = list_event_records(connection)

    assert result is not None
    assert result.belief is not None
    assert result.belief.topic_hint == "suspicious_arrival"
    assert result.forwarded_to_npc_ids == []
    assert merchant_state is not None
    assert merchant_state.message_queue[0].topic_hint == "suspicious_arrival"
    assert guard_state is not None
    assert not any(message.topic_hint == "suspicious_arrival" for message in guard_state.message_queue)
    assert merchant_beliefs[0].topic_hint == "suspicious_arrival"
    assert merchant_beliefs[0].truth_status == "unverified"
    assert guard_beliefs == []
    assert events == []


def test_receive_player_utterance_returns_none_for_missing_npc() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        result = receive_player_utterance(
            connection,
            "missing_npc",
            PlayerUtteranceRequest(
                speaker_id="player_001",
                content="There is a monster near the gate.",
                created_at_tick=210,
            ),
        )

    assert result is None


def test_llm_interpreter_can_create_belief_without_keyword_match() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        result = receive_player_utterance(
            connection,
            "npc_guard_001",
            PlayerUtteranceRequest(
                speaker_id="player_001",
                content="The new peddler keeps watching the north road and hiding his face.",
                created_at_tick=220,
            ),
            interpreter=StaticInterpreter(
                UtteranceInterpretation(
                    utterance_type="claim",
                    should_create_belief=True,
                    topic_hint="suspicious_arrival",
                    claim="A face-covered peddler is watching the north road near the village gate.",
                    confidence_delta=12,
                    urgency=68,
                    speaker_intent="warn",
                    target_id="unknown_peddler",
                    location_id="village_gate",
                    recommended_action="investigate",
                    reply_text="Stay calm. I will check the north road and verify this.",
                    reason="The utterance describes suspicious surveillance behavior.",
                    source="llm",
                )
            ),
        )
        beliefs = list_belief_records(connection, "npc_guard_001")

    assert result is not None
    assert result.interpretation.source == "llm"
    assert result.topic_hint == "suspicious_arrival"
    assert result.belief is not None
    assert result.belief.claim == "A face-covered peddler is watching the north road near the village gate."
    assert result.npc_reply == "Stay calm. I will check the north road and verify this."
    assert beliefs[0].topic_hint == "suspicious_arrival"


def test_llm_interpreter_can_decline_belief_even_when_keyword_exists() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)

        result = receive_player_utterance(
            connection,
            "npc_guard_001",
            PlayerUtteranceRequest(
                speaker_id="player_001",
                content="That merchant costume at the festival looked suspiciously good.",
                created_at_tick=221,
            ),
            interpreter=StaticInterpreter(
                UtteranceInterpretation(
                    utterance_type="unknown",
                    should_create_belief=False,
                    topic_hint=None,
                    claim="",
                    confidence_delta=0,
                    urgency=10,
                    speaker_intent="small_talk",
                    target_id=None,
                    location_id=None,
                    recommended_action=None,
                    reply_text="That sounds like festival gossip, not a security report.",
                    reason="The player is making casual commentary, not asserting a world fact.",
                    source="llm",
                )
            ),
        )
        beliefs = list_belief_records(connection, "npc_guard_001")
        events = list_event_records(connection)

    assert result is not None
    assert result.interpretation.source == "llm"
    assert result.topic_hint is None
    assert result.belief is None
    assert result.npc_reply == "That sounds like festival gossip, not a security report."
    assert beliefs == []
    assert events == []


def test_llm_interpreter_builds_responses_api_payload() -> None:
    with sqlite3.connect(":memory:") as connection:
        initialize_connection(connection, DEFAULT_SCHEMA_PATH, DEFAULT_SEED_DIR)
        agent_state = load_agent_state(connection, "npc_guard_001")

    assert agent_state is not None
    interpreter = LlmDialogueInterpreter(
        api_key="test-key",
        model="doubao-seed-2-0-mini-260215",
        base_url="https://ark.cn-beijing.volces.com/api/v3/responses",
        api_style="responses",
    )
    payload = interpreter._build_payload(
        agent_state=agent_state,
        speaker_id="player_001",
        content="A suspicious stranger arrived at the village gate.",
        created_at_tick=230,
    )

    assert payload["model"] == "doubao-seed-2-0-mini-260215"
    assert payload["input"][0]["role"] == "system"
    assert payload["input"][0]["content"][0]["type"] == "input_text"
    assert payload["input"][1]["role"] == "user"
    assert payload["input"][1]["content"][0]["type"] == "input_text"
    assert "A suspicious stranger arrived at the village gate." in payload["input"][1]["content"][0]["text"]
    assert "reply_text" in payload["input"][1]["content"][0]["text"]
    assert payload["max_output_tokens"] == 800
    assert payload["thinking"] == {"type": "disabled"}
    assert "messages" not in payload


def test_llm_interpreter_extracts_responses_api_text() -> None:
    interpreter = LlmDialogueInterpreter(
        api_key="test-key",
        model="test-model",
        api_style="responses",
    )
    response_payload = {
        "output": [
            {
                "type": "reasoning",
                "summary": [
                    {
                        "type": "summary_text",
                        "text": "The model is deciding what JSON to return.",
                    }
                ],
            },
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": '{"should_create_belief": true}',
                    }
                ]
            }
        ]
    }

    assert interpreter._extract_response_text(response_payload) == '{"should_create_belief": true}'


def test_configured_llm_interpreter_uses_ark_responses_api_by_default(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_LLM_DIALOGUE", "1")
    monkeypatch.setenv("ARK_API_KEY", "ark-test-key")
    monkeypatch.setenv("LLM_DIALOGUE_MODEL", "doubao-seed-2-0-mini-260215")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_CHAT_COMPLETIONS_URL", raising=False)
    monkeypatch.delenv("LLM_RESPONSES_URL", raising=False)
    monkeypatch.delenv("LLM_API_STYLE", raising=False)

    interpreter = configured_llm_interpreter()

    assert interpreter is not None
    assert interpreter.api_style == "responses"
    assert interpreter.base_url == "https://ark.cn-beijing.volces.com/api/v3/responses"
    assert interpreter.model == "doubao-seed-2-0-mini-260215"
    assert interpreter.timeout_seconds == 30


def test_configured_llm_interpreter_uses_timeout_from_env(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_LLM_DIALOGUE", "1")
    monkeypatch.setenv("ARK_API_KEY", "ark-test-key")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "45")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    interpreter = configured_llm_interpreter()

    assert interpreter is not None
    assert interpreter.timeout_seconds == 45
