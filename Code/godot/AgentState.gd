class_name AgentState
extends Resource

@export var npc_id: String = ""
@export var name: String = ""
@export var role: String = ""
@export var location_id: String = ""
@export var base_attributes: Dictionary = {}
@export var personality: Dictionary = {}
@export var needs: Dictionary = {}
@export var relationships: Array[Dictionary] = []
@export var current_task: Dictionary = {}
@export var task_queue: Array[Dictionary] = []
@export var message_queue: Array[Dictionary] = []
@export var memory_summary: Array[Dictionary] = []
@export var beliefs: Array[Dictionary] = []
@export var inventory: Array[Dictionary] = []
@export var learning_bias: Dictionary = {}
@export var runtime_flags: Dictionary = {}


static func from_dictionary(data: Dictionary) -> AgentState:
	var state := AgentState.new()
	state.npc_id = data.get("npc_id", "")
	state.name = data.get("name", "")
	state.role = data.get("role", "")
	state.location_id = data.get("location_id", "")
	state.base_attributes = _dictionary_or_empty(data.get("base_attributes", {}))
	state.personality = _dictionary_or_empty(data.get("personality", {}))
	state.needs = _dictionary_or_empty(data.get("needs", {}))
	state.relationships = _dictionary_array(data.get("relationships", []))
	state.current_task = _dictionary_or_empty(data.get("current_task", {}))
	state.task_queue = _dictionary_array(data.get("task_queue", []))
	state.message_queue = _dictionary_array(data.get("message_queue", []))
	state.memory_summary = _dictionary_array(data.get("memory_summary", []))
	state.beliefs = _dictionary_array(data.get("beliefs", []))
	state.inventory = _dictionary_array(data.get("inventory", []))
	state.learning_bias = _dictionary_or_empty(data.get("learning_bias", {}))
	state.runtime_flags = _dictionary_or_empty(data.get("runtime_flags", {}))
	return state


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
		"npc_id": npc_id,
		"name": name,
		"role": role,
		"location_id": location_id,
		"base_attributes": base_attributes,
		"personality": personality,
		"needs": needs,
		"relationships": relationships,
		"current_task": current_task,
		"task_queue": task_queue,
		"message_queue": message_queue,
		"memory_summary": memory_summary,
		"beliefs": beliefs,
		"inventory": inventory,
		"learning_bias": learning_bias,
		"runtime_flags": runtime_flags,
	}
