from app.models import AgentState, CandidateAction, SocialAdjustment, ThoughtResult


def build_fallback_thought(agent_state: AgentState) -> ThoughtResult:
    primary_goal = choose_primary_goal(agent_state)
    emotional_state = choose_emotional_state(agent_state)
    candidate_actions = choose_candidate_actions(agent_state, primary_goal)
    interrupt_decision = choose_interrupt_decision(agent_state, primary_goal)
    target_focus = choose_target_focus(agent_state)

    return ThoughtResult(
        primary_goal=primary_goal,
        emotional_state=emotional_state,
        risk_attitude=agent_state.learning_bias.risk_preference_delta,
        interrupt_decision=interrupt_decision,
        target_focus=target_focus,
        candidate_actions=candidate_actions,
        social_adjustments=choose_social_adjustments(agent_state),
        notes="Fallback rules generated this thought result.",
    )


def choose_primary_goal(agent_state: AgentState) -> str:
    if has_message_type(agent_state, "threat_alert") or agent_state.needs.safety < 35:
        return "avoid_threat"
    if has_belief_topic(agent_state, "monster_threat") or has_player_utterance_topic(agent_state, "monster_threat"):
        return "avoid_threat"
    if agent_state.role == "merchant" and has_belief_topic(agent_state, "suspicious_arrival", truth_statuses={"unverified"}):
        return "report"
    if has_belief_topic(agent_state, "suspicious_arrival", truth_statuses={"unverified"}) or has_player_utterance_topic(agent_state, "suspicious_arrival"):
        return "investigate"
    if agent_state.needs.hunger >= 65:
        return "get_food"
    if has_message_type(agent_state, "help_request"):
        return "help_other"
    if has_player_utterance_topic(agent_state, "help_request"):
        return "help_other"
    if agent_state.needs.energy < 30:
        return "rest"
    if agent_state.needs.social >= 65:
        return "maintain_relationship"
    if agent_state.role == "merchant":
        return "trade"
    if agent_state.role == "guard":
        return "patrol"
    if agent_state.role == "hunter":
        return "hunt"
    return "maintain_relationship"


def choose_emotional_state(agent_state: AgentState) -> str:
    if (
        has_danger_memory(agent_state)
        or has_message_type(agent_state, "threat_alert")
        or has_belief_topic(agent_state, "monster_threat")
        or has_player_utterance_topic(agent_state, "monster_threat")
    ):
        return "afraid" if agent_state.personality.bravery < 5 else "tense"
    if agent_state.needs.safety < 45 or agent_state.needs.hunger >= 65 or agent_state.needs.social >= 65:
        return "tense"
    if has_helpful_player_memory(agent_state):
        return "hopeful"
    return "calm"


def choose_interrupt_decision(agent_state: AgentState, primary_goal: str) -> dict:
    should_interrupt = False
    reason = "none"
    priority_delta = 0

    if has_message_type(agent_state, "threat_alert") or primary_goal == "avoid_threat":
        should_interrupt = True
        reason = "threat_alert"
        priority_delta = 35
    elif agent_state.needs.hunger >= 75:
        should_interrupt = True
        reason = "urgent_need"
        priority_delta = 25
    elif agent_state.needs.social >= 75:
        should_interrupt = True
        reason = "social_request"
        priority_delta = 20
    elif has_message_type(agent_state, "help_request") and agent_state.personality.kindness >= 5:
        should_interrupt = True
        reason = "social_request"
        priority_delta = 15
    elif has_high_credibility_player_utterance(agent_state):
        should_interrupt = True
        reason = "social_request"
        priority_delta = 12

    return {
        "should_interrupt": should_interrupt,
        "reason": reason,
        "priority_delta": priority_delta,
    }


def choose_target_focus(agent_state: AgentState) -> list[dict]:
    focus = []
    active_memories = active_memory_summary(agent_state)

    if agent_state.message_queue:
        message = max(agent_state.message_queue, key=lambda item: item.priority)
        focus.append(
            {
                "target_id": message.from_id,
                "focus_type": "person",
                "attention_score": min(message.priority + 20, 100),
            }
        )

    if agent_state.location_id and len(focus) < 3:
        focus.append(
            {
                "target_id": agent_state.location_id,
                "focus_type": "location",
                "attention_score": 60,
            }
        )

    for memory in sorted(active_memories, key=lambda item: item.importance, reverse=True):
        for related_id in memory.related_ids:
            if related_id not in {item["target_id"] for item in focus} and len(focus) < 3:
                focus.append(
                    {
                        "target_id": related_id,
                        "focus_type": "person" if related_id.startswith("npc_") or related_id.startswith("player_") else "event",
                        "attention_score": memory.importance,
                    }
                )

    return focus[:3]


def choose_candidate_actions(agent_state: AgentState, primary_goal: str) -> list[CandidateAction]:
    candidate_actions = []

    if primary_goal == "avoid_threat":
        candidate_actions.extend(
            [
                CandidateAction(
                    action_type="flee",
                    target_id=None,
                    location_id="village_square",
                    score=90,
                    reason="Threat pressure is high.",
                ),
                CandidateAction(
                    action_type="warn",
                    target_id=highest_priority_sender(agent_state),
                    location_id=None,
                    score=70,
                    reason="Warn nearby allies about danger.",
                ),
            ]
        )
    elif primary_goal == "get_food":
        candidate_actions.extend(
            [
                CandidateAction(
                    action_type="gather",
                    target_id=None,
                    location_id=food_location_for(agent_state),
                    score=80,
                    reason="Food pressure is high.",
                ),
                CandidateAction(
                    action_type="talk",
                    target_id=best_relationship_target(agent_state),
                    location_id=None,
                    score=65,
                    reason="Ask a trusted person for food.",
                ),
            ]
        )
    elif primary_goal == "help_other":
        candidate_actions.append(
            CandidateAction(
                action_type="help",
                target_id=highest_priority_sender(agent_state),
                location_id=None,
                score=78,
                reason="A social request needs attention.",
            )
        )
    elif primary_goal == "investigate":
        candidate_actions.append(
            CandidateAction(
                action_type="investigate",
                target_id=investigation_target(agent_state),
                location_id=agent_state.location_id,
                score=76,
                reason="A credible claim needs investigation.",
            )
        )
    elif primary_goal == "report":
        candidate_actions.append(
            CandidateAction(
                action_type="report",
                target_id="npc_guard_001",
                location_id="village_gate",
                score=84,
                reason="A safety-related claim should be reported to the guard.",
            )
        )
    elif primary_goal == "rest":
        candidate_actions.append(
            CandidateAction(
                action_type="rest",
                target_id=None,
                location_id="inn",
                score=78,
                reason="Energy is low.",
            )
        )
    elif primary_goal == "trade":
        candidate_actions.append(
                CandidateAction(
                    action_type="trade",
                    target_id=best_relationship_target(agent_state),
                    location_id=role_home_location(agent_state),
                    score=72,
                    reason="Trading fits the current role.",
                )
        )
    elif primary_goal == "hunt":
        candidate_actions.append(
            CandidateAction(
                action_type="hunt",
                target_id=None,
                location_id="forest_edge",
                score=72,
                reason="Hunting fits the current role.",
            )
        )
    elif primary_goal == "maintain_relationship":
        candidate_actions.append(
            CandidateAction(
                action_type="talk",
                target_id=best_relationship_target(agent_state),
                location_id=agent_state.location_id,
                score=75,
                reason="Social pressure is high.",
            )
        )
    else:
        candidate_actions.append(
            CandidateAction(
                action_type="patrol",
                target_id=None,
                location_id=agent_state.location_id,
                score=70,
                reason="Maintain local safety and routine.",
            )
        )

    candidate_actions.append(
        CandidateAction(
            action_type="rest",
            target_id=None,
            location_id="inn",
            score=20,
            reason="Low priority fallback action.",
        )
    )

    unique_actions = dedupe_actions(candidate_actions)
    return sorted(unique_actions, key=lambda action: action.score, reverse=True)[:5]


def choose_social_adjustments(agent_state: AgentState) -> list[SocialAdjustment]:
    adjustments = []
    for memory in active_memory_summary(agent_state):
        if "player helped" in memory.summary.lower() and "player_001" in memory.related_ids:
            adjustments.append(
                SocialAdjustment(
                    target_id="player_001",
                    favor_delta=3,
                    trust_delta=5,
                    hostility_delta=0,
                    reason="Helpful player memory increases trust.",
                )
            )
        if "refused" in memory.summary.lower():
            for related_id in memory.related_ids:
                if related_id.startswith("npc_") or related_id.startswith("player_"):
                    adjustments.append(
                        SocialAdjustment(
                            target_id=related_id,
                            favor_delta=-2,
                            trust_delta=-3,
                            hostility_delta=1,
                            reason="Refusal memory lowers social confidence.",
                        )
                    )

    return dedupe_social_adjustments(adjustments)


def has_message_type(agent_state: AgentState, message_type: str) -> bool:
    return any(message.message_type == message_type for message in agent_state.message_queue)


def has_player_utterance_topic(agent_state: AgentState, topic_hint: str) -> bool:
    return any(
        message.message_type == "player_utterance"
        and message.topic_hint == topic_hint
        and (message.credibility is None or message.credibility >= 35)
        for message in agent_state.message_queue
    )


def has_belief_topic(agent_state: AgentState, topic_hint: str, truth_statuses: set[str] | None = None) -> bool:
    allowed_statuses = truth_statuses or {"unverified", "confirmed"}
    return any(
        belief.topic_hint == topic_hint
        and belief.truth_status in allowed_statuses
        and belief.confidence >= 35
        for belief in active_beliefs(agent_state)
    )


def investigation_target(agent_state: AgentState) -> str | None:
    unverified_beliefs = [
        belief
        for belief in active_beliefs(agent_state)
        if belief.truth_status == "unverified" and belief.confidence >= 35
    ]
    if unverified_beliefs:
        belief = max(unverified_beliefs, key=lambda item: (item.confidence, item.created_at_tick))
        return belief.belief_id
    return highest_priority_sender(agent_state)


def has_high_credibility_player_utterance(agent_state: AgentState) -> bool:
    return any(
        message.message_type == "player_utterance"
        and message.topic_hint is not None
        and (message.credibility or 0) >= 55
        for message in agent_state.message_queue
    )


def active_beliefs(agent_state: AgentState):
    current_tick = agent_state.runtime_flags.last_thought_tick
    return [
        belief
        for belief in agent_state.beliefs
        if belief.expires_at_tick is None or belief.expires_at_tick > current_tick
    ]


def has_danger_memory(agent_state: AgentState) -> bool:
    danger_terms = ("monster", "attack", "harmed", "danger")
    return any(any(term in memory.summary.lower() for term in danger_terms) for memory in active_memory_summary(agent_state))


def has_helpful_player_memory(agent_state: AgentState) -> bool:
    return any("player helped" in memory.summary.lower() for memory in active_memory_summary(agent_state))


def active_memory_summary(agent_state: AgentState):
    current_tick = agent_state.runtime_flags.last_thought_tick
    return [
        memory
        for memory in agent_state.memory_summary
        if memory.expires_at_tick is None or memory.expires_at_tick > current_tick
    ]


# TODO: Apply expired memories into slower relationship or learning-bias changes before pruning them.
# 除非用户主动要求解决，否则在代码编写过程中忽略


def highest_priority_sender(agent_state: AgentState) -> str | None:
    if not agent_state.message_queue:
        return None
    return max(agent_state.message_queue, key=lambda message: message.priority).from_id


def best_relationship_target(agent_state: AgentState) -> str | None:
    if not agent_state.relationships:
        return None
    relationship = max(
        agent_state.relationships,
        key=lambda item: item.trust + item.favor - item.hostility,
    )
    return relationship.target_id


def food_location_for(agent_state: AgentState) -> str:
    if agent_state.role == "merchant":
        return "market"
    return "forest_edge"


def role_home_location(agent_state: AgentState) -> str:
    if agent_state.role == "merchant":
        return "market"
    if agent_state.role == "guard":
        return "village_gate"
    if agent_state.role == "hunter":
        return "forest_edge"
    return agent_state.location_id


def dedupe_actions(candidate_actions: list[CandidateAction]) -> list[CandidateAction]:
    seen = set()
    deduped = []
    for action in candidate_actions:
        key = (action.action_type, action.target_id, action.location_id)
        if key not in seen:
            seen.add(key)
            deduped.append(action)
    return deduped


def dedupe_social_adjustments(adjustments: list[SocialAdjustment]) -> list[SocialAdjustment]:
    by_target = {}
    for adjustment in adjustments:
        by_target.setdefault(adjustment.target_id, adjustment)
    return list(by_target.values())
