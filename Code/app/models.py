from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NpcRole(str, Enum):
    hunter = "hunter"
    merchant = "merchant"
    guard = "guard"
    villager = "villager"
    player_related = "player_related"


class TaskType(str, Enum):
    idle = "idle"
    rest = "rest"
    patrol = "patrol"
    gather = "gather"
    hunt = "hunt"
    talk = "talk"
    help = "help"
    flee = "flee"
    trade = "trade"
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
    talk_request = "talk_request"
    help_request = "help_request"
    warning = "warning"
    trade_request = "trade_request"
    threat_alert = "threat_alert"
    player_action = "player_action"
    player_utterance = "player_utterance"
    world_event = "world_event"


class PrimaryGoal(str, Enum):
    survive = "survive"
    rest = "rest"
    get_food = "get_food"
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
    talk = "talk"
    help = "help"
    patrol = "patrol"
    gather = "gather"
    hunt = "hunt"
    flee = "flee"
    trade = "trade"
    investigate = "investigate"
    warn = "warn"
    report = "report"


class StrictSchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BaseAttributes(StrictSchemaModel):
    strength: int = Field(ge=0, le=10)
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


class Needs(StrictSchemaModel):
    energy: int = Field(ge=0, le=100)
    hunger: int = Field(ge=0, le=100)
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


class LearningBias(StrictSchemaModel):
    risk_preference_delta: int = Field(ge=-50, le=50)
    cooperation_bias_delta: int = Field(ge=-50, le=50)
    combat_confidence_delta: int = Field(ge=-50, le=50)


class RuntimeFlags(StrictSchemaModel):
    is_critical_npc: bool
    thought_cooldown_ticks: int = Field(ge=0)
    last_thought_tick: int = Field(ge=0)


class AgentState(StrictSchemaModel):
    npc_id: str
    name: str
    role: NpcRole
    location_id: str
    base_attributes: BaseAttributes
    personality: Personality
    needs: Needs
    relationships: list[Relationship]
    current_task: CurrentTask
    task_queue: list[QueuedTask]
    message_queue: list[Message]
    memory_summary: list[MemorySummary]
    beliefs: list[NpcBelief] = Field(default_factory=list)
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

