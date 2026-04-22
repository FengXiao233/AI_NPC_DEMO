from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NpcRole(str, Enum):
    hunter = "hunter"
    merchant = "merchant"
    guard = "guard"
    villager = "villager"
    player_related = "player_related"
    monster = "monster"
    warrior = "warrior"
    producer = "producer"
    farmer = "farmer"
    blacksmith = "blacksmith"
    official = "official"
    village_chief = "village_chief"
    physician = "physician"


class NpcIdentity(str, Enum):
    merchant = "merchant"
    warrior = "warrior"
    producer = "producer"
    official = "official"
    physician = "physician"
    civilian = "civilian"
    monster = "monster"
    player_related = "player_related"


class TaskType(str, Enum):
    idle = "idle"
    rest = "rest"
    patrol = "patrol"
    gather = "gather"
    hunt = "hunt"
    eat = "eat"
    talk = "talk"
    help = "help"
    flee = "flee"
    trade = "trade"
    plant = "plant"
    forge = "forge"
    heal = "heal"
    investigate = "investigate"
    report = "report"


class TaskSource(str, Enum):
    thought = "thought"
    routine = "routine"
    message = "message"
    event = "event"


class TaskStatus(str, Enum):
    queued = "queued"
    paused = "paused"


class MessageType(str, Enum):
    chat = "chat"
    talk_request = "talk_request"
    help_request = "help_request"
    warning = "warning"
    trade_request = "trade_request"
    threat_alert = "threat_alert"
    npc_report = "npc_report"
    player_action = "player_action"
    player_utterance = "player_utterance"
    world_event = "world_event"


class PrimaryGoal(str, Enum):
    survive = "survive"
    rest = "rest"
    get_food = "get_food"
    produce = "produce"
    heal = "heal"
    patrol = "patrol"
    trade = "trade"
    seek_help = "seek_help"
    help_other = "help_other"
    hunt = "hunt"
    avoid_threat = "avoid_threat"
    maintain_relationship = "maintain_relationship"
    investigate = "investigate"
    report = "report"


class EmotionalState(str, Enum):
    calm = "calm"
    tense = "tense"
    afraid = "afraid"
    angry = "angry"
    curious = "curious"
    hopeful = "hopeful"
    frustrated = "frustrated"


class InterruptReason(str, Enum):
    none = "none"
    urgent_need = "urgent_need"
    threat_alert = "threat_alert"
    social_request = "social_request"
    better_opportunity = "better_opportunity"
    emotional_reaction = "emotional_reaction"


class FocusType(str, Enum):
    person = "person"
    location = "location"
    object = "object"
    event = "event"


class ActionType(str, Enum):
    idle = "idle"
    rest = "rest"
    move = "move"
    chat = "chat"
    talk = "talk"
    help = "help"
    patrol = "patrol"
    gather = "gather"
    hunt = "hunt"
    eat = "eat"
    flee = "flee"
    trade = "trade"
    plant = "plant"
    forge = "forge"
    heal = "heal"
    investigate = "investigate"
    warn = "warn"
    report = "report"


class StrictSchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BaseAttributes(StrictSchemaModel):
    strength: int = Field(ge=0, le=10)
    endurance: int = Field(default=5, ge=0, le=10)
    technique: int = Field(ge=0, le=10)
    logic: int = Field(ge=0, le=10)
    perception: int = Field(ge=0, le=10)
    influence: int = Field(ge=0, le=10)


class Personality(StrictSchemaModel):
    bravery: int = Field(ge=0, le=10)
    kindness: int = Field(ge=0, le=10)
    prudence: int = Field(ge=0, le=10)
    greed: int = Field(ge=0, le=10)
    curiosity: int = Field(ge=0, le=10)
    empathy: int = Field(default=5, ge=0, le=10)
    discipline: int = Field(default=5, ge=0, le=10)
    conformity: int = Field(default=5, ge=0, le=10)
    ambition: int = Field(default=5, ge=0, le=10)
    loyalty: int = Field(default=5, ge=0, le=10)
    aggression: int = Field(default=3, ge=0, le=10)
    patience: int = Field(default=5, ge=0, le=10)


class Needs(StrictSchemaModel):
    energy: int = Field(ge=0, le=100)
    hunger: int = Field(ge=0, le=100)
    health: int = Field(default=100, ge=0, le=100)
    safety: int = Field(ge=0, le=100)
    social: int = Field(ge=0, le=100)


class Relationship(StrictSchemaModel):
    target_id: str
    favor: int = Field(ge=-100, le=100)
    trust: int = Field(ge=-100, le=100)
    hostility: int = Field(ge=0, le=100)


class CurrentTask(StrictSchemaModel):
    task_type: TaskType
    target_id: Optional[str]
    location_id: Optional[str]
    priority: int = Field(ge=0, le=100)
    interruptible: bool


class QueuedTask(CurrentTask):
    task_id: str
    source: TaskSource
    status: TaskStatus


class Message(StrictSchemaModel):
    message_id: str
    message_type: MessageType
    from_id: str
    priority: int = Field(ge=0, le=100)
    created_at_tick: int = Field(ge=0)
    content: Optional[str] = Field(default=None, max_length=500)
    topic_hint: Optional[str] = Field(default=None, max_length=80)
    credibility: Optional[int] = Field(default=None, ge=0, le=100)


class MemorySummary(StrictSchemaModel):
    memory_id: str
    summary: str
    importance: int = Field(ge=0, le=100)
    related_ids: list[str]
    created_at_tick: int = Field(ge=0)
    expires_at_tick: Optional[int] = Field(default=None, ge=0)


class StoredMemoryRecord(MemorySummary):
    npc_id: str


class NpcBelief(StrictSchemaModel):
    belief_id: str
    source_type: str
    source_id: str
    topic_hint: Optional[str] = None
    claim: str = Field(max_length=500)
    confidence: int = Field(ge=0, le=100)
    truth_status: str
    created_at_tick: int = Field(ge=0)
    expires_at_tick: Optional[int] = Field(default=None, ge=0)


class StoredNpcBeliefRecord(NpcBelief):
    npc_id: str


class InventoryItem(StrictSchemaModel):
    item_id: str
    item_type: str = Field(max_length=80)
    quantity: int = Field(ge=0, le=999)
    item_name: str = Field(max_length=120)
    source_location_id: Optional[str] = Field(default=None, max_length=120)
    updated_at_tick: int = Field(ge=0)


class StoredInventoryItem(InventoryItem):
    npc_id: str


class WarehouseItem(StrictSchemaModel):
    item_id: str
    item_type: str = Field(max_length=80)
    quantity: int = Field(ge=0, le=999)
    item_name: str = Field(max_length=120)
    updated_at_tick: int = Field(ge=0)


class WarehouseTransaction(StrictSchemaModel):
    transaction_id: str
    actor_id: Optional[str] = None
    item_type: str = Field(max_length=80)
    item_name: str = Field(max_length=120)
    quantity_delta: int = Field(ge=-999, le=999)
    reason: str = Field(max_length=120)
    created_at_tick: int = Field(ge=0)


class ProductionOrder(StrictSchemaModel):
    order_id: str
    actor_id: str = Field(max_length=120)
    order_type: str = Field(max_length=40)
    status: str = Field(max_length=24)
    input_item_type: Optional[str] = Field(default=None, max_length=80)
    input_quantity: int = Field(ge=0, le=999)
    output_item_type: str = Field(max_length=80)
    output_item_name: str = Field(max_length=120)
    output_quantity: int = Field(ge=1, le=999)
    started_at_tick: int = Field(ge=0)
    completes_at_tick: int = Field(ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)


class SkillProficiency(StrictSchemaModel):
    skill_id: str = Field(max_length=80)
    domain: str = Field(max_length=80)
    level: int = Field(ge=0, le=100)
    xp: int = Field(default=0, ge=0, le=99999)
    affinity: int = Field(default=0, ge=-100, le=100)
    unlocked: bool = True


class IdentityProfile(StrictSchemaModel):
    identity: NpcIdentity
    profession: str = Field(max_length=80)
    identity_scores: dict[str, int] = Field(default_factory=dict)
    profession_interests: dict[str, int] = Field(default_factory=dict)
    skills: list[SkillProficiency] = Field(default_factory=list)
    capability_notes: list[str] = Field(default_factory=list)


class DialogueTurnRecord(StrictSchemaModel):
    turn_id: str
    npc_id: str
    speaker_id: str
    speaker_label: str = Field(max_length=80)
    role: str = Field(max_length=16)
    content: str = Field(max_length=500)
    created_at_tick: int = Field(ge=0)


class DialogueHistoryRecord(StrictSchemaModel):
    npc_id: str
    speaker_id: str
    summary: str = Field(default="", max_length=1200)
    recent_turns: list[DialogueTurnRecord] = Field(default_factory=list, max_length=10)
    total_turn_count: int = Field(default=0, ge=0)
    updated_at_tick: Optional[int] = Field(default=None, ge=0)


class StoredEventRecord(StrictSchemaModel):
    event_id: str
    event_type: str
    actor_id: Optional[str]
    target_id: Optional[str]
    location_id: Optional[str]
    payload: dict[str, Any]
    importance: int = Field(ge=0, le=100)
    created_at_tick: int = Field(ge=0)


class EventCatalogResponse(StrictSchemaModel):
    role: str
    task_type: str
    target: Optional[str] = None
    location: Optional[str] = None
    priority: int = Field(ge=0, le=100)
    interruptible: bool
    source: str
    status: str


class EventCatalogEntry(StrictSchemaModel):
    event_type: str
    category: str
    template_key: str
    routing_roles: list[str]
    payload_fields: list[str]
    significant: bool
    summary_template: str
    relationship_delta: Optional[dict[str, int]] = None
    default_role_responses: list[EventCatalogResponse] = Field(default_factory=list)


class WorldResourceNode(StrictSchemaModel):
    node_id: str
    location_id: str = Field(max_length=120)
    resource_type: str = Field(max_length=80)
    display_name: str = Field(max_length=120)
    available_quantity: int = Field(ge=0, le=999)
    max_quantity: int = Field(ge=0, le=999)
    respawn_rate: int = Field(ge=0, le=100)
    cooldown_ticks: int = Field(ge=0)
    last_harvested_tick: int = Field(default=0, ge=0)
    last_refreshed_tick: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorldEntity(StrictSchemaModel):
    entity_id: str
    entity_type: str = Field(max_length=80)
    display_name: str = Field(max_length=120)
    location_id: str = Field(max_length=120)
    state: str = Field(max_length=40)
    quantity: int = Field(ge=0, le=999)
    threat_level: int = Field(default=0, ge=0, le=100)
    faction: str = Field(default="neutral", max_length=40)
    health: int = Field(default=1, ge=0, le=999)
    max_health: int = Field(default=1, ge=1, le=999)
    hostility: int = Field(default=0, ge=0, le=100)
    aggression: int = Field(default=0, ge=0, le=100)
    intelligence: int = Field(default=0, ge=0, le=100)
    awareness: int = Field(default=0, ge=0, le=100)
    morale: int = Field(default=50, ge=0, le=100)
    attack_power: int = Field(default=0, ge=0, le=100)
    defense: int = Field(default=0, ge=0, le=100)
    target_id: Optional[str] = Field(default=None, max_length=120)
    behavior: str = Field(default="static", max_length=40)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at_tick: int = Field(ge=0)
    updated_at_tick: int = Field(ge=0)


class ResourceRefreshRecord(StrictSchemaModel):
    node_id: str
    resource_type: str = Field(max_length=80)
    location_id: str = Field(max_length=120)
    quantity_delta: int = Field(ge=-999, le=999)
    available_quantity: int = Field(ge=0, le=999)


class WorldUpdateResult(StrictSchemaModel):
    refreshed_resources: list[ResourceRefreshRecord] = Field(default_factory=list)
    moved_entity_ids: list[str] = Field(default_factory=list)
    generated_event_ids: list[str] = Field(default_factory=list)
    spawned_entity_ids: list[str] = Field(default_factory=list)
    matured_production_order_ids: list[str] = Field(default_factory=list)


class LearningBias(StrictSchemaModel):
    risk_preference_delta: int = Field(ge=-50, le=50)
    cooperation_bias_delta: int = Field(ge=-50, le=50)
    combat_confidence_delta: int = Field(ge=-50, le=50)


class RuntimeFlags(StrictSchemaModel):
    is_critical_npc: bool
    priority_tier: str = Field(default="normal", max_length=16)
    thought_cooldown_ticks: int = Field(ge=0)
    last_thought_tick: int = Field(ge=0)
    last_plan_tick: int = Field(default=0, ge=0)

    @field_validator("priority_tier")
    @classmethod
    def validate_priority_tier(cls, value: str) -> str:
        if value in {"highest", "high", "normal"}:
            return value
        return "normal"


class AgentState(StrictSchemaModel):
    npc_id: str
    name: str
    role: NpcRole
    location_id: str
    base_attributes: BaseAttributes
    personality: Personality
    identity: NpcIdentity = NpcIdentity.civilian
    profession: str = Field(default="villager", max_length=80)
    interests: dict[str, int] = Field(default_factory=dict)
    skills: list[SkillProficiency] = Field(default_factory=list)
    identity_profile: IdentityProfile | None = None
    needs: Needs
    relationships: list[Relationship]
    current_task: CurrentTask
    task_queue: list[QueuedTask]
    message_queue: list[Message]
    memory_summary: list[MemorySummary]
    beliefs: list[NpcBelief] = Field(default_factory=list)
    inventory: list[InventoryItem] = Field(default_factory=list)
    learning_bias: LearningBias
    runtime_flags: RuntimeFlags


class InterruptDecision(StrictSchemaModel):
    should_interrupt: bool
    reason: InterruptReason
    priority_delta: int

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, reason: InterruptReason, info):
        should_interrupt = info.data.get("should_interrupt")
        if should_interrupt is False and reason != InterruptReason.none:
            raise ValueError('reason must be "none" when should_interrupt is false')
        return reason


class TargetFocus(StrictSchemaModel):
    target_id: str
    focus_type: FocusType
    attention_score: int = Field(ge=0, le=100)


class CandidateAction(StrictSchemaModel):
    action_type: ActionType
    target_id: Optional[str]
    location_id: Optional[str]
    score: int = Field(ge=0, le=100)
    reason: str = Field(max_length=120)


class SocialAdjustment(StrictSchemaModel):
    target_id: str
    favor_delta: int = Field(ge=-20, le=20)
    trust_delta: int = Field(ge=-20, le=20)
    hostility_delta: int = Field(ge=-20, le=20)
    reason: str


class ThoughtResult(StrictSchemaModel):
    primary_goal: PrimaryGoal
    emotional_state: EmotionalState
    risk_attitude: int = Field(ge=-100, le=100)
    interrupt_decision: InterruptDecision
    target_focus: list[TargetFocus] = Field(max_length=3)
    candidate_actions: list[CandidateAction] = Field(min_length=1, max_length=5)
    social_adjustments: list[SocialAdjustment]
    notes: str = Field(default="", max_length=160)

    @field_validator("candidate_actions")
    @classmethod
    def validate_candidate_actions_sorted(cls, candidate_actions: list[CandidateAction]):
        scores = [action.score for action in candidate_actions]
        if scores != sorted(scores, reverse=True):
            raise ValueError("candidate_actions must be sorted by score descending")
        return candidate_actions

