# NPC State Schema

## Purpose

This document defines the canonical runtime state structure for an NPC in the first playable prototype.

The schema is used by:
- Godot simulation layer
- Python thought service
- SQLite persistence layer
- test fixtures and seed data

This is the source of truth for field names and meanings.

---

## Version

- schema_version: v0.1

---

## Design Goals

The first version only supports:
- small-scale NPC social simulation
- low-frequency thought updates
- rule-based action execution
- lightweight relationship and memory changes

The first version does NOT support:
- reproduction
- inheritance
- large-scale world simulation
- complex economy
- multi-region scheduling
- full skill trees

---

## Top-level Structure

Each NPC state is represented as a single object:

```json
{
  "npc_id": "npc_hunter_001",
  "name": "Aren",
  "role": "hunter",
  "location_id": "village_square",
  "base_attributes": {},
  "personality": {},
  "needs": {},
  "relationships": [],
  "current_task": {},
  "task_queue":[],
  "message_queue": [],
  "memory_summary": [],
  "learning_bias": {},
  "runtime_flags": {}
}
```

---

## Field Definitions

### npc_id
- type: string
- required: yes
- description: unique stable NPC identifier
- example: `npc_hunter_001`

### name
- type: string
- required: yes
- description: display name

### role
- type: enum string
- required: yes
- allowed values:
  - hunter
  - merchant
  - guard
  - villager
  - player_related
- description: broad gameplay role

### location_id
- type: string
- required: yes
- description: current area or node id
- example: `inn`, `market`, `forest_edge`

---

## base_attributes

Represents relatively stable capability values.

```json
{
  "strength": 6,
  "technique": 5,
  "logic": 4,
  "perception": 7,
  "influence": 3
}
```

### Rules
- type: object
- required: yes
- all values are integers
- recommended range: 0 to 10

### Fields
- strength
- technique
- logic
- perception
- influence

---

## personality

Represents long-term behavioral tendency.

```json
{
  "bravery": 7,
  "kindness": 4,
  "prudence": 5,
  "greed": 3,
  "curiosity": 6
}
```

### Rules
- type: object
- required: yes
- all values are integers
- recommended range: 0 to 10

### Fields
- bravery
- kindness
- prudence
- greed
- curiosity

---

## needs

Represents short-term internal pressure.

```json
{
  "energy": 65,
  "hunger": 40,
  "safety": 55,
  "social": 30
}
```

### Rules
- type: object
- required: yes
- all values are integers
- range: 0 to 100
- higher value means stronger current state
- interpretation:
  - energy: remaining stamina
  - hunger: urgency of food need
  - safety: current feeling of safety
  - social: desire for interaction

---

## relationships

Represents directed social values from this NPC to others.

```json
[
  {
    "target_id": "npc_merchant_001",
    "favor": 10,
    "trust": 5,
    "hostility": 0
  },
  {
    "target_id": "player_001",
    "favor": 15,
    "trust": 20,
    "hostility": 0
  }
]
```

### Rules
- type: array
- required: yes
- one record per target entity
- values are integers
- recommended range: -100 to 100 for favor/trust
- recommended range: 0 to 100 for hostility

### Relationship Fields
- target_id: string
- favor: how much this NPC likes the target
- trust: how much this NPC believes the target is reliable
- hostility: how much this NPC sees the target as a threat or enemy

---

## current_task

Represents what the NPC is currently doing.

```json
{
  "task_type": "patrol",
  "target_id": null,
  "location_id": "village_gate",
  "priority": 50,
  "interruptible": true
}
```
---
## task_queue

Represents planned follow-up tasks that are not currently being executed.

```json
[
  {
    "task_id": "task_002",
    "task_type": "talk",
    "target_id": "npc_merchant_001",
    "location_id": "market",
    "priority": 70,
    "interruptible": true,
    "source": "thought",
    "status": "queued"
  },
  {
    "task_id": "task_003",
    "task_type": "gather",
    "target_id": null,
    "location_id": "forest_edge",
    "priority": 50,
    "interruptible": true,
    "source": "routine",
    "status": "queued"
  }
]
```
### task_type allowed values
- idle
- rest
- patrol
- gather
- hunt
- talk
- help
- flee
- trade
- investigate

### Rules
- required: yes
- only one active current_task at a time

---

## message_queue

Represents incoming requests or events that may affect thought.

```json
[
  {
    "message_id": "msg_001",
    "message_type": "help_request",
    "from_id": "npc_merchant_001",
    "priority": 70,
    "created_at_tick": 120
  }
]
```

### message_type allowed values
- talk_request
- help_request
- warning
- trade_request
- threat_alert
- player_action
- world_event

---

## memory_summary

Represents recent important events remembered by the NPC.

```json
[
  {
    "memory_id": "mem_001",
    "summary": "The merchant refused to share food.",
    "importance": 80,
    "related_ids": ["npc_merchant_001"],
    "created_at_tick": 90
  },
  {
    "memory_id": "mem_002",
    "summary": "The player helped during the wolf attack.",
    "importance": 95,
    "related_ids": ["player_001"],
    "created_at_tick": 105
  }
]
```

### Rules
- required: yes
- keep only recent important memories in first prototype
- recommended size: 3 to 10 items

---

## learning_bias

Represents slowly changing learned tendencies.

```json
{
  "risk_preference_delta": -10,
  "cooperation_bias_delta": 15,
  "combat_confidence_delta": 5
}
```

### Rules
- type: object
- required: yes
- values are integers
- recommended range: -50 to 50

### Fields
- risk_preference_delta
- cooperation_bias_delta
- combat_confidence_delta

---

## runtime_flags

Represents simulation-specific control flags.

```json
{
  "is_critical_npc": true,
  "thought_cooldown_ticks": 20,
  "last_thought_tick": 100
}
```

### Fields
- is_critical_npc: bool
- thought_cooldown_ticks: int
- last_thought_tick: int

---

## Invariants

The following rules must always hold:

1. `npc_id` must be unique and stable.
2. All numeric personality and `base_attributes` values must remain within their allowed range.
3. `current_task` must always exist.
4. `relationships` are directed, not automatically mirrored.
5. `memory_summary` only contains condensed memories, not full dialogue logs.
6. `learning_bias` modifies decisions but does not replace personality.
7. `task_queue` contains future tasks only and must not duplicate `current_task`.
8.  Interrupted tasks may be re-added to `task_queue` with status = `paused`.

---

## Minimal Example

```json
{
  "npc_id": "npc_guard_001",
  "name": "Darin",
  "role": "guard",
  "location_id": "village_gate",
  "base_attributes": {
    "strength": 7,
    "technique": 6,
    "logic": 5,
    "perception": 6,
    "influence": 4
  },
  "personality": {
    "bravery": 8,
    "kindness": 5,
    "prudence": 6,
    "greed": 2,
    "curiosity": 3
  },
  "needs": {
    "energy": 70,
    "hunger": 35,
    "safety": 80,
    "social": 20
  },
  "relationships": [
    {
      "target_id": "npc_merchant_001",
      "favor": 5,
      "trust": 10,
      "hostility": 0
    }
  ],
  "current_task": {
    "task_type": "patrol",
    "target_id": null,
    "location_id": "village_gate",
    "priority": 60,
    "interruptible": true
  },
    "task_queue": [
    {
      "task_id": "task_002",
      "task_type": "investigate",
      "target_id": null,
      "location_id": "market",
      "priority": 40,
      "interruptible": true,
      "source": "message",
      "status": "queued"
    }
  ],
  "message_queue": [],
  "memory_summary": [],
  "learning_bias": {
    "risk_preference_delta": 0,
    "cooperation_bias_delta": 5,
    "combat_confidence_delta": 0
  },
  "runtime_flags": {
    "is_critical_npc": true,
    "thought_cooldown_ticks": 20,
    "last_thought_tick": 0
  }
}
```
