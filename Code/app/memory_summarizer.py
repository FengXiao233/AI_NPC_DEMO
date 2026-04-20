from typing import Any

from pydantic import Field

from app.event_catalog import get_event_definition
from app.models import MemorySummary, StrictSchemaModel


class WorldEvent(StrictSchemaModel):
    event_id: str
    event_type: str
    actor_id: str | None = None
    target_id: str | None = None
    location_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    importance: int = Field(default=0, ge=0, le=100)
    created_at_tick: int = Field(ge=0)


# TODO: Add gradual importance decay and last_recalled_tick if memory behavior needs more nuance.
# 除非用户主动要求解决，否则在代码编写过程中忽略


def summarize_events_for_npc(
    npc_id: str,
    events: list[WorldEvent | dict[str, Any]],
    max_items: int = 5,
    minimum_importance: int = 50,
    already_routed: bool = False,
) -> list[MemorySummary]:
    parsed_events = [event if isinstance(event, WorldEvent) else WorldEvent.model_validate(event) for event in events]
    ranked_events = [
        (score_event_for_npc(npc_id, event), event)
        for event in parsed_events
        if already_routed or is_event_relevant_to_npc(npc_id, event)
    ]
    ranked_events = [
        (score, event)
        for score, event in ranked_events
        if score >= minimum_importance or get_event_definition(event.event_type).significant
    ]
    ranked_events.sort(key=lambda scored_event: (scored_event[0], scored_event[1].created_at_tick), reverse=True)

    return [
        MemorySummary(
            memory_id=f"mem_{npc_id}_{event.event_id}",
            summary=render_event_summary(event),
            importance=score,
            related_ids=related_ids_for_event(event),
            created_at_tick=event.created_at_tick,
            expires_at_tick=calculate_expires_at_tick(event, score),
        )
        for score, event in ranked_events[:max_items]
    ]


def is_event_relevant_to_npc(npc_id: str, event: WorldEvent) -> bool:
    return npc_id in related_ids_for_event(event)


def score_event_for_npc(npc_id: str, event: WorldEvent) -> int:
    score = event.importance + get_event_definition(event.event_type).memory_bonus

    if event.actor_id == npc_id:
        score += 20
    if event.target_id == npc_id:
        score += 25
    if npc_id in event.payload.get("related_ids", []):
        score += 15

    return min(score, 100)


def related_ids_for_event(event: WorldEvent) -> list[str]:
    related_ids = [
        event.actor_id,
        event.target_id,
        event.location_id,
        *event.payload.get("related_ids", []),
    ]
    return list(dict.fromkeys(related_id for related_id in related_ids if related_id))


def render_event_summary(event: WorldEvent) -> str:
    actor = event.actor_id or "Someone"
    target = event.target_id or "someone"
    location = event.location_id or "an unknown place"
    monster_kind = event.payload.get("monster_kind") or event.payload.get("monster_id") or actor
    count = event.payload.get("count", 1)
    monster_label = f"{count} {monster_kind}" if count != 1 else str(monster_kind)

    template = get_event_definition(event.event_type).summary_template
    return template.format(
        actor=actor,
        target=target,
        location=location,
        event_type=event.event_type,
        monster_label=monster_label,
        **event.payload,
    )


def calculate_expires_at_tick(event: WorldEvent, importance: int) -> int:
    base_lifetime = get_event_definition(event.event_type).memory_lifetime
    return event.created_at_tick + base_lifetime + importance * 5
