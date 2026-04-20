from pydantic import Field

from app.event_catalog import role_event_subscriptions
from app.memory_summarizer import WorldEvent
from app.models import StrictSchemaModel


ROLE_EVENT_SUBSCRIPTIONS = role_event_subscriptions()


class NpcRoutingProfile(StrictSchemaModel):
    npc_id: str
    role: str
    location_id: str
    is_critical_npc: bool = False
    watched_ids: list[str] = Field(default_factory=list)


def route_event_to_npcs(
    event: WorldEvent | dict,
    npc_profiles: list[NpcRoutingProfile | dict],
    critical_importance_threshold: int = 80,
) -> list[str]:
    parsed_event = event if isinstance(event, WorldEvent) else WorldEvent.model_validate(event)
    parsed_profiles = [
        profile if isinstance(profile, NpcRoutingProfile) else NpcRoutingProfile.model_validate(profile)
        for profile in npc_profiles
    ]

    recipients = [
        profile.npc_id
        for profile in parsed_profiles
        if should_receive_event(parsed_event, profile, critical_importance_threshold)
    ]
    return sorted(set(recipients))


def should_receive_event(
    event: WorldEvent,
    profile: NpcRoutingProfile,
    critical_importance_threshold: int = 80,
) -> bool:
    if profile.npc_id in event_related_ids(event):
        return True
    if event.location_id and event.location_id == profile.location_id:
        return True
    if event.event_type in ROLE_EVENT_SUBSCRIPTIONS.get(profile.role, set()):
        return True
    if set(profile.watched_ids).intersection(event_related_ids(event)):
        return True
    if profile.is_critical_npc and event.importance >= critical_importance_threshold:
        return True
    return False


def event_related_ids(event: WorldEvent) -> set[str]:
    related_ids = {
        event.actor_id,
        event.target_id,
        event.location_id,
        *event.payload.get("related_ids", []),
    }
    return {related_id for related_id in related_ids if related_id}
