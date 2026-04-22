import sqlite3
from typing import Any

from app.models import DialogueHistoryRecord, DialogueTurnRecord
from app.state_repository import list_dialogue_turn_records, load_dialogue_history_record, store_dialogue_turn, upsert_dialogue_session


RECENT_DIALOGUE_TURN_LIMIT = 6
SUMMARY_EXCHANGE_LIMIT = 4
SUMMARY_MAX_LENGTH = 800


def load_dialogue_history(
    connection: sqlite3.Connection,
    npc_id: str,
    speaker_id: str,
    recent_turn_limit: int = RECENT_DIALOGUE_TURN_LIMIT,
) -> DialogueHistoryRecord:
    return load_dialogue_history_record(connection, npc_id, speaker_id, recent_turn_limit=recent_turn_limit)


def build_dialogue_context_payload(
    connection: sqlite3.Connection,
    npc_id: str,
    speaker_id: str,
    recent_turn_limit: int = RECENT_DIALOGUE_TURN_LIMIT,
) -> dict[str, Any] | None:
    history = load_dialogue_history(connection, npc_id, speaker_id, recent_turn_limit=recent_turn_limit)
    if history.total_turn_count == 0 and not history.summary:
        return None
    return {
        "summary": history.summary,
        "recent_turns": [
            {
                "speaker_id": turn.speaker_id,
                "speaker_label": turn.speaker_label,
                "role": turn.role,
                "content": turn.content,
                "created_at_tick": turn.created_at_tick,
            }
            for turn in history.recent_turns
        ],
        "total_turn_count": history.total_turn_count,
    }


def store_dialogue_exchange(
    connection: sqlite3.Connection,
    npc_id: str,
    speaker_id: str,
    npc_label: str,
    player_content: str,
    npc_reply: str,
    created_at_tick: int,
    exchange_id: str,
) -> DialogueHistoryRecord:
    store_dialogue_turn(
        connection,
        DialogueTurnRecord(
            turn_id=f"{exchange_id}_player",
            npc_id=npc_id,
            speaker_id=speaker_id,
            speaker_label=player_label_for_speaker(speaker_id),
            role="player",
            content=player_content,
            created_at_tick=created_at_tick,
        ),
    )
    store_dialogue_turn(
        connection,
        DialogueTurnRecord(
            turn_id=f"{exchange_id}_npc",
            npc_id=npc_id,
            speaker_id=speaker_id,
            speaker_label=npc_label,
            role="npc",
            content=npc_reply,
            created_at_tick=created_at_tick,
        ),
    )
    return refresh_dialogue_session_summary(connection, npc_id, speaker_id, updated_at_tick=created_at_tick)


def store_npc_dialogue_exchange(
    connection: sqlite3.Connection,
    npc_id: str,
    speaker_id: str,
    speaker_label: str,
    listener_label: str,
    speaker_content: str,
    listener_reply: str,
    created_at_tick: int,
    exchange_id: str,
) -> DialogueHistoryRecord:
    store_dialogue_turn(
        connection,
        DialogueTurnRecord(
            turn_id=f"{exchange_id}_speaker",
            npc_id=npc_id,
            speaker_id=speaker_id,
            speaker_label=speaker_label,
            role="player",
            content=speaker_content,
            created_at_tick=created_at_tick,
        ),
    )
    store_dialogue_turn(
        connection,
        DialogueTurnRecord(
            turn_id=f"{exchange_id}_listener",
            npc_id=npc_id,
            speaker_id=speaker_id,
            speaker_label=listener_label,
            role="npc",
            content=listener_reply,
            created_at_tick=created_at_tick,
        ),
    )
    return refresh_dialogue_session_summary(connection, npc_id, speaker_id, updated_at_tick=created_at_tick)


def refresh_dialogue_session_summary(
    connection: sqlite3.Connection,
    npc_id: str,
    speaker_id: str,
    updated_at_tick: int,
) -> DialogueHistoryRecord:
    all_turns = list_dialogue_turn_records(connection, npc_id, speaker_id, newest_first=False)
    archived_turns = all_turns[:-RECENT_DIALOGUE_TURN_LIMIT] if len(all_turns) > RECENT_DIALOGUE_TURN_LIMIT else []
    summary = summarize_dialogue_turns(archived_turns)
    upsert_dialogue_session(
        connection,
        npc_id,
        speaker_id,
        summary=summary,
        total_turn_count=len(all_turns),
        updated_at_tick=updated_at_tick if all_turns else None,
    )
    return load_dialogue_history(connection, npc_id, speaker_id)


def summarize_dialogue_turns(turns: list[DialogueTurnRecord]) -> str:
    if not turns:
        return ""
    exchanges = group_dialogue_exchanges(turns)
    if not exchanges:
        return ""

    summary_parts: list[str] = []
    archived_exchanges = exchanges[-SUMMARY_EXCHANGE_LIMIT:]
    if len(exchanges) > len(archived_exchanges):
        summary_parts.append(f"Earlier dialogue covered {len(exchanges)} exchanges.")

    for exchange in archived_exchanges:
        player_text = truncate_dialogue_text(exchange.get("player_text", ""))
        npc_text = truncate_dialogue_text(exchange.get("npc_text", ""))
        tick = exchange.get("created_at_tick", 0)
        if player_text and npc_text:
            summary_parts.append(f"t{tick} player: {player_text} / npc: {npc_text}")
        elif player_text:
            summary_parts.append(f"t{tick} player: {player_text}")
        elif npc_text:
            summary_parts.append(f"t{tick} npc: {npc_text}")

    return truncate_summary(" | ".join(summary_parts))


def group_dialogue_exchanges(turns: list[DialogueTurnRecord]) -> list[dict[str, Any]]:
    exchanges: list[dict[str, Any]] = []
    pending_player_turn: DialogueTurnRecord | None = None

    for turn in turns:
        if turn.role == "player":
            if pending_player_turn is not None:
                exchanges.append(
                    {
                        "created_at_tick": pending_player_turn.created_at_tick,
                        "player_text": pending_player_turn.content,
                        "npc_text": "",
                    }
                )
            pending_player_turn = turn
            continue

        if pending_player_turn is not None:
            exchanges.append(
                {
                    "created_at_tick": pending_player_turn.created_at_tick,
                    "player_text": pending_player_turn.content,
                    "npc_text": turn.content,
                }
            )
            pending_player_turn = None
            continue

        exchanges.append(
            {
                "created_at_tick": turn.created_at_tick,
                "player_text": "",
                "npc_text": turn.content,
            }
        )

    if pending_player_turn is not None:
        exchanges.append(
            {
                "created_at_tick": pending_player_turn.created_at_tick,
                "player_text": pending_player_turn.content,
                "npc_text": "",
            }
        )
    return exchanges


def truncate_dialogue_text(text: str, limit: int = 96) -> str:
    normalized = " ".join(text.strip().split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 3)].rstrip() + "..."


def truncate_summary(summary: str) -> str:
    if len(summary) <= SUMMARY_MAX_LENGTH:
        return summary
    return summary[: SUMMARY_MAX_LENGTH - 3].rstrip() + "..."


def player_label_for_speaker(speaker_id: str) -> str:
    if speaker_id.startswith("player_"):
        return "Player"
    return speaker_id
