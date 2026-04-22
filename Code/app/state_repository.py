import json
import sqlite3

from app.models import (
    AgentState,
    BaseAttributes,
    DialogueHistoryRecord,
    DialogueTurnRecord,
    InventoryItem,
    MemorySummary,
    NpcBelief,
    Personality,
    ProductionOrder,
    StoredEventRecord,
    StoredInventoryItem,
    StoredMemoryRecord,
    StoredNpcBeliefRecord,
    WarehouseItem,
    WarehouseTransaction,
    WorldEntity,
    WorldResourceNode,
)
from app.npc_profile import build_identity_profile
from scripts.init_sqlite import dump_json


def list_npc_ids(connection: sqlite3.Connection) -> list[str]:
    return [
        row[0]
        for row in connection.execute("SELECT npc_id FROM npc_state ORDER BY npc_id").fetchall()
    ]


def load_all_agent_states(connection: sqlite3.Connection) -> list[AgentState]:
    return [
        agent_state
        for npc_id in list_npc_ids(connection)
        if (agent_state := load_agent_state(connection, npc_id)) is not None
    ]


def load_agent_state(connection: sqlite3.Connection, npc_id: str) -> AgentState | None:
    row = connection.execute(
        """
        SELECT
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
            runtime_flags_json
        FROM npc_state
        WHERE npc_id = ?
        """,
        (npc_id,),
    ).fetchone()

    if row is None:
        return None

    runtime_flags = json.loads(row[11])
    current_tick = runtime_flags["last_thought_tick"]
    base_attributes = json.loads(row[4])
    personality = json.loads(row[5])
    profile = build_identity_profile(
        str(row[2]),
        BaseAttributes.model_validate(base_attributes),
        Personality.model_validate(personality),
    )
    data = {
        "npc_id": row[0],
        "name": row[1],
        "role": row[2],
        "location_id": row[3],
        "base_attributes": base_attributes,
        "personality": personality,
        "identity": profile.identity,
        "profession": profile.profession,
        "interests": profile.profession_interests,
        "skills": [skill.model_dump(mode="json") for skill in profile.skills],
        "identity_profile": profile.model_dump(mode="json"),
        "needs": json.loads(row[6]),
        "relationships": load_relationships(connection, npc_id),
        "current_task": json.loads(row[7]),
        "task_queue": json.loads(row[8]),
        "message_queue": json.loads(row[9]),
        "memory_summary": load_active_memories(connection, npc_id, current_tick),
        "beliefs": load_active_beliefs(connection, npc_id, current_tick),
        "inventory": load_inventory_records(connection, npc_id),
        "learning_bias": json.loads(row[10]),
        "runtime_flags": runtime_flags,
    }
    return AgentState.model_validate(data)


def load_relationships(connection: sqlite3.Connection, npc_id: str) -> list[dict]:
    rows = connection.execute(
        """
        SELECT target_id, favor, trust, hostility
        FROM relationships
        WHERE npc_id = ?
        ORDER BY target_id
        """,
        (npc_id,),
    ).fetchall()
    return [
        {
            "target_id": target_id,
            "favor": favor,
            "trust": trust,
            "hostility": hostility,
        }
        for target_id, favor, trust, hostility in rows
    ]


def load_active_memories(
    connection: sqlite3.Connection,
    npc_id: str,
    current_tick: int,
    limit: int = 10,
) -> list[dict]:
    rows = connection.execute(
        """
        SELECT memory_id, summary, importance, related_ids_json, created_at_tick, expires_at_tick
        FROM memories
        WHERE npc_id = ?
          AND (expires_at_tick IS NULL OR expires_at_tick > ?)
        ORDER BY importance DESC, created_at_tick DESC
        LIMIT ?
        """,
        (npc_id, current_tick, limit),
    ).fetchall()
    return [
        {
            "memory_id": memory_id,
            "summary": summary,
            "importance": importance,
            "related_ids": json.loads(related_ids_json),
            "created_at_tick": created_at_tick,
            "expires_at_tick": expires_at_tick,
        }
        for memory_id, summary, importance, related_ids_json, created_at_tick, expires_at_tick in rows
    ]


def list_event_records(connection: sqlite3.Connection, limit: int = 50) -> list[StoredEventRecord]:
    rows = connection.execute(
        """
        SELECT
            event_id,
            event_type,
            actor_id,
            target_id,
            location_id,
            payload_json,
            importance,
            created_at_tick
        FROM events
        ORDER BY created_at_tick DESC, event_id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        StoredEventRecord(
            event_id=event_id,
            event_type=event_type,
            actor_id=actor_id,
            target_id=target_id,
            location_id=location_id,
            payload=json.loads(payload_json),
            importance=importance,
            created_at_tick=created_at_tick,
        )
        for (
            event_id,
            event_type,
            actor_id,
            target_id,
            location_id,
            payload_json,
            importance,
            created_at_tick,
        ) in rows
    ]


def load_inventory_records(connection: sqlite3.Connection, npc_id: str) -> list[dict]:
    rows = connection.execute(
        """
        SELECT item_id, item_type, item_name, quantity, source_location_id, updated_at_tick
        FROM npc_inventory
        WHERE npc_id = ?
          AND quantity > 0
        ORDER BY item_type, item_id
        """,
        (npc_id,),
    ).fetchall()
    return [
        {
            "item_id": item_id,
            "item_type": item_type,
            "item_name": item_name,
            "quantity": quantity,
            "source_location_id": source_location_id,
            "updated_at_tick": updated_at_tick,
        }
        for item_id, item_type, item_name, quantity, source_location_id, updated_at_tick in rows
    ]


def list_inventory_records(connection: sqlite3.Connection, npc_id: str) -> list[StoredInventoryItem]:
    return [
        StoredInventoryItem(npc_id=npc_id, **record)
        for record in load_inventory_records(connection, npc_id)
    ]


def upsert_inventory_item(
    connection: sqlite3.Connection,
    npc_id: str,
    item: InventoryItem,
) -> None:
    connection.execute(
        """
        INSERT INTO npc_inventory (
            item_id,
            npc_id,
            item_type,
            item_name,
            quantity,
            source_location_id,
            updated_at_tick
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(item_id) DO UPDATE SET
            npc_id = excluded.npc_id,
            item_type = excluded.item_type,
            item_name = excluded.item_name,
            quantity = excluded.quantity,
            source_location_id = excluded.source_location_id,
            updated_at_tick = excluded.updated_at_tick
        """,
        (
            item.item_id,
            npc_id,
            item.item_type,
            item.item_name,
            item.quantity,
            item.source_location_id,
            item.updated_at_tick,
        ),
    )


def delete_inventory_item(connection: sqlite3.Connection, item_id: str) -> None:
    connection.execute("DELETE FROM npc_inventory WHERE item_id = ?", (item_id,))


def list_warehouse_records(connection: sqlite3.Connection) -> list[WarehouseItem]:
    rows = connection.execute(
        """
        SELECT item_id, item_type, item_name, quantity, updated_at_tick
        FROM village_warehouse
        WHERE quantity > 0
        ORDER BY item_type, item_id
        """
    ).fetchall()
    return [
        WarehouseItem(
            item_id=item_id,
            item_type=item_type,
            item_name=item_name,
            quantity=quantity,
            updated_at_tick=updated_at_tick,
        )
        for item_id, item_type, item_name, quantity, updated_at_tick in rows
    ]


def upsert_warehouse_item(connection: sqlite3.Connection, item: WarehouseItem) -> None:
    connection.execute(
        """
        INSERT INTO village_warehouse (
            item_id,
            item_type,
            item_name,
            quantity,
            updated_at_tick
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(item_id) DO UPDATE SET
            item_type = excluded.item_type,
            item_name = excluded.item_name,
            quantity = excluded.quantity,
            updated_at_tick = excluded.updated_at_tick
        """,
        (
            item.item_id,
            item.item_type,
            item.item_name,
            item.quantity,
            item.updated_at_tick,
        ),
    )


def delete_warehouse_item(connection: sqlite3.Connection, item_id: str) -> None:
    connection.execute("DELETE FROM village_warehouse WHERE item_id = ?", (item_id,))


def list_warehouse_transactions(connection: sqlite3.Connection, limit: int = 50) -> list[WarehouseTransaction]:
    rows = connection.execute(
        """
        SELECT transaction_id, actor_id, item_type, item_name, quantity_delta, reason, created_at_tick
        FROM village_warehouse_transactions
        ORDER BY created_at_tick DESC, transaction_id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        WarehouseTransaction(
            transaction_id=transaction_id,
            actor_id=actor_id,
            item_type=item_type,
            item_name=item_name,
            quantity_delta=quantity_delta,
            reason=reason,
            created_at_tick=created_at_tick,
        )
        for transaction_id, actor_id, item_type, item_name, quantity_delta, reason, created_at_tick in rows
    ]


def insert_warehouse_transaction(connection: sqlite3.Connection, transaction: WarehouseTransaction) -> None:
    connection.execute(
        """
        INSERT INTO village_warehouse_transactions (
            transaction_id,
            actor_id,
            item_type,
            item_name,
            quantity_delta,
            reason,
            created_at_tick
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(transaction_id) DO NOTHING
        """,
        (
            transaction.transaction_id,
            transaction.actor_id,
            transaction.item_type,
            transaction.item_name,
            transaction.quantity_delta,
            transaction.reason,
            transaction.created_at_tick,
        ),
    )


def list_production_orders(
    connection: sqlite3.Connection,
    include_completed: bool = False,
    limit: int = 50,
) -> list[ProductionOrder]:
    filters = "" if include_completed else "WHERE status != 'completed'"
    rows = connection.execute(
        f"""
        SELECT
            order_id,
            actor_id,
            order_type,
            status,
            input_item_type,
            input_quantity,
            output_item_type,
            output_item_name,
            output_quantity,
            started_at_tick,
            completes_at_tick,
            payload_json
        FROM village_production_orders
        {filters}
        ORDER BY completes_at_tick ASC, order_id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        ProductionOrder(
            order_id=order_id,
            actor_id=actor_id,
            order_type=order_type,
            status=status,
            input_item_type=input_item_type,
            input_quantity=input_quantity,
            output_item_type=output_item_type,
            output_item_name=output_item_name,
            output_quantity=output_quantity,
            started_at_tick=started_at_tick,
            completes_at_tick=completes_at_tick,
            payload=json.loads(payload_json),
        )
        for (
            order_id,
            actor_id,
            order_type,
            status,
            input_item_type,
            input_quantity,
            output_item_type,
            output_item_name,
            output_quantity,
            started_at_tick,
            completes_at_tick,
            payload_json,
        ) in rows
    ]


def upsert_production_order(connection: sqlite3.Connection, order: ProductionOrder) -> None:
    connection.execute(
        """
        INSERT INTO village_production_orders (
            order_id,
            actor_id,
            order_type,
            status,
            input_item_type,
            input_quantity,
            output_item_type,
            output_item_name,
            output_quantity,
            started_at_tick,
            completes_at_tick,
            payload_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(order_id) DO UPDATE SET
            status = excluded.status,
            payload_json = excluded.payload_json
        """,
        (
            order.order_id,
            order.actor_id,
            order.order_type,
            order.status,
            order.input_item_type,
            order.input_quantity,
            order.output_item_type,
            order.output_item_name,
            order.output_quantity,
            order.started_at_tick,
            order.completes_at_tick,
            dump_json(order.payload),
        ),
    )


def mark_production_order_completed(connection: sqlite3.Connection, order_id: str) -> None:
    connection.execute(
        """
        UPDATE village_production_orders
        SET status = 'completed'
        WHERE order_id = ?
        """,
        (order_id,),
    )


def list_world_resource_nodes(
    connection: sqlite3.Connection,
    location_id: str | None = None,
    include_depleted: bool = True,
) -> list[WorldResourceNode]:
    params: list[object] = []
    filters: list[str] = []
    if location_id is not None:
        filters.append("location_id = ?")
        params.append(location_id)
    if not include_depleted:
        filters.append("available_quantity > 0")
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    rows = connection.execute(
        f"""
        SELECT
            node_id,
            location_id,
            resource_type,
            display_name,
            available_quantity,
            max_quantity,
            respawn_rate,
            cooldown_ticks,
            last_harvested_tick,
            last_refreshed_tick,
            metadata_json
        FROM world_resource_nodes
        {where_clause}
        ORDER BY location_id, node_id
        """,
        params,
    ).fetchall()
    return [
        WorldResourceNode(
            node_id=node_id,
            location_id=stored_location_id,
            resource_type=resource_type,
            display_name=display_name,
            available_quantity=available_quantity,
            max_quantity=max_quantity,
            respawn_rate=respawn_rate,
            cooldown_ticks=cooldown_ticks,
            last_harvested_tick=last_harvested_tick,
            last_refreshed_tick=last_refreshed_tick,
            metadata=json.loads(metadata_json),
        )
        for (
            node_id,
            stored_location_id,
            resource_type,
            display_name,
            available_quantity,
            max_quantity,
            respawn_rate,
            cooldown_ticks,
            last_harvested_tick,
            last_refreshed_tick,
            metadata_json,
        ) in rows
    ]


def upsert_world_resource_node(connection: sqlite3.Connection, node: WorldResourceNode) -> None:
    connection.execute(
        """
        INSERT INTO world_resource_nodes (
            node_id,
            location_id,
            resource_type,
            display_name,
            available_quantity,
            max_quantity,
            respawn_rate,
            cooldown_ticks,
            last_harvested_tick,
            last_refreshed_tick,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(node_id) DO UPDATE SET
            location_id = excluded.location_id,
            resource_type = excluded.resource_type,
            display_name = excluded.display_name,
            available_quantity = excluded.available_quantity,
            max_quantity = excluded.max_quantity,
            respawn_rate = excluded.respawn_rate,
            cooldown_ticks = excluded.cooldown_ticks,
            last_harvested_tick = excluded.last_harvested_tick,
            last_refreshed_tick = excluded.last_refreshed_tick,
            metadata_json = excluded.metadata_json
        """,
        (
            node.node_id,
            node.location_id,
            node.resource_type,
            node.display_name,
            node.available_quantity,
            node.max_quantity,
            node.respawn_rate,
            node.cooldown_ticks,
            node.last_harvested_tick,
            node.last_refreshed_tick,
            dump_json(node.metadata),
        ),
    )


def list_world_entities(
    connection: sqlite3.Connection,
    location_id: str | None = None,
    include_inactive: bool = False,
) -> list[WorldEntity]:
    params: list[object] = []
    filters: list[str] = []
    if location_id is not None:
        filters.append("location_id = ?")
        params.append(location_id)
    if not include_inactive:
        filters.append("state != 'removed'")
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    rows = connection.execute(
        f"""
        SELECT
            entity_id,
            entity_type,
            display_name,
            location_id,
            state,
            quantity,
            threat_level,
            faction,
            health,
            max_health,
            hostility,
            aggression,
            intelligence,
            awareness,
            morale,
            attack_power,
            defense,
            target_id,
            behavior,
            payload_json,
            created_at_tick,
            updated_at_tick
        FROM world_entities
        {where_clause}
        ORDER BY updated_at_tick DESC, entity_id
        """,
        params,
    ).fetchall()
    return [
        WorldEntity(
            entity_id=entity_id,
            entity_type=entity_type,
            display_name=display_name,
            location_id=stored_location_id,
            state=state,
            quantity=quantity,
            threat_level=threat_level,
            faction=faction,
            health=health,
            max_health=max_health,
            hostility=hostility,
            aggression=aggression,
            intelligence=intelligence,
            awareness=awareness,
            morale=morale,
            attack_power=attack_power,
            defense=defense,
            target_id=target_id,
            behavior=behavior,
            payload=json.loads(payload_json),
            created_at_tick=created_at_tick,
            updated_at_tick=updated_at_tick,
        )
        for (
            entity_id,
            entity_type,
            display_name,
            stored_location_id,
            state,
            quantity,
            threat_level,
            faction,
            health,
            max_health,
            hostility,
            aggression,
            intelligence,
            awareness,
            morale,
            attack_power,
            defense,
            target_id,
            behavior,
            payload_json,
            created_at_tick,
            updated_at_tick,
        ) in rows
    ]


def load_world_entity(connection: sqlite3.Connection, entity_id: str) -> WorldEntity | None:
    rows = list_world_entities(connection, include_inactive=True)
    for entity in rows:
        if entity.entity_id == entity_id:
            return entity
    return None


def upsert_world_entity(connection: sqlite3.Connection, entity: WorldEntity) -> None:
    connection.execute(
        """
        INSERT INTO world_entities (
            entity_id,
            entity_type,
            display_name,
            location_id,
            state,
            quantity,
            threat_level,
            faction,
            health,
            max_health,
            hostility,
            aggression,
            intelligence,
            awareness,
            morale,
            attack_power,
            defense,
            target_id,
            behavior,
            payload_json,
            created_at_tick,
            updated_at_tick
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(entity_id) DO UPDATE SET
            entity_type = excluded.entity_type,
            display_name = excluded.display_name,
            location_id = excluded.location_id,
            state = excluded.state,
            quantity = excluded.quantity,
            threat_level = excluded.threat_level,
            faction = excluded.faction,
            health = excluded.health,
            max_health = excluded.max_health,
            hostility = excluded.hostility,
            aggression = excluded.aggression,
            intelligence = excluded.intelligence,
            awareness = excluded.awareness,
            morale = excluded.morale,
            attack_power = excluded.attack_power,
            defense = excluded.defense,
            target_id = excluded.target_id,
            behavior = excluded.behavior,
            payload_json = excluded.payload_json,
            created_at_tick = excluded.created_at_tick,
            updated_at_tick = excluded.updated_at_tick
        """,
        (
            entity.entity_id,
            entity.entity_type,
            entity.display_name,
            entity.location_id,
            entity.state,
            entity.quantity,
            entity.threat_level,
            entity.faction,
            entity.health,
            entity.max_health,
            entity.hostility,
            entity.aggression,
            entity.intelligence,
            entity.awareness,
            entity.morale,
            entity.attack_power,
            entity.defense,
            entity.target_id,
            entity.behavior,
            dump_json(entity.payload),
            entity.created_at_tick,
            entity.updated_at_tick,
        ),
    )


def find_event_records_by_topic(
    connection: sqlite3.Connection,
    topic_hint: str | None,
    location_id: str | None,
    created_at_tick: int,
    lookback_ticks: int = 120,
    limit: int = 5,
) -> list[StoredEventRecord]:
    event_types = event_types_for_topic(topic_hint)
    if not event_types:
        return []

    earliest_evidence_tick = max(0, created_at_tick - lookback_ticks)
    params: list[object] = [*event_types, earliest_evidence_tick]
    location_filter = ""
    if location_id is not None:
        location_filter = "AND (location_id = ? OR location_id IS NULL)"
        params.append(location_id)
    params.append(limit)

    placeholders = ",".join("?" for _ in event_types)
    rows = connection.execute(
        f"""
        SELECT
            event_id,
            event_type,
            actor_id,
            target_id,
            location_id,
            payload_json,
            importance,
            created_at_tick
          FROM events
          WHERE event_type IN ({placeholders})
           AND created_at_tick >= ?
          {location_filter}
        ORDER BY created_at_tick DESC, importance DESC, event_id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [
        StoredEventRecord(
            event_id=event_id,
            event_type=event_type,
            actor_id=actor_id,
            target_id=target_id,
            location_id=stored_location_id,
            payload=json.loads(payload_json),
            importance=importance,
            created_at_tick=event_created_at_tick,
        )
        for (
            event_id,
            event_type,
            actor_id,
            target_id,
            stored_location_id,
            payload_json,
            importance,
            event_created_at_tick,
        ) in rows
    ]


def event_types_for_topic(topic_hint: str | None) -> tuple[str, ...]:
    if topic_hint == "monster_threat":
        return ("monster_appeared", "attack")
    if topic_hint == "suspicious_arrival":
        return ("suspicious_arrival",)
    if topic_hint == "food_shortage":
        return ("food_shortage",)
    if topic_hint == "help_request":
        return ("help_given", "help_refused", "player_helped", "player_harmed")
    return ()


def list_memory_records(
    connection: sqlite3.Connection,
    npc_id: str,
    current_tick: int | None = None,
    include_expired: bool = False,
    limit: int = 50,
) -> list[StoredMemoryRecord]:
    params: list[object] = [npc_id]
    expiration_filter = ""
    if not include_expired and current_tick is not None:
        expiration_filter = "AND (expires_at_tick IS NULL OR expires_at_tick > ?)"
        params.append(current_tick)
    params.append(limit)

    rows = connection.execute(
        f"""
        SELECT
            memory_id,
            npc_id,
            summary,
            importance,
            related_ids_json,
            created_at_tick,
            expires_at_tick
        FROM memories
        WHERE npc_id = ?
          {expiration_filter}
        ORDER BY created_at_tick DESC, importance DESC, memory_id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [
        StoredMemoryRecord(
            memory_id=memory_id,
            npc_id=stored_npc_id,
            summary=summary,
            importance=importance,
            related_ids=json.loads(related_ids_json),
            created_at_tick=created_at_tick,
            expires_at_tick=expires_at_tick,
        )
        for (
            memory_id,
            stored_npc_id,
            summary,
            importance,
            related_ids_json,
            created_at_tick,
            expires_at_tick,
        ) in rows
    ]


def load_active_beliefs(
    connection: sqlite3.Connection,
    npc_id: str,
    current_tick: int,
    limit: int = 10,
) -> list[dict]:
    rows = connection.execute(
        """
        SELECT
            belief_id,
            source_type,
            source_id,
            topic_hint,
            claim,
            confidence,
            truth_status,
            created_at_tick,
            expires_at_tick
        FROM npc_beliefs
        WHERE npc_id = ?
          AND (expires_at_tick IS NULL OR expires_at_tick > ?)
        ORDER BY confidence DESC, created_at_tick DESC
        LIMIT ?
        """,
        (npc_id, current_tick, limit),
    ).fetchall()
    return [
        {
            "belief_id": belief_id,
            "source_type": source_type,
            "source_id": source_id,
            "topic_hint": topic_hint,
            "claim": claim,
            "confidence": confidence,
            "truth_status": truth_status,
            "created_at_tick": created_at_tick,
            "expires_at_tick": expires_at_tick,
        }
        for (
            belief_id,
            source_type,
            source_id,
            topic_hint,
            claim,
            confidence,
            truth_status,
            created_at_tick,
            expires_at_tick,
        ) in rows
    ]


def list_belief_records(
    connection: sqlite3.Connection,
    npc_id: str,
    current_tick: int | None = None,
    include_expired: bool = False,
    limit: int = 50,
) -> list[StoredNpcBeliefRecord]:
    params: list[object] = [npc_id]
    expiration_filter = ""
    if not include_expired and current_tick is not None:
        expiration_filter = "AND (expires_at_tick IS NULL OR expires_at_tick > ?)"
        params.append(current_tick)
    params.append(limit)

    rows = connection.execute(
        f"""
        SELECT
            belief_id,
            npc_id,
            source_type,
            source_id,
            topic_hint,
            claim,
            confidence,
            truth_status,
            created_at_tick,
            expires_at_tick
        FROM npc_beliefs
        WHERE npc_id = ?
          {expiration_filter}
        ORDER BY created_at_tick DESC, confidence DESC, belief_id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [
        StoredNpcBeliefRecord(
            belief_id=belief_id,
            npc_id=stored_npc_id,
            source_type=source_type,
            source_id=source_id,
            topic_hint=topic_hint,
            claim=claim,
            confidence=confidence,
            truth_status=truth_status,
            created_at_tick=created_at_tick,
            expires_at_tick=expires_at_tick,
        )
        for (
            belief_id,
            stored_npc_id,
            source_type,
            source_id,
            topic_hint,
            claim,
            confidence,
            truth_status,
            created_at_tick,
            expires_at_tick,
        ) in rows
    ]


def list_dialogue_turn_records(
    connection: sqlite3.Connection,
    npc_id: str,
    speaker_id: str,
    limit: int | None = None,
    newest_first: bool = False,
) -> list[DialogueTurnRecord]:
    order_direction = "DESC" if newest_first else "ASC"
    role_order_direction = "DESC" if newest_first else "ASC"
    limit_clause = "LIMIT ?" if limit is not None else ""
    params: list[object] = [npc_id, speaker_id]
    if limit is not None:
        params.append(limit)

    rows = connection.execute(
        f"""
        SELECT
            turn_id,
            npc_id,
            speaker_id,
            speaker_label,
            role,
            content,
            created_at_tick
        FROM dialogue_turns
        WHERE npc_id = ?
          AND speaker_id = ?
        ORDER BY
            created_at_tick {order_direction},
            CASE role WHEN 'player' THEN 0 ELSE 1 END {role_order_direction},
            turn_id {order_direction}
        {limit_clause}
        """,
        params,
    ).fetchall()
    return [
        DialogueTurnRecord(
            turn_id=turn_id,
            npc_id=stored_npc_id,
            speaker_id=stored_speaker_id,
            speaker_label=speaker_label,
            role=role,
            content=content,
            created_at_tick=created_at_tick,
        )
        for (
            turn_id,
            stored_npc_id,
            stored_speaker_id,
            speaker_label,
            role,
            content,
            created_at_tick,
        ) in rows
    ]


def load_dialogue_history_record(
    connection: sqlite3.Connection,
    npc_id: str,
    speaker_id: str,
    recent_turn_limit: int = 6,
) -> DialogueHistoryRecord:
    session_row = connection.execute(
        """
        SELECT summary, total_turn_count, updated_at_tick
        FROM dialogue_sessions
        WHERE npc_id = ?
          AND speaker_id = ?
        """,
        (npc_id, speaker_id),
    ).fetchone()

    recent_turns = list_dialogue_turn_records(
        connection,
        npc_id,
        speaker_id,
        limit=recent_turn_limit,
        newest_first=True,
    )
    recent_turns.reverse()

    summary = ""
    total_turn_count = len(recent_turns)
    updated_at_tick = None
    if session_row is not None:
        summary = session_row[0]
        total_turn_count = session_row[1]
        updated_at_tick = session_row[2]

    return DialogueHistoryRecord(
        npc_id=npc_id,
        speaker_id=speaker_id,
        summary=summary,
        recent_turns=recent_turns,
        total_turn_count=total_turn_count,
        updated_at_tick=updated_at_tick,
    )


def store_dialogue_turn(connection: sqlite3.Connection, turn: DialogueTurnRecord) -> None:
    connection.execute(
        """
        INSERT INTO dialogue_turns (
            turn_id,
            npc_id,
            speaker_id,
            speaker_label,
            role,
            content,
            created_at_tick
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(turn_id) DO UPDATE SET
            speaker_label = excluded.speaker_label,
            role = excluded.role,
            content = excluded.content,
            created_at_tick = excluded.created_at_tick
        """,
        (
            turn.turn_id,
            turn.npc_id,
            turn.speaker_id,
            turn.speaker_label,
            turn.role,
            turn.content,
            turn.created_at_tick,
        ),
    )


def upsert_dialogue_session(
    connection: sqlite3.Connection,
    npc_id: str,
    speaker_id: str,
    summary: str,
    total_turn_count: int,
    updated_at_tick: int | None,
) -> None:
    connection.execute(
        """
        INSERT INTO dialogue_sessions (
            npc_id,
            speaker_id,
            summary,
            total_turn_count,
            updated_at_tick
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(npc_id, speaker_id) DO UPDATE SET
            summary = excluded.summary,
            total_turn_count = excluded.total_turn_count,
            updated_at_tick = excluded.updated_at_tick
        """,
        (
            npc_id,
            speaker_id,
            summary,
            total_turn_count,
            updated_at_tick,
        ),
    )


def upsert_npc_belief(connection: sqlite3.Connection, npc_id: str, belief: NpcBelief) -> None:
    connection.execute(
        """
        INSERT INTO npc_beliefs (
            belief_id,
            npc_id,
            source_type,
            source_id,
            topic_hint,
            claim,
            confidence,
            truth_status,
            created_at_tick,
            expires_at_tick
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(belief_id) DO UPDATE SET
            topic_hint = excluded.topic_hint,
            claim = excluded.claim,
            confidence = excluded.confidence,
            truth_status = excluded.truth_status,
            expires_at_tick = excluded.expires_at_tick
        """,
        (
            belief.belief_id,
            npc_id,
            belief.source_type,
            belief.source_id,
            belief.topic_hint,
            belief.claim,
            belief.confidence,
            belief.truth_status,
            belief.created_at_tick,
            belief.expires_at_tick,
        ),
    )


def update_npc_belief_truth_status(
    connection: sqlite3.Connection,
    belief_id: str,
    truth_status: str,
    confidence: int,
    expires_at_tick: int | None,
) -> None:
    connection.execute(
        """
        UPDATE npc_beliefs
        SET truth_status = ?,
            confidence = ?,
            expires_at_tick = ?
        WHERE belief_id = ?
        """,
        (
            truth_status,
            confidence,
            expires_at_tick,
            belief_id,
        ),
    )


def store_memory_record(connection: sqlite3.Connection, npc_id: str, memory: MemorySummary) -> None:
    connection.execute(
        """
        INSERT INTO memories (
            memory_id,
            npc_id,
            summary,
            importance,
            related_ids_json,
            created_at_tick,
            expires_at_tick
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(memory_id) DO UPDATE SET
            npc_id = excluded.npc_id,
            summary = excluded.summary,
            importance = excluded.importance,
            related_ids_json = excluded.related_ids_json,
            created_at_tick = excluded.created_at_tick,
            expires_at_tick = excluded.expires_at_tick
        """,
        (
            memory.memory_id,
            npc_id,
            memory.summary,
            memory.importance,
            dump_json(memory.related_ids),
            memory.created_at_tick,
            memory.expires_at_tick,
        ),
    )


def update_npc_message_queue(
    connection: sqlite3.Connection,
    npc_id: str,
    message_queue: list[dict],
) -> None:
    connection.execute(
        """
        UPDATE npc_state
        SET message_queue_json = ?
        WHERE npc_id = ?
        """,
        (
            dump_json(message_queue),
            npc_id,
        ),
    )
