from dataclasses import dataclass, field
from typing import Any

from app.models import EventCatalogEntry, EventCatalogResponse


@dataclass(frozen=True)
class RoleEventResponse:
    task_type: str
    target: str | None = None
    location: str | None = "{event.location_id}"
    priority: int = 50
    interruptible: bool = True
    source: str = "event"
    status: str = "queued"


@dataclass(frozen=True)
class EventDefinition:
    event_type: str
    category: str = "misc"
    template_key: str = "generic"
    routing_roles: set[str] = field(default_factory=set)
    memory_bonus: int = 0
    memory_lifetime: int = 300
    significant: bool = False
    summary_template: str = "{event_type} involved {target} near {location}."
    relationship_delta: dict[str, int] | None = None
    payload_fields: tuple[str, ...] = ()
    default_role_responses: dict[str, tuple[RoleEventResponse, ...]] = field(default_factory=dict)


EVENT_CATALOG = {
    "monster_appeared": EventDefinition(
        event_type="monster_appeared",
        category="monster_incursion",
        template_key="monster_presence",
        routing_roles={"guard", "hunter", "merchant", "villager", "farmer", "blacksmith", "physician", "village_chief"},
        memory_bonus=25,
        memory_lifetime=1800,
        significant=True,
        summary_template="{monster_label} appeared near {location}.",
        payload_fields=("monster_kind", "monster_id", "count", "severity", "entry_point"),
        default_role_responses={
            "guard": (RoleEventResponse("patrol", location="{event.location_id}", priority=86),),
            "hunter": (RoleEventResponse("hunt", target="{event.actor_id}", location="{event.location_id}", priority=84),),
            "merchant": (RoleEventResponse("flee", location="market", priority=72),),
            "villager": (RoleEventResponse("flee", location="village_square", priority=78),),
            "farmer": (RoleEventResponse("flee", location="village_square", priority=74),),
            "blacksmith": (RoleEventResponse("forge", location="village_square", priority=62),),
            "physician": (RoleEventResponse("help", location="village_square", priority=58),),
            "village_chief": (RoleEventResponse("report", target="npc_guard_001", location="village_square", priority=76),),
        },
    ),
    "attack": EventDefinition(
        event_type="attack",
        category="violent_threat",
        template_key="attack",
        routing_roles={"guard", "hunter", "villager", "physician", "village_chief"},
        memory_bonus=30,
        memory_lifetime=2000,
        significant=True,
        summary_template="{actor} attacked {target} near {location}.",
        payload_fields=("weapon", "severity", "injury_level", "witness_ids"),
        default_role_responses={
            "guard": (RoleEventResponse("patrol", location="{event.location_id}", priority=90),),
            "hunter": (RoleEventResponse("hunt", target="{event.actor_id}", location="{event.location_id}", priority=80),),
            "villager": (RoleEventResponse("flee", location="village_square", priority=80),),
            "physician": (RoleEventResponse("heal", target="{event.target_id}", location="{event.location_id}", priority=84),),
            "village_chief": (RoleEventResponse("report", target="npc_guard_001", location="{event.location_id}", priority=72),),
        },
    ),
    "food_shortage": EventDefinition(
        event_type="food_shortage",
        category="resource_pressure",
        template_key="food_shortage",
        routing_roles={"hunter", "merchant", "farmer", "village_chief"},
        memory_bonus=20,
        memory_lifetime=800,
        significant=True,
        summary_template="Food became scarce near {location}.",
        payload_fields=("resource", "amount", "severity", "expected_duration"),
        default_role_responses={
            "merchant": (RoleEventResponse("trade", location="market", priority=78),),
            "hunter": (RoleEventResponse("gather", location="forest_edge", priority=74),),
            "farmer": (RoleEventResponse("plant", location="village_square", priority=82),),
            "village_chief": (RoleEventResponse("report", target="npc_merchant_001", location="village_square", priority=62),),
            "guard": (RoleEventResponse("patrol", location="{event.location_id}", priority=45),),
        },
    ),
    "suspicious_arrival": EventDefinition(
        event_type="suspicious_arrival",
        category="suspicious_activity",
        template_key="suspicious_arrival",
        routing_roles={"guard", "merchant", "village_chief"},
        memory_bonus=15,
        memory_lifetime=900,
        significant=True,
        summary_template="{actor} drew suspicion near {location}.",
        payload_fields=("appearance", "claimed_role", "behavior", "witness_ids", "risk_hint"),
        default_role_responses={
            "guard": (RoleEventResponse("investigate", target="suspicious_arrival", location="{event.location_id}", priority=82),),
            "merchant": (RoleEventResponse("report", target="npc_guard_001", location="village_gate", priority=72),),
            "hunter": (RoleEventResponse("patrol", location="{event.location_id}", priority=48),),
            "village_chief": (RoleEventResponse("report", target="npc_guard_001", location="{event.location_id}", priority=66),),
        },
    ),
    "help_given": EventDefinition(
        event_type="help_given",
        category="social_aid",
        template_key="help_given",
        memory_bonus=15,
        memory_lifetime=1000,
        significant=True,
        summary_template="{actor} helped {target}.",
        relationship_delta={"favor": 5, "trust": 8, "hostility": -2},
        payload_fields=("aid_type", "cost", "witness_ids"),
        default_role_responses={
            "merchant": (RoleEventResponse("talk", target="{event.actor_id}", location="{event.location_id}", priority=42),),
            "guard": (RoleEventResponse("patrol", location="{event.location_id}", priority=35),),
        },
    ),
    "help_refused": EventDefinition(
        event_type="help_refused",
        category="social_aid",
        template_key="help_refused",
        routing_roles={"merchant"},
        memory_bonus=20,
        memory_lifetime=1200,
        significant=True,
        summary_template="{actor} refused to help {target}.",
        relationship_delta={"favor": -4, "trust": -6, "hostility": 3},
        payload_fields=("aid_type", "reason", "witness_ids"),
        default_role_responses={
            "merchant": (RoleEventResponse("talk", target="{event.actor_id}", location="{event.location_id}", priority=55),),
            "guard": (RoleEventResponse("help", target="{event.target_id}", location="{event.location_id}", priority=50),),
        },
    ),
    "trade_completed": EventDefinition(
        event_type="trade_completed",
        category="trade",
        template_key="trade_completed",
        routing_roles={"merchant"},
        memory_bonus=10,
        memory_lifetime=300,
        significant=True,
        summary_template="{actor} completed a trade with {target}.",
        relationship_delta={"favor": 2, "trust": 3, "hostility": 0},
        payload_fields=("goods", "price", "quantity"),
        default_role_responses={
            "merchant": (RoleEventResponse("trade", target="{event.target_id}", location="market", priority=55),),
        },
    ),
    "trade_refused": EventDefinition(
        event_type="trade_refused",
        category="trade",
        template_key="trade_refused",
        routing_roles={"merchant"},
        memory_bonus=15,
        memory_lifetime=600,
        significant=True,
        summary_template="{actor} refused a trade with {target}.",
        relationship_delta={"favor": -2, "trust": -3, "hostility": 1},
        payload_fields=("goods", "reason", "price"),
        default_role_responses={
            "merchant": (RoleEventResponse("talk", target="{event.actor_id}", location="market", priority=58),),
        },
    ),
    "player_helped": EventDefinition(
        event_type="player_helped",
        category="player_reputation",
        template_key="player_helped",
        routing_roles={"merchant"},
        memory_bonus=25,
        memory_lifetime=2400,
        significant=True,
        summary_template="The player helped {target}.",
        relationship_delta={"favor": 6, "trust": 10, "hostility": -3},
        payload_fields=("help_type", "witness_ids"),
        default_role_responses={
            "merchant": (RoleEventResponse("talk", target="player_001", location="{event.location_id}", priority=62),),
            "guard": (RoleEventResponse("patrol", location="{event.location_id}", priority=35),),
        },
    ),
    "player_harmed": EventDefinition(
        event_type="player_harmed",
        category="player_misconduct",
        template_key="player_harmed",
        routing_roles={"guard"},
        memory_bonus=30,
        memory_lifetime=3000,
        significant=True,
        summary_template="The player harmed {target}.",
        relationship_delta={"favor": -10, "trust": -12, "hostility": 15},
        payload_fields=("harm_type", "severity", "witness_ids"),
        default_role_responses={
            "guard": (RoleEventResponse("investigate", target="{event.target_id}", location="{event.location_id}", priority=88),),
            "merchant": (RoleEventResponse("report", target="npc_guard_001", location="village_gate", priority=70),),
            "villager": (RoleEventResponse("flee", location="village_square", priority=70),),
        },
    ),
    "player_stole": EventDefinition(
        event_type="player_stole",
        category="player_misconduct",
        template_key="player_stole",
        routing_roles={"guard", "merchant"},
        memory_bonus=25,
        memory_lifetime=2200,
        significant=True,
        summary_template="The player stole from {target}.",
        relationship_delta={"favor": -8, "trust": -15, "hostility": 10},
        payload_fields=("item", "value", "witness_ids"),
        default_role_responses={
            "guard": (RoleEventResponse("investigate", target="player_001", location="{event.location_id}", priority=84),),
            "merchant": (RoleEventResponse("report", target="npc_guard_001", location="village_gate", priority=74),),
        },
    ),
    "warning_received": EventDefinition(
        event_type="warning_received",
        category="warning",
        template_key="warning_received",
        routing_roles={"guard", "hunter"},
        memory_bonus=10,
        memory_lifetime=600,
        significant=True,
        summary_template="{target} received a warning from {actor}.",
        payload_fields=("topic_hint", "urgency", "witness_ids"),
        default_role_responses={
            "guard": (RoleEventResponse("patrol", location="{event.location_id}", priority=64),),
            "hunter": (RoleEventResponse("hunt", location="{event.location_id}", priority=62),),
            "merchant": (RoleEventResponse("report", target="npc_guard_001", location="village_gate", priority=50),),
        },
    ),
    "traveler_arrived": EventDefinition(
        event_type="traveler_arrived",
        category="visitor_activity",
        template_key="traveler_arrived",
        routing_roles={"merchant", "guard"},
        memory_bonus=12,
        memory_lifetime=700,
        significant=True,
        summary_template="A traveler arrived near {location}.",
        payload_fields=("traveler_id", "origin", "intent"),
        default_role_responses={
            "merchant": (RoleEventResponse("talk", target="{event.actor_id}", location="{event.location_id}", priority=60),),
            "guard": (RoleEventResponse("investigate", target="{event.actor_id}", location="{event.location_id}", priority=52),),
        },
    ),
    "monster_slain": EventDefinition(
        event_type="monster_slain",
        category="combat_resolution",
        template_key="monster_slain",
        routing_roles={"guard", "hunter", "merchant", "farmer", "blacksmith"},
        memory_bonus=16,
        memory_lifetime=1000,
        significant=True,
        summary_template="{actor} slew {target} near {location}.",
        payload_fields=("monster_kind", "loot", "witness_ids"),
        default_role_responses={
            "guard": (RoleEventResponse("patrol", location="{event.location_id}", priority=50),),
            "hunter": (RoleEventResponse("hunt", location="{event.location_id}", priority=44),),
            "merchant": (RoleEventResponse("trade", location="market", priority=48),),
            "farmer": (RoleEventResponse("plant", location="village_square", priority=42),),
            "blacksmith": (RoleEventResponse("forge", location="village_square", priority=42),),
        },
    ),
}


def get_event_definition(event_type: str) -> EventDefinition:
    return EVENT_CATALOG.get(event_type, EventDefinition(event_type=event_type))


def event_category(event_type: str) -> str:
    return get_event_definition(event_type).category


def normalized_event_payload(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    definition = get_event_definition(event_type)
    normalized = dict(payload)
    normalized.setdefault("_category", definition.category)
    normalized.setdefault("_template", definition.template_key)
    normalized.setdefault("_payload_fields", list(definition.payload_fields))
    return normalized


def default_response_tasks_for_role(event: Any, role: str, npc_id: str) -> list[dict[str, Any]]:
    definition = get_event_definition(event.event_type)
    responses = definition.default_role_responses.get(role, ())
    tasks = []
    for index, response in enumerate(responses):
        tasks.append(
            {
                "task_id": f"task_{npc_id}_{event.created_at_tick}_{event.event_id}_{response.task_type}_{index}",
                "task_type": response.task_type,
                "target_id": resolve_response_value(response.target, event),
                "location_id": resolve_response_value(response.location, event),
                "priority": response.priority,
                "interruptible": response.interruptible,
                "source": response.source,
                "status": response.status,
            }
        )
    return tasks


def resolve_response_value(template: str | None, event: Any) -> str | None:
    if template is None:
        return None
    values = {
        "{event.actor_id}": event.actor_id,
        "{event.target_id}": event.target_id,
        "{event.location_id}": event.location_id,
        "{event.event_type}": event.event_type,
    }
    return values.get(template, template)


def role_event_subscriptions() -> dict[str, set[str]]:
    subscriptions: dict[str, set[str]] = {}
    for event_type, definition in EVENT_CATALOG.items():
        for role in definition.routing_roles:
            subscriptions.setdefault(role, set()).add(event_type)
    return subscriptions


def list_event_catalog_entries() -> list[EventCatalogEntry]:
    entries: list[EventCatalogEntry] = []
    for event_type, definition in sorted(EVENT_CATALOG.items()):
        responses: list[EventCatalogResponse] = []
        for role, role_responses in sorted(definition.default_role_responses.items()):
            for response in role_responses:
                responses.append(
                    EventCatalogResponse(
                        role=role,
                        task_type=response.task_type,
                        target=response.target,
                        location=response.location,
                        priority=response.priority,
                        interruptible=response.interruptible,
                        source=response.source,
                        status=response.status,
                    )
                )
        entries.append(
            EventCatalogEntry(
                event_type=event_type,
                category=definition.category,
                template_key=definition.template_key,
                routing_roles=sorted(definition.routing_roles),
                payload_fields=list(definition.payload_fields),
                significant=definition.significant,
                summary_template=definition.summary_template,
                relationship_delta=definition.relationship_delta,
                default_role_responses=responses,
            )
        )
    return entries
