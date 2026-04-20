# Thought Output Schema

## Purpose

This document defines the canonical output structure of the NPC thought module.

The thought module may be implemented by:
- LLM-based service
- rule-based fallback service

The output must always be structured and machine-readable.

The thought module does NOT directly execute actions.
It only produces:
- subjective intention
- action preference ordering
- interruption decision
- social attitude adjustment

The game simulation layer is responsible for actual execution.

---

## Version

- schema_version: v0.1

---

## Design Rules

1. Output must be valid JSON.
2. Output must match this schema exactly.
3. Output must not include long free-form narrative.
4. Output must not invent unavailable actions.
5. Output must not directly mutate world state.
6. Output must rank candidate actions instead of assuming execution.

---

## Top-level Structure

```json
{
  "primary_goal": "",
  "emotional_state": "",
  "risk_attitude": 0,
  "interrupt_decision": {},
  "target_focus": [],
  "candidate_actions": [],
  "social_adjustments": [],
  "notes": ""
}
```

---

## Field Definitions

### primary_goal
- type: enum string
- required: yes
- allowed values:
  - survive
  - rest
  - get_food
  - patrol
  - trade
  - seek_help
  - help_other
  - hunt
  - avoid_threat
  - maintain_relationship
  - investigate

### emotional_state
- type: enum string
- required: yes
- allowed values:
  - calm
  - tense
  - afraid
  - angry
  - curious
  - hopeful
  - frustrated

### risk_attitude
- type: integer
- required: yes
- range: -100 to 100
- meaning:
  - negative = risk-averse
  - positive = risk-seeking
  - 0 = neutral

---

## interrupt_decision

Represents whether the NPC wants to interrupt the current task.

```json
{
  "should_interrupt": true,
  "reason": "threat_alert",
  "priority_delta": 25
}
```

### Fields
- should_interrupt: bool, required
- reason: enum string, required
- priority_delta: integer, required

### reason allowed values
- none
- urgent_need
- threat_alert
- social_request
- better_opportunity
- emotional_reaction

---

## target_focus

Represents entities or locations the NPC currently cares about.

```json
[
  {
    "target_id": "npc_merchant_001",
    "focus_type": "person",
    "attention_score": 80
  },
  {
    "target_id": "forest_edge",
    "focus_type": "location",
    "attention_score": 60
  }
]
```

### focus_type allowed values
- person
- location
- object
- event

### Rules
- array length recommended: 0 to 3
- attention_score range: 0 to 100

---

## candidate_actions

This is the most important field.

The thought layer proposes ranked candidate actions.
The simulation layer will validate and execute one of them.

```json
[
  {
    "action_type": "talk",
    "target_id": "npc_merchant_001",
    "location_id": null,
    "score": 82,
    "reason": "Need information and cooperation."
  },
  {
    "action_type": "hunt",
    "target_id": null,
    "location_id": "forest_edge",
    "score": 64,
    "reason": "Food pressure is increasing."
  }
]
```

### Rules
- type: array
- required: yes
- at least 1 item
- recommended max: 5 items
- sorted from highest score to lowest score

### action_type allowed values
- idle
- rest
- move
- talk
- help
- patrol
- gather
- hunt
- flee
- trade
- investigate
- warn

### Candidate Action Fields
- action_type: enum string, required
- target_id: string or null
- location_id: string or null
- score: integer, required, range 0 to 100
- reason: short string, required, max 120 chars

---

## social_adjustments

Represents immediate subjective change toward specific targets.

```json
[
  {
    "target_id": "player_001",
    "favor_delta": 5,
    "trust_delta": 10,
    "hostility_delta": 0,
    "reason": "Player recently helped during danger."
  }
]
```

### Rules
- type: array
- required: yes
- values are integer deltas
- recommended range per update: -20 to 20

### Fields
- target_id: string
- favor_delta: int
- trust_delta: int
- hostility_delta: int
- reason: short string

---

## notes
- type: string
- required: no
- purpose: brief internal summary for debugging
- recommended max length: 160 chars

---

## Invariants

1. `candidate_actions` must be sorted descending by `score`.
2. `candidate_actions` must only use allowed action types.
3. `should_interrupt = false` must use `reason = "none"` unless explicitly justified by fallback logic.
4. `social_adjustments` are subjective intent signals, not final committed state changes.
5. Final world state updates happen only after simulation layer validation.
6. - `candidate_actions` are temporary thought-layer proposals.
- `task_queue` contains validated executable follow-up tasks.
- `candidate_actions` must not be treated as committed execution plans.
- The planner is responsible for converting candidate actions into task queue entries.

---

## Minimal Example

```json
{
  "primary_goal": "get_food",
  "emotional_state": "tense",
  "risk_attitude": -10,
  "interrupt_decision": {
    "should_interrupt": true,
    "reason": "urgent_need",
    "priority_delta": 20
  },
  "target_focus": [
    {
      "target_id": "npc_merchant_001",
      "focus_type": "person",
      "attention_score": 75
    }
  ],
  "candidate_actions": [
    {
      "action_type": "talk",
      "target_id": "npc_merchant_001",
      "location_id": null,
      "score": 80,
      "reason": "Request food or trade support."
    },
    {
      "action_type": "gather",
      "target_id": null,
      "location_id": "forest_edge",
      "score": 62,
      "reason": "Food need remains high."
    },
    {
      "action_type": "rest",
      "target_id": null,
      "location_id": "inn",
      "score": 20,
      "reason": "Energy is acceptable, not top priority."
    }
  ],
  "social_adjustments": [
    {
      "target_id": "npc_merchant_001",
      "favor_delta": 0,
      "trust_delta": 0,
      "hostility_delta": 0,
      "reason": "No new social shift yet."
    }
  ],
  "notes": "Hungry NPC prefers low-risk social solution before gathering."
}
```
