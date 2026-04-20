class_name ThoughtResult
extends Resource

@export var primary_goal: String = ""
@export var emotional_state: String = ""
@export var risk_attitude: int = 0
@export var interrupt_decision: Dictionary = {}
@export var target_focus: Array[Dictionary] = []
@export var candidate_actions: Array[Dictionary] = []
@export var social_adjustments: Array[Dictionary] = []
@export var notes: String = ""


static func from_dictionary(data: Dictionary) -> ThoughtResult:
	var result := ThoughtResult.new()
	result.primary_goal = data.get("primary_goal", "")
	result.emotional_state = data.get("emotional_state", "")
	result.risk_attitude = data.get("risk_attitude", 0)
	result.interrupt_decision = _dictionary_or_empty(data.get("interrupt_decision", {}))
	result.target_focus = _dictionary_array(data.get("target_focus", []))
	result.candidate_actions = _dictionary_array(data.get("candidate_actions", []))
	result.social_adjustments = _dictionary_array(data.get("social_adjustments", []))
	result.notes = data.get("notes", "")
	return result


static func _dictionary_or_empty(value: Variant) -> Dictionary:
	if typeof(value) == TYPE_DICTIONARY:
		return value
	return {}


static func _dictionary_array(value: Variant) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	if typeof(value) != TYPE_ARRAY:
		return result
	for item in value:
		if typeof(item) == TYPE_DICTIONARY:
			result.append(item)
	return result


func to_dictionary() -> Dictionary:
	return {
		"primary_goal": primary_goal,
		"emotional_state": emotional_state,
		"risk_attitude": risk_attitude,
		"interrupt_decision": interrupt_decision,
		"target_focus": target_focus,
		"candidate_actions": candidate_actions,
		"social_adjustments": social_adjustments,
		"notes": notes,
	}
