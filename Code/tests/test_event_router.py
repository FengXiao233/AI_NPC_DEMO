from app.event_router import route_event_to_npcs


NPC_PROFILES = [
    {
        "npc_id": "npc_guard_001",
        "role": "guard",
        "location_id": "village_gate",
        "is_critical_npc": True,
        "watched_ids": [],
    },
    {
        "npc_id": "npc_hunter_001",
        "role": "hunter",
        "location_id": "forest_edge",
        "is_critical_npc": False,
        "watched_ids": ["npc_guard_001"],
    },
    {
        "npc_id": "npc_merchant_001",
        "role": "merchant",
        "location_id": "market",
        "is_critical_npc": True,
        "watched_ids": [],
    },
    {
        "npc_id": "npc_villager_001",
        "role": "villager",
        "location_id": "inn",
        "is_critical_npc": False,
        "watched_ids": [],
    },
]


def test_route_event_to_npcs_uses_direct_location_role_and_watch_rules() -> None:
    recipients = route_event_to_npcs(
        {
            "event_id": "evt_001",
            "event_type": "monster_appeared",
            "actor_id": "monster_wolf_001",
            "target_id": "npc_guard_001",
            "location_id": "village_gate",
            "payload": {},
            "importance": 60,
            "created_at_tick": 100,
        },
        NPC_PROFILES,
    )

    assert recipients == ["npc_guard_001", "npc_hunter_001", "npc_merchant_001", "npc_villager_001"]


def test_route_event_to_npcs_sends_high_importance_to_critical_npcs() -> None:
    recipients = route_event_to_npcs(
        {
            "event_id": "evt_002",
            "event_type": "unknown_omen",
            "actor_id": None,
            "target_id": None,
            "location_id": "forest_edge",
            "payload": {},
            "importance": 85,
            "created_at_tick": 100,
        },
        NPC_PROFILES,
    )

    assert recipients == ["npc_guard_001", "npc_hunter_001", "npc_merchant_001"]
