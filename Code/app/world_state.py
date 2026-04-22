import json
import random
import sqlite3
from typing import Any

from app.memory_summarizer import WorldEvent
from app.models import (
    InventoryItem,
    ProductionOrder,
    ResourceRefreshRecord,
    WarehouseItem,
    WarehouseTransaction,
    WorldEntity,
    WorldResourceNode,
)
from app.npc_profile import skill_lookup
from app.state_repository import (
    delete_inventory_item,
    delete_warehouse_item,
    insert_warehouse_transaction,
    list_inventory_records,
    list_production_orders,
    list_warehouse_records,
    load_all_agent_states,
    load_agent_state,
    list_world_entities,
    list_world_resource_nodes,
    mark_production_order_completed,
    upsert_inventory_item,
    upsert_production_order,
    upsert_warehouse_item,
    upsert_world_entity,
    upsert_world_resource_node,
)
from scripts.init_sqlite import dump_json


LOCATION_GRAPH = {
    "market": ("inn", "village_gate", "village_square"),
    "inn": ("market", "village_square"),
    "village_gate": ("market", "forest_edge", "village_square"),
    "forest_edge": ("village_gate",),
    "village_square": ("market", "village_gate", "inn"),
}

INTELLIGENT_MONSTER_THRESHOLD = 70
FOOD_NUTRITION = {
    "rations": 26,
    "meat": 30,
    "berries": 16,
    "grain": 20,
    "meal": 36,
}
WAREHOUSE_SELL_PRICES = {
    "equipment_weapon": 14,
    "equipment_tool": 10,
    "equipment_armor": 18,
    "rations": 4,
    "meat": 5,
    "berries": 2,
    "grain": 3,
    "herbs": 6,
    "hide": 5,
}
FOOD_ITEM_TYPES = set(FOOD_NUTRITION)
WAREHOUSE_RESERVE_QUANTITIES = {
    "rations": 4,
    "grain": 6,
    "meat": 2,
    "berries": 2,
    "herbs": 2,
}
PLANT_GROWTH_TICKS = 4
FORGE_COMPLETION_TICKS = 3

MONSTER_TEMPLATES: dict[str, dict[str, Any]] = {
    "wolf": {
        "display_name": "Wolf",
        "health": 42,
        "threat_level": 58,
        "hostility": 72,
        "aggression": 68,
        "intelligence": 14,
        "awareness": 72,
        "morale": 52,
        "attack_power": 48,
        "defense": 24,
        "behavior": "roaming",
        "loot_table": {"meat": 3, "hide": 1, "trophy": 1},
    },
    "boar": {
        "display_name": "Wild boar",
        "health": 55,
        "threat_level": 48,
        "hostility": 46,
        "aggression": 55,
        "intelligence": 8,
        "awareness": 45,
        "morale": 64,
        "attack_power": 38,
        "defense": 34,
        "behavior": "roaming",
        "loot_table": {"meat": 4, "hide": 1},
    },
    "goblin": {
        "display_name": "Goblin raider",
        "health": 38,
        "threat_level": 64,
        "hostility": 74,
        "aggression": 64,
        "intelligence": 46,
        "awareness": 60,
        "morale": 45,
        "attack_power": 44,
        "defense": 28,
        "behavior": "roaming",
        "loot_table": {"rations": 1, "trophy": 1},
    },
    "goblin_shaman": {
        "display_name": "Goblin shaman",
        "health": 48,
        "threat_level": 76,
        "hostility": 68,
        "aggression": 48,
        "intelligence": 82,
        "awareness": 78,
        "morale": 70,
        "attack_power": 58,
        "defense": 32,
        "behavior": "npc_controlled",
        "loot_table": {"rations": 2, "trophy": 1},
    },
}


def refresh_world_resources(
    connection: sqlite3.Connection,
    current_tick: int,
) -> list[ResourceRefreshRecord]:
    refreshes: list[ResourceRefreshRecord] = []
    for node in list_world_resource_nodes(connection, include_depleted=True):
        if node.available_quantity >= node.max_quantity:
            continue
        if current_tick - node.last_harvested_tick < node.cooldown_ticks:
            continue
        delta = min(node.respawn_rate, node.max_quantity - node.available_quantity)
        if delta <= 0:
            continue
        refreshed = node.model_copy(
            update={
                "available_quantity": node.available_quantity + delta,
                "last_refreshed_tick": current_tick,
            }
        )
        upsert_world_resource_node(connection, refreshed)
        refreshes.append(
            ResourceRefreshRecord(
                node_id=node.node_id,
                resource_type=node.resource_type,
                location_id=node.location_id,
                quantity_delta=delta,
                available_quantity=refreshed.available_quantity,
            )
        )
    return refreshes


def mature_due_production_orders(connection: sqlite3.Connection, current_tick: int) -> list[str]:
    matured_order_ids: list[str] = []
    orders = [
        order
        for order in list_production_orders(connection, include_completed=False, limit=200)
        if order.status == "pending" and order.completes_at_tick <= current_tick
    ]
    for order in orders:
        add_warehouse_quantity(
            connection,
            item_type=order.output_item_type,
            item_name=order.output_item_name,
            quantity_delta=order.output_quantity,
            current_tick=current_tick,
            actor_id=order.actor_id,
            reason=f"{order.order_type}_completed",
        )
        if order.order_type == "plant":
            increase_village_field_yield(connection, order.output_quantity, current_tick)
        mark_production_order_completed(connection, order.order_id)
        matured_order_ids.append(order.order_id)
    return matured_order_ids


def move_roaming_entities(connection: sqlite3.Connection, current_tick: int) -> list[str]:
    moved_entity_ids: list[str] = []
    for entity in list_world_entities(connection):
        if entity.behavior != "roaming" or entity.state not in {"active", "roaming", "fleeing"}:
            continue
        neighbors = LOCATION_GRAPH.get(entity.location_id, ())
        if not neighbors:
            continue
        rng = random.Random(f"{entity.entity_id}:{current_tick}")
        next_location = rng.choice(neighbors)
        if next_location == entity.location_id:
            continue
        moved_entity = entity.model_copy(
            update={
                "location_id": next_location,
                "updated_at_tick": current_tick,
            }
        )
        upsert_world_entity(connection, moved_entity)
        moved_entity_ids.append(entity.entity_id)
    return moved_entity_ids


def advance_entity_behaviors(
    connection: sqlite3.Connection,
    current_tick: int,
) -> list[WorldEvent]:
    events: list[WorldEvent] = []
    npc_states = load_all_agent_states(connection)
    npcs_by_location: dict[str, list[Any]] = {}
    for state in npc_states:
        npcs_by_location.setdefault(state.location_id, []).append(state)

    for entity in list_world_entities(connection):
        if entity.entity_type != "monster" or entity.state == "removed":
            continue
        if entity.intelligence >= INTELLIGENT_MONSTER_THRESHOLD:
            ensure_intelligent_monster_npc(connection, entity)
            continue
        occupants = npcs_by_location.get(entity.location_id, [])
        target_state = select_monster_target(entity, occupants)
        payload = dict(entity.payload)
        last_attack_tick = int(payload.get("last_attack_tick", -999))
        if target_state is None:
            if entity.state != "roaming":
                upsert_world_entity(
                    connection,
                    entity.model_copy(
                        update={
                            "state": "roaming",
                            "updated_at_tick": current_tick,
                            "target_id": None,
                            "payload": clear_monster_target(payload),
                        }
                    ),
                )
            continue
        if entity.aggression < 35 and entity.hostility < 50:
            continue
        payload["target_npc_id"] = target_state.npc_id
        payload["last_seen_tick"] = current_tick
        attack_interval = max(1, 5 - int(entity.aggression / 25))
        if entity.state in {"stalking", "attacking"} and last_attack_tick <= current_tick - attack_interval:
            payload["last_attack_tick"] = current_tick
            updated_entity = entity.model_copy(
                update={
                    "state": "attacking",
                    "updated_at_tick": current_tick,
                    "target_id": target_state.npc_id,
                    "payload": payload,
                }
            )
            upsert_world_entity(connection, updated_entity)
            events.append(
                WorldEvent(
                    event_id=f"evt_{entity.entity_id}_attack_{current_tick}",
                    event_type="attack",
                    actor_id=entity.entity_id,
                    target_id=target_state.npc_id,
                    location_id=entity.location_id,
                    payload={
                        "weapon": entity.payload.get("monster_kind", "claws"),
                        "severity": "high" if entity.threat_level >= 60 else "medium",
                        "injury_level": "serious" if entity.threat_level >= 75 else "minor",
                        "damage": max(1, int(entity.attack_power * 0.35)),
                        "witness_ids": [state.npc_id for state in occupants if state.npc_id != target_state.npc_id],
                    },
                    importance=min(95, max(58, entity.threat_level + 10)),
                    created_at_tick=current_tick,
                )
            )
            continue
        if entity.state != "stalking":
            upsert_world_entity(
                connection,
                entity.model_copy(
                    update={
                        "state": "stalking",
                        "updated_at_tick": current_tick,
                        "target_id": target_state.npc_id,
                        "payload": payload,
                    }
                ),
            )
    return events


def generate_random_world_events(
    connection: sqlite3.Connection,
    current_tick: int,
) -> list[WorldEvent]:
    del connection
    events: list[WorldEvent] = []
    rng = random.Random(current_tick * 97 + 13)
    if current_tick % 15 == 0:
        monster_kind = rng.choice(["wolf", "boar", "goblin", "goblin_shaman"])
        location_id = rng.choice(["village_gate", "forest_edge"])
        count = 1 if location_id == "village_gate" else 2
        entity_id = f"monster_{monster_kind}_{current_tick}"
        events.append(
            WorldEvent(
                event_id=f"evt_random_monster_{current_tick}",
                event_type="monster_appeared",
                actor_id=entity_id,
                target_id=None,
                location_id=location_id,
                payload={
                    "monster_kind": monster_kind,
                    "monster_id": entity_id,
                    "count": count,
                    "severity": "high" if location_id == "village_gate" else "medium",
                },
                importance=70 if location_id == "village_gate" else 58,
                created_at_tick=current_tick,
            )
        )
    if current_tick % 12 == 0:
        traveler_id = f"traveler_{current_tick}"
        events.append(
            WorldEvent(
                event_id=f"evt_random_traveler_{current_tick}",
                event_type="traveler_arrived",
                actor_id=traveler_id,
                target_id=None,
                location_id="market",
                payload={
                    "traveler_id": traveler_id,
                    "origin": rng.choice(["hill_road", "river_path", "north_trail"]),
                    "intent": rng.choice(["trade", "rest", "ask_directions"]),
                },
                importance=42,
                created_at_tick=current_tick,
            )
        )
    return events


def populate_event_world_effects(
    connection: sqlite3.Connection,
    event: WorldEvent,
) -> list[str]:
    spawned_entity_ids: list[str] = []
    if event.event_type == "monster_appeared":
        entity = build_monster_entity_from_event(event)
        upsert_world_entity(connection, entity)
        if entity.intelligence >= INTELLIGENT_MONSTER_THRESHOLD:
            ensure_intelligent_monster_npc(connection, entity)
        spawned_entity_ids.append(entity.entity_id)
    elif event.event_type == "traveler_arrived":
        entity_id = event.payload.get("traveler_id") or event.actor_id or f"traveler_{event.event_id}"
        entity = WorldEntity(
            entity_id=entity_id,
            entity_type="traveler",
            display_name="Traveling stranger",
            location_id=event.location_id or "market",
            state="visiting",
            quantity=1,
            threat_level=10,
            behavior="static",
            payload=event.payload,
            created_at_tick=event.created_at_tick,
            updated_at_tick=event.created_at_tick,
        )
        upsert_world_entity(connection, entity)
        spawned_entity_ids.append(entity.entity_id)
    elif event.event_type == "monster_slain" and event.target_id:
        for entity in list_world_entities(connection, include_inactive=True):
            if entity.entity_id != event.target_id:
                continue
            removed = entity.model_copy(
                update={
                    "state": "removed",
                    "quantity": 0,
                    "updated_at_tick": event.created_at_tick,
                }
            )
            upsert_world_entity(connection, removed)
            break
    return spawned_entity_ids


def materialize_task_world_effects(
    connection: sqlite3.Connection,
    npc_id: str,
    task_type: str,
    location_id: str,
    current_tick: int,
    target_id: str | None = None,
) -> dict[str, Any]:
    if task_type == "gather":
        return materialize_gather_effect(connection, npc_id, location_id, current_tick)
    if task_type == "hunt":
        return materialize_hunt_effect(connection, npc_id, location_id, current_tick, target_id=target_id)
    if task_type == "trade":
        return materialize_trade_effect(connection, npc_id, current_tick)
    if task_type == "plant":
        return materialize_plant_effect(connection, npc_id, location_id, current_tick)
    if task_type == "forge":
        return materialize_forge_effect(connection, npc_id, current_tick)
    if task_type == "eat":
        return materialize_eat_effect(connection, npc_id, current_tick)
    if task_type == "heal":
        return materialize_heal_effect(connection, npc_id, current_tick, target_id=target_id)
    if task_type == "help":
        return materialize_help_effect(connection, npc_id, current_tick, target_id=target_id)
    if task_type == "patrol":
        return materialize_patrol_effect(connection, npc_id, current_tick)
    return {}


def materialize_gather_effect(
    connection: sqlite3.Connection,
    npc_id: str,
    location_id: str,
    current_tick: int,
) -> dict[str, Any]:
    candidates = list_world_resource_nodes(connection, location_id=location_id, include_depleted=False)
    if not candidates:
        return {}
    node = max(candidates, key=lambda item: (item.available_quantity, item.max_quantity))
    yield_quantity = int(node.metadata.get("yield_quantity", 1))
    harvest_amount = max(1, min(yield_quantity, node.available_quantity))
    updated_node = node.model_copy(
        update={
            "available_quantity": node.available_quantity - harvest_amount,
            "last_harvested_tick": current_tick,
        }
    )
    upsert_world_resource_node(connection, updated_node)
    item_type = str(node.metadata.get("item_type") or node.resource_type)
    gatherer_state = load_agent_state(connection, npc_id)
    if should_deposit_gathered_item(gatherer_state, item_type):
        add_warehouse_quantity(
            connection,
            item_type=item_type,
            item_name=node.display_name,
            quantity_delta=harvest_amount,
            current_tick=current_tick,
            actor_id=npc_id,
            reason="gather_deposit",
        )
        destination = "warehouse"
    else:
        add_inventory_quantity(
            connection,
            npc_id,
            item_type=item_type,
            item_name=node.display_name,
            quantity_delta=harvest_amount,
            current_tick=current_tick,
            source_location_id=location_id,
        )
        destination = "inventory"
    return {
        "resource_node_id": node.node_id,
        "resource_type": node.resource_type,
        "harvested_quantity": harvest_amount,
        "item_type": item_type,
        "destination": destination,
    }


def materialize_hunt_effect(
    connection: sqlite3.Connection,
    npc_id: str,
    location_id: str,
    current_tick: int,
    target_id: str | None = None,
) -> dict[str, Any]:
    candidates = [
        entity
        for entity in list_world_entities(connection, location_id=location_id)
        if entity.entity_type in {"monster", "wildlife"}
        and entity.state in {"active", "roaming", "stalking", "attacking"}
        and entity.quantity > 0
    ]
    if not candidates:
        return {}
    targeted = [entity for entity in candidates if entity.entity_id == target_id]
    entity = targeted[0] if targeted else max(candidates, key=lambda item: (item.threat_level, item.quantity))
    hunter_state = load_agent_state(connection, npc_id)
    if hunter_state is None:
        return {}
    skill_check = hunt_skill_check(hunter_state, entity)
    if not skill_check["success"]:
        fatigued = entity.model_copy(
            update={
                "state": "stalking" if entity.entity_type == "monster" else entity.state,
                "target_id": npc_id if entity.entity_type == "monster" else entity.target_id,
                "updated_at_tick": current_tick,
                "payload": {**entity.payload, "last_hunt_attempt_tick": current_tick, "last_hunter_id": npc_id},
            }
        )
        upsert_world_entity(connection, fatigued)
        return {
            "entity_id": entity.entity_id,
            "entity_type": entity.entity_type,
            "success": False,
            "defeated": False,
            "skill_check": skill_check,
            "loot": {},
        }
    next_quantity = max(0, entity.quantity - 1)
    next_state = "removed" if next_quantity == 0 else entity.state
    unit_health = max(1, int(entity.max_health / max(1, entity.quantity)))
    updated_entity = entity.model_copy(
        update={
            "quantity": next_quantity,
            "state": next_state,
            "health": unit_health * next_quantity,
            "updated_at_tick": current_tick,
        }
    )
    upsert_world_entity(connection, updated_entity)
    loot = loot_for_entity(entity, skill_check)
    for item_type, quantity in loot.items():
        add_inventory_quantity(
            connection,
            npc_id,
            item_type=item_type,
            item_name=loot_item_name(entity, item_type),
            quantity_delta=quantity,
            current_tick=current_tick,
            source_location_id=location_id,
        )
    return {
        "entity_id": entity.entity_id,
        "entity_type": entity.entity_type,
        "success": True,
        "defeated": next_quantity == 0,
        "skill_check": skill_check,
        "loot": loot,
    }


def materialize_trade_effect(
    connection: sqlite3.Connection,
    npc_id: str,
    current_tick: int,
) -> dict[str, Any]:
    warehouse_stock = select_warehouse_trade_stock(connection)
    if warehouse_stock is not None:
        price = WAREHOUSE_SELL_PRICES.get(warehouse_stock.item_type, 3)
        add_warehouse_quantity(
            connection,
            item_type=warehouse_stock.item_type,
            item_name=warehouse_stock.item_name,
            quantity_delta=-1,
            current_tick=current_tick,
            actor_id=npc_id,
            reason="trade_sale",
        )
        add_warehouse_quantity(
            connection,
            item_type="coin",
            item_name="Village coin reserve",
            quantity_delta=price,
            current_tick=current_tick,
            actor_id=npc_id,
            reason="trade_income",
        )
        add_inventory_quantity(
            connection,
            npc_id,
            item_type="coin",
            item_name="Merchant commission",
            quantity_delta=1,
            current_tick=current_tick,
            source_location_id=None,
        )
        return {
            "sold_item_type": warehouse_stock.item_type,
            "sold_item_name": warehouse_stock.item_name,
            "source": "warehouse",
            "price": price,
            "warehouse_coin_delta": price,
            "merchant_coin_delta": 1,
        }

    inventory = list_inventory_records(connection, npc_id)
    tradeable = next((item for item in inventory if item.item_type not in {"coin", "trophy"} and item.quantity > 0), None)
    if tradeable is None:
        return {}
    add_inventory_quantity(
        connection,
        npc_id,
        item_type=tradeable.item_type,
        item_name=tradeable.item_name,
        quantity_delta=-1,
        current_tick=current_tick,
        source_location_id=tradeable.source_location_id,
    )
    add_inventory_quantity(
        connection,
        npc_id,
        item_type="coin",
        item_name="Coin pouch",
        quantity_delta=2,
        current_tick=current_tick,
        source_location_id=None,
    )
    return {
        "sold_item_type": tradeable.item_type,
        "sold_item_name": tradeable.item_name,
        "source": "inventory",
        "coin_delta": 2,
    }


def materialize_plant_effect(
    connection: sqlite3.Connection,
    npc_id: str,
    location_id: str,
    current_tick: int,
) -> dict[str, Any]:
    seed_item = next((item for item in list_warehouse_records(connection) if item.item_type == "grain_seed"), None)
    if seed_item is None:
        return {
            "success": False,
            "reason": "no_seed",
            "warehouse": "village_warehouse",
        }
    add_warehouse_quantity(
        connection,
        item_type="grain_seed",
        item_name=seed_item.item_name,
        quantity_delta=-1,
        current_tick=current_tick,
        actor_id=npc_id,
        reason="plant_started",
    )
    order_id = create_production_order(
        connection,
        actor_id=npc_id,
        order_type="plant",
        input_item_type="grain_seed",
        input_quantity=1,
        output_item_type="grain",
        output_item_name="Stored grain",
        output_quantity=3,
        started_at_tick=current_tick,
        completes_at_tick=current_tick + PLANT_GROWTH_TICKS,
        payload={"location_id": location_id},
    )
    field_node = ensure_village_field_node(connection, current_tick)
    return {
        "success": True,
        "status": "in_progress",
        "actor_id": npc_id,
        "warehouse": "village_warehouse",
        "production_order_id": order_id,
        "consumed_item_type": "grain_seed",
        "consumed_quantity": 1,
        "produced_item_type": "grain",
        "produced_quantity": 3,
        "completes_at_tick": current_tick + PLANT_GROWTH_TICKS,
        "field_node_id": field_node.node_id,
        "field_quantity": field_node.available_quantity,
        "location_id": location_id,
    }


def materialize_forge_effect(
    connection: sqlite3.Connection,
    npc_id: str,
    current_tick: int,
) -> dict[str, Any]:
    smith_state = load_agent_state(connection, npc_id)
    if smith_state is None:
        return {}
    ore = next((item for item in list_warehouse_records(connection) if item.item_type == "ore"), None)
    if ore is None or ore.quantity < 2:
        return {
            "success": False,
            "reason": "not_enough_ore",
            "warehouse": "village_warehouse",
        }
    add_warehouse_quantity(
        connection,
        item_type="ore",
        item_name=ore.item_name,
        quantity_delta=-2,
        current_tick=current_tick,
        actor_id=npc_id,
        reason="forge_started",
    )
    skill_check = forge_skill_check(smith_state)
    if not skill_check["success"]:
        add_warehouse_quantity(
            connection,
            item_type="scrap_metal",
            item_name="Scrap metal",
            quantity_delta=1,
            current_tick=current_tick,
            actor_id=npc_id,
            reason="forge_failed",
        )
        return {
            "success": False,
            "reason": "failed_skill_check",
            "warehouse": "village_warehouse",
            "consumed_item_type": "ore",
            "consumed_quantity": 2,
            "produced_item_type": "scrap_metal",
            "produced_quantity": 1,
            "skill_check": skill_check,
        }
    equipment_type = "equipment_weapon" if smith_state.base_attributes.strength >= 5 else "equipment_tool"
    equipment_name = "Iron spear" if equipment_type == "equipment_weapon" else "Iron tool set"
    order_id = create_production_order(
        connection,
        actor_id=npc_id,
        order_type="forge",
        input_item_type="ore",
        input_quantity=2,
        output_item_type=equipment_type,
        output_item_name=equipment_name,
        output_quantity=1,
        started_at_tick=current_tick,
        completes_at_tick=current_tick + FORGE_COMPLETION_TICKS,
        payload={"skill_check": skill_check},
    )
    return {
        "success": True,
        "status": "in_progress",
        "warehouse": "village_warehouse",
        "production_order_id": order_id,
        "consumed_item_type": "ore",
        "consumed_quantity": 2,
        "produced_item_type": equipment_type,
        "produced_item_name": equipment_name,
        "produced_quantity": 1,
        "completes_at_tick": current_tick + FORGE_COMPLETION_TICKS,
        "skill_check": skill_check,
    }


def materialize_eat_effect(
    connection: sqlite3.Connection,
    npc_id: str,
    current_tick: int,
) -> dict[str, Any]:
    consumed = consume_food(connection, npc_id, current_tick)
    if consumed is None:
        return {
            "success": False,
            "reason": "no_food",
            "needs_delta": {},
        }
    return {
        "success": True,
        "consumed_item_type": consumed["item_type"],
        "consumed_item_name": consumed["item_name"],
        "source": consumed["source"],
        "nutrition": consumed["nutrition"],
        "needs_delta": {
            "hunger": -consumed["nutrition"],
            "health": 3,
        },
    }


def materialize_heal_effect(
    connection: sqlite3.Connection,
    npc_id: str,
    current_tick: int,
    target_id: str | None = None,
) -> dict[str, Any]:
    healer_state = load_agent_state(connection, npc_id)
    target_npc_id = target_id if target_id and target_id.startswith("npc_") else npc_id
    if target_npc_id == npc_id and healer_state is not None and profession_value(healer_state) == "physician":
        patient = select_most_injured_patient(connection, exclude_npc_id=npc_id)
        if patient is not None:
            target_npc_id = patient.npc_id
    herbs = next((item for item in list_inventory_records(connection, npc_id) if item.item_type == "herbs"), None)
    source = "inventory"
    if herbs is None:
        herbs = next((item for item in list_warehouse_records(connection) if item.item_type == "herbs"), None)
        source = "warehouse"
    if herbs is None:
        return {
            "success": False,
            "reason": "no_herbs",
            "target_npc_id": target_npc_id,
            "needs_delta": {},
        }
    if source == "inventory":
        add_inventory_quantity(
            connection,
            npc_id,
            item_type="herbs",
            item_name=herbs.item_name,
            quantity_delta=-1,
            current_tick=current_tick,
            source_location_id=getattr(herbs, "source_location_id", None),
        )
    else:
        add_warehouse_quantity(
            connection,
            item_type="herbs",
            item_name=herbs.item_name,
            quantity_delta=-1,
            current_tick=current_tick,
            actor_id=npc_id,
            reason="heal_used",
        )
    return {
        "success": True,
        "target_npc_id": target_npc_id,
        "consumed_item_type": "herbs",
        "source": source,
        "needs_delta": {"health": 22} if target_npc_id == npc_id else {},
        "target_needs_delta": {"health": 22} if target_npc_id != npc_id else {},
    }


def materialize_help_effect(
    connection: sqlite3.Connection,
    npc_id: str,
    current_tick: int,
    target_id: str | None = None,
) -> dict[str, Any]:
    helper_state = load_agent_state(connection, npc_id)
    if helper_state is None:
        return {}
    if profession_value(helper_state) == "physician":
        return materialize_heal_effect(connection, npc_id, current_tick, target_id=target_id)
    return {
        "success": True,
        "helper_npc_id": npc_id,
        "reason": "social_support",
        "needs_delta": {"social": -3},
    }


def materialize_patrol_effect(
    connection: sqlite3.Connection,
    npc_id: str,
    current_tick: int,
) -> dict[str, Any]:
    state = load_agent_state(connection, npc_id)
    if state is None or profession_value(state) != "village_chief":
        return {}
    assignments = coordinate_village_work(connection, current_tick)
    if not assignments:
        return {}
    return {
        "success": True,
        "coordinator_npc_id": npc_id,
        "reason": "warehouse_coordination",
        "assignments": assignments,
    }


def coordinate_village_work(connection: sqlite3.Connection, current_tick: int) -> list[dict[str, Any]]:
    warehouse = list_warehouse_records(connection)
    food_quantity = sum(item.quantity for item in warehouse if item.item_type in FOOD_ITEM_TYPES)
    equipment_quantity = sum(item.quantity for item in warehouse if item.item_type.startswith("equipment_"))
    herb_quantity = sum(item.quantity for item in warehouse if item.item_type == "herbs")
    ore_quantity = sum(item.quantity for item in warehouse if item.item_type == "ore")
    assignments: list[dict[str, Any]] = []
    if food_quantity < 14:
        assignments.extend(
            [
                enqueue_work_task(connection, "npc_farmer_001", "plant", "village_square", 72, current_tick, "food_stock_low"),
                enqueue_work_task(connection, "npc_hunter_001", "gather", "forest_edge", 58, current_tick, "food_stock_low"),
                enqueue_work_task(connection, "npc_merchant_001", "trade", "market", 54, current_tick, "food_stock_low"),
            ]
        )
    if equipment_quantity < 2 and ore_quantity >= 2:
        assignments.append(
            enqueue_work_task(connection, "npc_blacksmith_001", "forge", "village_square", 66, current_tick, "equipment_stock_low")
        )
    if herb_quantity < 2:
        assignments.append(
            enqueue_work_task(connection, "npc_hunter_001", "gather", "forest_edge", 56, current_tick, "herb_stock_low")
        )
    return [assignment for assignment in assignments if assignment]


def enqueue_work_task(
    connection: sqlite3.Connection,
    npc_id: str,
    task_type: str,
    location_id: str,
    priority: int,
    current_tick: int,
    reason: str,
) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT current_task_json, task_queue_json
        FROM npc_state
        WHERE npc_id = ?
        """,
        (npc_id,),
    ).fetchone()
    if row is None:
        return {}
    current_task = json.loads(row[0])
    if current_task.get("task_type") == task_type and current_task.get("location_id") == location_id:
        return {}
    task_queue = json.loads(row[1])
    if any(task.get("task_type") == task_type and task.get("location_id") == location_id for task in task_queue):
        return {}
    task = {
        "task_id": f"task_{npc_id}_{current_tick}_{reason}_{task_type}",
        "task_type": task_type,
        "target_id": None,
        "location_id": location_id,
        "priority": priority,
        "interruptible": True,
        "source": "routine",
        "status": "queued",
    }
    task_queue.append(task)
    connection.execute(
        """
        UPDATE npc_state
        SET task_queue_json = ?
        WHERE npc_id = ?
        """,
        (dump_json(task_queue), npc_id),
    )
    return {"npc_id": npc_id, "task_type": task_type, "location_id": location_id, "reason": reason}


def select_most_injured_patient(connection: sqlite3.Connection, exclude_npc_id: str | None = None) -> Any:
    candidates = [
        state
        for state in load_all_agent_states(connection)
        if state.npc_id != exclude_npc_id and state.needs.health <= 75
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda state: (state.needs.health, state.needs.safety))


def profession_value(agent_state: Any) -> str:
    profession = getattr(agent_state, "profession", "villager")
    if profession != "villager":
        return str(profession).split(":", 1)[0]
    role = getattr(agent_state, "role", "")
    return getattr(role, "value", str(role))


def hunt_skill_check(hunter_state: Any, entity: WorldEntity) -> dict[str, Any]:
    combat_skill = skill_lookup(hunter_state.skills, "combat")
    hunting_skill = skill_lookup(hunter_state.skills, "hunting")
    weapon_skill = skill_lookup(hunter_state.skills, "weapon_use")
    score = (
        hunter_state.base_attributes.strength * 7
        + hunter_state.base_attributes.endurance * 5
        + hunter_state.base_attributes.technique * 6
        + hunter_state.base_attributes.perception * 5
        + combat_skill * 0.35
        + hunting_skill * 0.45
        + weapon_skill * 0.20
        + hunter_state.learning_bias.combat_confidence_delta
    )
    difficulty = entity.threat_level + int(entity.defense * 0.45) + max(0, entity.quantity - 1) * 8
    if hunter_state.base_attributes.strength < 4 and entity.max_health >= 35:
        difficulty += 25
    margin = int(score - difficulty)
    return {
        "score": int(score),
        "difficulty": int(difficulty),
        "margin": margin,
        "success": margin >= 0,
        "combat_skill": combat_skill,
        "hunting_skill": hunting_skill,
        "weapon_skill": weapon_skill,
    }


def loot_for_entity(entity: WorldEntity, skill_check: dict[str, Any]) -> dict[str, int]:
    loot_table = entity.payload.get("loot_table")
    if not isinstance(loot_table, dict) or not loot_table:
        loot_table = {"meat": 2, "trophy": 1} if entity.entity_type == "monster" else {"meat": 2}
    yield_multiplier = 1.0 + max(0, int(skill_check["margin"])) / 100.0
    loot: dict[str, int] = {}
    for item_type, raw_quantity in loot_table.items():
        try:
            quantity = int(raw_quantity)
        except (TypeError, ValueError):
            continue
        if quantity <= 0:
            continue
        loot[str(item_type)] = max(1, int(quantity * yield_multiplier))
    return loot


def loot_item_name(entity: WorldEntity, item_type: str) -> str:
    names = {
        "meat": f"{entity.display_name} meat",
        "hide": f"{entity.display_name} hide",
        "rations": f"{entity.display_name} rations",
        "trophy": f"{entity.display_name} trophy",
    }
    return names.get(item_type, f"{entity.display_name} {item_type}")


def should_deposit_gathered_item(agent_state: Any, item_type: str) -> bool:
    if agent_state is None:
        return False
    profession = getattr(agent_state, "profession", "")
    profession_base = str(profession).split(":", 1)[0]
    return profession_base == "farmer" or item_type == "grain"


def select_warehouse_trade_stock(connection: sqlite3.Connection) -> WarehouseItem | None:
    stock = [
        item
        for item in list_warehouse_records(connection)
        if item.item_type in WAREHOUSE_SELL_PRICES
        and item.quantity > WAREHOUSE_RESERVE_QUANTITIES.get(item.item_type, 0)
    ]
    if not stock:
        return None
    return max(stock, key=lambda item: (WAREHOUSE_SELL_PRICES.get(item.item_type, 0), item.quantity))


def consume_food(connection: sqlite3.Connection, npc_id: str, current_tick: int) -> dict[str, Any] | None:
    for item in list_inventory_records(connection, npc_id):
        nutrition = FOOD_NUTRITION.get(item.item_type)
        if nutrition is None or item.quantity <= 0:
            continue
        add_inventory_quantity(
            connection,
            npc_id,
            item_type=item.item_type,
            item_name=item.item_name,
            quantity_delta=-1,
            current_tick=current_tick,
            source_location_id=item.source_location_id,
        )
        return {
            "item_type": item.item_type,
            "item_name": item.item_name,
            "source": "inventory",
            "nutrition": nutrition,
        }
    for item in list_warehouse_records(connection):
        nutrition = FOOD_NUTRITION.get(item.item_type)
        if nutrition is None or item.quantity <= 0:
            continue
        add_warehouse_quantity(
            connection,
            item_type=item.item_type,
            item_name=item.item_name,
            quantity_delta=-1,
            current_tick=current_tick,
            actor_id=npc_id,
            reason="food_consumed",
        )
        return {
            "item_type": item.item_type,
            "item_name": item.item_name,
            "source": "warehouse",
            "nutrition": nutrition,
        }
    return None


def ensure_village_field_node(connection: sqlite3.Connection, current_tick: int) -> WorldResourceNode:
    existing = next(
        (node for node in list_world_resource_nodes(connection, location_id="village_square", include_depleted=True) if node.node_id == "res_village_fields"),
        None,
    )
    if existing is not None:
        return existing
    node = WorldResourceNode(
        node_id="res_village_fields",
        location_id="village_square",
        resource_type="grain_field",
        display_name="Village grain fields",
        available_quantity=0,
        max_quantity=12,
        respawn_rate=1,
        cooldown_ticks=6,
        last_harvested_tick=current_tick,
        last_refreshed_tick=current_tick,
        metadata={"item_type": "grain", "yield_quantity": 2},
    )
    upsert_world_resource_node(connection, node)
    return node


def forge_skill_check(smith_state: Any) -> dict[str, Any]:
    forging_skill = skill_lookup(smith_state.skills, "forging")
    crafting_skill = skill_lookup(smith_state.skills, "crafting")
    repair_skill = skill_lookup(smith_state.skills, "repair")
    score = (
        smith_state.base_attributes.strength * 5
        + smith_state.base_attributes.endurance * 4
        + smith_state.base_attributes.technique * 8
        + smith_state.base_attributes.logic * 4
        + forging_skill * 0.45
        + crafting_skill * 0.30
        + repair_skill * 0.15
    )
    difficulty = 88
    margin = int(score - difficulty)
    return {
        "score": int(score),
        "difficulty": difficulty,
        "margin": margin,
        "success": margin >= 0,
        "forging_skill": forging_skill,
        "crafting_skill": crafting_skill,
        "repair_skill": repair_skill,
    }


def create_production_order(
    connection: sqlite3.Connection,
    actor_id: str,
    order_type: str,
    input_item_type: str | None,
    input_quantity: int,
    output_item_type: str,
    output_item_name: str,
    output_quantity: int,
    started_at_tick: int,
    completes_at_tick: int,
    payload: dict[str, Any] | None = None,
) -> str:
    existing_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM village_production_orders
        WHERE started_at_tick = ?
        """,
        (started_at_tick,),
    ).fetchone()[0]
    order_id = "prod_%s_%s_%s_%03d" % (
        started_at_tick,
        sanitize_identifier(actor_id),
        sanitize_identifier(order_type),
        existing_count + 1,
    )
    upsert_production_order(
        connection,
        ProductionOrder(
            order_id=order_id,
            actor_id=actor_id,
            order_type=order_type,
            status="pending",
            input_item_type=input_item_type,
            input_quantity=input_quantity,
            output_item_type=output_item_type,
            output_item_name=output_item_name,
            output_quantity=output_quantity,
            started_at_tick=started_at_tick,
            completes_at_tick=completes_at_tick,
            payload=payload or {},
        ),
    )
    return order_id


def increase_village_field_yield(connection: sqlite3.Connection, quantity: int, current_tick: int) -> None:
    field_node = ensure_village_field_node(connection, current_tick)
    upsert_world_resource_node(
        connection,
        field_node.model_copy(
            update={
                "available_quantity": min(field_node.max_quantity, field_node.available_quantity + quantity),
                "last_refreshed_tick": current_tick,
            }
        ),
    )


def add_inventory_quantity(
    connection: sqlite3.Connection,
    npc_id: str,
    item_type: str,
    item_name: str,
    quantity_delta: int,
    current_tick: int,
    source_location_id: str | None,
) -> None:
    existing = next((item for item in list_inventory_records(connection, npc_id) if item.item_type == item_type), None)
    if existing is None:
        if quantity_delta <= 0:
            return
        upsert_inventory_item(
            connection,
            npc_id,
            InventoryItem(
                item_id=f"inv_{npc_id}_{item_type}",
                item_type=item_type,
                item_name=item_name,
                quantity=quantity_delta,
                source_location_id=source_location_id,
                updated_at_tick=current_tick,
            ),
        )
        return
    next_quantity = existing.quantity + quantity_delta
    if next_quantity <= 0:
        delete_inventory_item(connection, existing.item_id)
        return
    upsert_inventory_item(
        connection,
        npc_id,
        existing.model_copy(
            update={
                "quantity": next_quantity,
                "updated_at_tick": current_tick,
                "source_location_id": source_location_id or existing.source_location_id,
            }
        ),
    )


def add_warehouse_quantity(
    connection: sqlite3.Connection,
    item_type: str,
    item_name: str,
    quantity_delta: int,
    current_tick: int,
    actor_id: str | None = None,
    reason: str = "adjustment",
) -> None:
    if quantity_delta == 0:
        return
    existing = next((item for item in list_warehouse_records(connection) if item.item_type == item_type), None)
    if existing is None:
        if quantity_delta <= 0:
            return
        upsert_warehouse_item(
            connection,
            WarehouseItem(
                item_id=f"warehouse_{item_type}",
                item_type=item_type,
                item_name=item_name,
                quantity=quantity_delta,
                updated_at_tick=current_tick,
            ),
        )
        record_warehouse_transaction(connection, actor_id, item_type, item_name, quantity_delta, reason, current_tick)
        return
    next_quantity = existing.quantity + quantity_delta
    if next_quantity <= 0:
        delete_warehouse_item(connection, existing.item_id)
        record_warehouse_transaction(connection, actor_id, item_type, existing.item_name, -existing.quantity, reason, current_tick)
        return
    upsert_warehouse_item(
        connection,
        existing.model_copy(
            update={
                "quantity": next_quantity,
                "updated_at_tick": current_tick,
                "item_name": item_name or existing.item_name,
            }
        ),
    )
    record_warehouse_transaction(connection, actor_id, item_type, item_name or existing.item_name, quantity_delta, reason, current_tick)


def record_warehouse_transaction(
    connection: sqlite3.Connection,
    actor_id: str | None,
    item_type: str,
    item_name: str,
    quantity_delta: int,
    reason: str,
    current_tick: int,
) -> None:
    if quantity_delta == 0:
        return
    existing_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM village_warehouse_transactions
        WHERE created_at_tick = ?
        """,
        (current_tick,),
    ).fetchone()[0]
    transaction_id = "warehouse_tx_%s_%s_%s_%03d" % (
        current_tick,
        sanitize_identifier(actor_id or "system"),
        sanitize_identifier(item_type),
        existing_count + 1,
    )
    insert_warehouse_transaction(
        connection,
        WarehouseTransaction(
            transaction_id=transaction_id,
            actor_id=actor_id,
            item_type=item_type,
            item_name=item_name,
            quantity_delta=quantity_delta,
            reason=reason,
            created_at_tick=current_tick,
        ),
    )


def sanitize_identifier(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value)[:80]


def build_monster_entity_from_event(event: WorldEvent) -> WorldEntity:
    monster_kind = str(event.payload.get("monster_kind") or "wolf")
    template = dict(MONSTER_TEMPLATES.get(monster_kind, MONSTER_TEMPLATES["wolf"]))
    quantity = max(1, int(event.payload.get("count", 1)))
    entity_id = event.payload.get("monster_id") or event.actor_id or f"monster_{event.event_id}"
    template.update({key: event.payload[key] for key in template.keys() & event.payload.keys()})
    max_health = int(template["health"]) * quantity
    intelligence = clamp_stat(int(template["intelligence"]))
    payload = dict(event.payload)
    payload.update(
        {
            "monster_kind": monster_kind,
            "monster_id": entity_id,
            "ai_mode": "npc" if intelligence >= INTELLIGENT_MONSTER_THRESHOLD else "beast",
            "loot_table": dict(template.get("loot_table", {})),
        }
    )
    return WorldEntity(
        entity_id=str(entity_id),
        entity_type="monster",
        display_name=str(template["display_name"]),
        location_id=event.location_id or "forest_edge",
        state="planning" if intelligence >= INTELLIGENT_MONSTER_THRESHOLD else "roaming",
        quantity=quantity,
        threat_level=max(clamp_stat(int(template["threat_level"])), min(100, 45 + int(event.importance * 0.5))),
        faction="monster",
        health=max_health,
        max_health=max_health,
        hostility=clamp_stat(int(template["hostility"])),
        aggression=clamp_stat(int(template["aggression"])),
        intelligence=intelligence,
        awareness=clamp_stat(int(template["awareness"])),
        morale=clamp_stat(int(template["morale"])),
        attack_power=clamp_stat(int(template["attack_power"])),
        defense=clamp_stat(int(template["defense"])),
        target_id=event.target_id,
        behavior=str(template["behavior"]),
        payload=payload,
        created_at_tick=event.created_at_tick,
        updated_at_tick=event.created_at_tick,
    )


def ensure_intelligent_monster_npc(connection: sqlite3.Connection, entity: WorldEntity) -> str:
    npc_id = str(entity.payload.get("npc_id") or f"npc_{entity.entity_id}")
    current_task = {
        "task_type": "hunt",
        "target_id": entity.target_id,
        "location_id": entity.location_id,
        "priority": max(50, entity.threat_level),
        "interruptible": True,
    }
    connection.execute(
        """
        INSERT INTO npc_state (
            npc_id,
            name,
            role,
            location_id,
            base_attributes_json,
            personality_json,
            needs_json,
            current_task_json,
            task_queue_json,
            message_queue_json,
            learning_bias_json,
            runtime_flags_json,
            updated_at_tick
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(npc_id) DO UPDATE SET
            location_id = excluded.location_id,
            current_task_json = excluded.current_task_json,
            updated_at_tick = excluded.updated_at_tick
        """,
        (
            npc_id,
            entity.display_name,
            "monster",
            entity.location_id,
            dump_json(monster_base_attributes(entity)),
            dump_json(monster_personality(entity)),
            dump_json(monster_needs(entity)),
            dump_json(current_task),
            "[]",
            "[]",
            dump_json(
                {
                    "risk_preference_delta": min(50, int(entity.aggression / 2)),
                    "cooperation_bias_delta": -20,
                    "combat_confidence_delta": min(50, int(entity.threat_level / 2)),
                }
            ),
            dump_json(
                {
                    "is_critical_npc": True,
                    "priority_tier": "high",
                    "thought_cooldown_ticks": 8,
                    "last_thought_tick": entity.updated_at_tick,
                    "last_plan_tick": entity.created_at_tick,
                }
            ),
            entity.updated_at_tick,
        ),
    )
    if entity.payload.get("npc_id") != npc_id:
        payload = dict(entity.payload)
        payload["npc_id"] = npc_id
        upsert_world_entity(connection, entity.model_copy(update={"payload": payload}))
    return npc_id


def monster_base_attributes(entity: WorldEntity) -> dict[str, int]:
    return {
        "strength": clamp_ability(entity.attack_power),
        "endurance": clamp_ability(int((entity.max_health + entity.morale) / 2)),
        "technique": clamp_ability(int((entity.attack_power + entity.defense) / 2)),
        "logic": clamp_ability(entity.intelligence),
        "perception": clamp_ability(entity.awareness),
        "influence": clamp_ability(int((entity.hostility + entity.morale) / 2)),
    }


def monster_personality(entity: WorldEntity) -> dict[str, int]:
    return {
        "bravery": clamp_ability(entity.morale),
        "kindness": 0,
        "prudence": clamp_ability(100 - entity.aggression),
        "greed": clamp_ability(entity.hostility),
        "curiosity": clamp_ability(entity.intelligence),
        "empathy": 0,
        "discipline": clamp_ability(entity.intelligence),
        "conformity": 0,
        "ambition": clamp_ability(entity.hostility),
        "loyalty": clamp_ability(entity.morale),
        "aggression": clamp_ability(entity.aggression),
        "patience": clamp_ability(100 - entity.aggression),
    }


def monster_needs(entity: WorldEntity) -> dict[str, int]:
    injury_pressure = 100 - int((entity.health / max(1, entity.max_health)) * 100)
    return {
        "energy": max(25, 100 - injury_pressure),
        "hunger": min(100, 45 + int(entity.aggression / 2)),
        "health": max(5, 100 - injury_pressure),
        "safety": max(10, entity.morale),
        "social": 0,
    }


def select_monster_target(entity: WorldEntity, occupants: list[Any]) -> Any:
    if not occupants:
        return None
    candidates = [state for state in occupants if role_value(state) != "monster"]
    if not candidates:
        return None
    role_priority = {
        "merchant": 5,
        "villager": 4,
        "player_related": 3,
        "guard": 2,
        "hunter": 1,
    }
    return max(
        candidates,
        key=lambda state: (
            role_priority.get(role_value(state), 0),
            entity.hostility,
            entity.awareness,
            100 - int(state.needs.safety),
            100 - int(state.needs.energy),
        ),
    )


def clear_monster_target(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(payload)
    cleaned.pop("target_npc_id", None)
    return cleaned


def role_value(state: Any) -> str:
    role = getattr(state, "role", "")
    return getattr(role, "value", str(role))


def clamp_stat(value: int) -> int:
    return max(0, min(value, 100))


def clamp_ability(value: int) -> int:
    return max(0, min(int(value / 10), 10))
