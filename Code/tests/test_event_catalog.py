from app.event_catalog import (
    default_response_tasks_for_role,
    event_category,
    get_event_definition,
    list_event_catalog_entries,
    normalized_event_payload,
    role_event_subscriptions,
)
from app.memory_summarizer import WorldEvent


def test_event_catalog_drives_role_subscriptions() -> None:
    subscriptions = role_event_subscriptions()

    assert "monster_appeared" in subscriptions["guard"]
    assert "monster_appeared" in subscriptions["hunter"]
    assert "monster_appeared" in subscriptions["merchant"]
    assert "suspicious_arrival" in subscriptions["guard"]
    assert "suspicious_arrival" in subscriptions["merchant"]
    assert "player_stole" in subscriptions["guard"]
    assert "player_stole" in subscriptions["merchant"]


def test_unknown_event_definition_has_safe_defaults() -> None:
    definition = get_event_definition("unknown_event")

    assert definition.event_type == "unknown_event"
    assert definition.memory_bonus == 0
    assert definition.memory_lifetime == 300
    assert definition.relationship_delta is None


def test_event_catalog_classifies_payload_and_builds_role_default_tasks() -> None:
    payload = normalized_event_payload(
        "monster_appeared",
        {"monster_kind": "wolf", "count": 3, "severity": "high"},
    )
    event = WorldEvent(
        event_id="evt_catalog_monster",
        event_type="monster_appeared",
        actor_id="monster_pack_001",
        target_id=None,
        location_id="village_gate",
        payload=payload,
        importance=75,
        created_at_tick=200,
    )

    guard_tasks = default_response_tasks_for_role(event, "guard", "npc_guard_001")
    hunter_tasks = default_response_tasks_for_role(event, "hunter", "npc_hunter_001")

    assert event_category("monster_appeared") == "monster_incursion"
    assert payload["_category"] == "monster_incursion"
    assert payload["monster_kind"] == "wolf"
    assert guard_tasks[0]["task_type"] == "patrol"
    assert guard_tasks[0]["location_id"] == "village_gate"
    assert hunter_tasks[0]["task_type"] == "hunt"
    assert hunter_tasks[0]["target_id"] == "monster_pack_001"


def test_event_catalog_entries_expose_default_role_responses() -> None:
    entries = {entry.event_type: entry for entry in list_event_catalog_entries()}

    monster_entry = entries["monster_appeared"]

    assert monster_entry.category == "monster_incursion"
    assert "monster_kind" in monster_entry.payload_fields
    assert "guard" in monster_entry.routing_roles
    assert any(
        response.role == "guard"
        and response.task_type == "patrol"
        and response.location == "{event.location_id}"
        for response in monster_entry.default_role_responses
    )
