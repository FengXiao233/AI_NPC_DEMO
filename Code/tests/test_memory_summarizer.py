from app.memory_summarizer import summarize_events_for_npc
from app.models import MemorySummary


def test_summarize_events_keeps_relevant_ranked_memories() -> None:
    memories = summarize_events_for_npc(
        "npc_merchant_001",
        [
            {
                "event_id": "evt_001",
                "event_type": "food_shortage",
                "actor_id": None,
                "target_id": None,
                "location_id": "market",
                "payload": {"related_ids": ["npc_merchant_001"]},
                "importance": 45,
                "created_at_tick": 120,
            },
            {
                "event_id": "evt_002",
                "event_type": "player_helped",
                "actor_id": "player_001",
                "target_id": "npc_merchant_001",
                "location_id": "market",
                "payload": {},
                "importance": 60,
                "created_at_tick": 125,
            },
            {
                "event_id": "evt_003",
                "event_type": "routine_patrol",
                "actor_id": "npc_guard_001",
                "target_id": None,
                "location_id": "village_gate",
                "payload": {},
                "importance": 20,
                "created_at_tick": 130,
            },
        ],
    )

    assert [memory.memory_id for memory in memories] == [
        "mem_npc_merchant_001_evt_002",
        "mem_npc_merchant_001_evt_001",
    ]
    assert all(isinstance(memory, MemorySummary) for memory in memories)
    assert memories[0].summary == "The player helped npc_merchant_001."
    assert memories[0].importance == 100
    assert memories[0].expires_at_tick == 3725


def test_summarize_events_respects_max_items_and_recency_tiebreak() -> None:
    memories = summarize_events_for_npc(
        "npc_guard_001",
        [
            {
                "event_id": "evt_old",
                "event_type": "warning_received",
                "actor_id": "npc_hunter_001",
                "target_id": "npc_guard_001",
                "location_id": "village_gate",
                "payload": {},
                "importance": 40,
                "created_at_tick": 20,
            },
            {
                "event_id": "evt_new",
                "event_type": "warning_received",
                "actor_id": "npc_hunter_001",
                "target_id": "npc_guard_001",
                "location_id": "village_gate",
                "payload": {},
                "importance": 40,
                "created_at_tick": 30,
            },
        ],
        max_items=1,
    )

    assert [memory.memory_id for memory in memories] == ["mem_npc_guard_001_evt_new"]


def test_player_stole_uses_catalog_memory_rules() -> None:
    memories = summarize_events_for_npc(
        "npc_merchant_001",
        [
            {
                "event_id": "evt_steal_001",
                "event_type": "player_stole",
                "actor_id": "player_001",
                "target_id": "npc_merchant_001",
                "location_id": "market",
                "payload": {},
                "importance": 60,
                "created_at_tick": 200,
            },
        ],
    )

    assert memories[0].summary == "The player stole from npc_merchant_001."
    assert memories[0].importance == 100
    assert memories[0].expires_at_tick == 3600


def test_event_importance_changes_memory_retention() -> None:
    low_importance = summarize_events_for_npc(
        "npc_merchant_001",
        [
            {
                "event_id": "evt_low_food_memory",
                "event_type": "food_shortage",
                "actor_id": None,
                "target_id": None,
                "location_id": "market",
                "payload": {"related_ids": ["npc_merchant_001"]},
                "importance": 30,
                "created_at_tick": 300,
            },
        ],
        minimum_importance=0,
    )[0]
    high_importance = summarize_events_for_npc(
        "npc_merchant_001",
        [
            {
                "event_id": "evt_high_food_memory",
                "event_type": "food_shortage",
                "actor_id": None,
                "target_id": None,
                "location_id": "market",
                "payload": {"related_ids": ["npc_merchant_001"]},
                "importance": 80,
                "created_at_tick": 300,
            },
        ],
        minimum_importance=0,
    )[0]

    assert high_importance.importance > low_importance.importance
    assert high_importance.expires_at_tick - high_importance.created_at_tick > (
        low_importance.expires_at_tick - low_importance.created_at_tick
    )
