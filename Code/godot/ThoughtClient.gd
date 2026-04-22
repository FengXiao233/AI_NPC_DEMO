class_name ThoughtClient
extends Node

signal thought_received(result: ThoughtResult)
signal thought_failed(status_code: int, message: String)
signal event_ingested(result: Dictionary)
signal event_failed(status_code: int, message: String)
signal plan_applied(result: Dictionary)
signal plan_failed(status_code: int, message: String)
signal task_executed(result: Dictionary)
signal task_execution_failed(status_code: int, message: String)
signal simulation_tick_completed(result: Dictionary)
signal simulation_tick_failed(status_code: int, message: String)
signal npc_state_received(state: AgentState)
signal npc_state_failed(status_code: int, message: String)
signal npc_list_received(states: Array)
signal npc_list_failed(status_code: int, message: String)
signal event_catalog_received(entries: Array)
signal event_catalog_failed(status_code: int, message: String)
signal event_log_received(events: Array)
signal event_log_failed(status_code: int, message: String)
signal npc_memories_received(npc_id: String, memories: Array)
signal npc_memories_failed(status_code: int, message: String)
signal npc_beliefs_received(npc_id: String, beliefs: Array)
signal npc_beliefs_failed(status_code: int, message: String)
signal npc_inventory_received(npc_id: String, inventory: Array)
signal npc_inventory_failed(status_code: int, message: String)
signal village_warehouse_received(items: Array)
signal village_warehouse_failed(status_code: int, message: String)
signal warehouse_transactions_received(transactions: Array)
signal warehouse_transactions_failed(status_code: int, message: String)
signal production_orders_received(orders: Array)
signal production_orders_failed(status_code: int, message: String)
signal dialogue_history_received(npc_id: String, history: Dictionary)
signal dialogue_history_failed(status_code: int, message: String)
signal world_resources_received(resources: Array)
signal world_resources_failed(status_code: int, message: String)
signal world_entities_received(entities: Array)
signal world_entities_failed(status_code: int, message: String)
signal world_reset(result: Dictionary)
signal world_reset_failed(status_code: int, message: String)
signal player_utterance_received(result: Dictionary)
signal player_utterance_failed(status_code: int, message: String)

@export var service_base_url: String = "http://127.0.0.1:8000"

var _thought_request: HTTPRequest
var _event_request: HTTPRequest
var _plan_request: HTTPRequest
var _execute_task_request: HTTPRequest
var _simulation_tick_request: HTTPRequest
var _npc_state_request: HTTPRequest
var _npc_list_request: HTTPRequest
var _event_catalog_request: HTTPRequest
var _event_log_request: HTTPRequest
var _npc_memories_request: HTTPRequest
var _npc_beliefs_request: HTTPRequest
var _npc_inventory_request: HTTPRequest
var _village_warehouse_request: HTTPRequest
var _warehouse_transactions_request: HTTPRequest
var _production_orders_request: HTTPRequest
var _dialogue_history_request: HTTPRequest
var _world_resources_request: HTTPRequest
var _world_entities_request: HTTPRequest
var _reset_world_request: HTTPRequest
var _player_utterance_request: HTTPRequest
var _pending_memory_npc_id: String = ""
var _pending_belief_npc_id: String = ""
var _pending_inventory_npc_id: String = ""
var _pending_dialogue_history_npc_id: String = ""


func _ready() -> void:
	_thought_request = HTTPRequest.new()
	_event_request = HTTPRequest.new()
	_plan_request = HTTPRequest.new()
	_execute_task_request = HTTPRequest.new()
	_simulation_tick_request = HTTPRequest.new()
	_npc_state_request = HTTPRequest.new()
	_npc_list_request = HTTPRequest.new()
	_event_catalog_request = HTTPRequest.new()
	_event_log_request = HTTPRequest.new()
	_npc_memories_request = HTTPRequest.new()
	_npc_beliefs_request = HTTPRequest.new()
	_npc_inventory_request = HTTPRequest.new()
	_village_warehouse_request = HTTPRequest.new()
	_warehouse_transactions_request = HTTPRequest.new()
	_production_orders_request = HTTPRequest.new()
	_dialogue_history_request = HTTPRequest.new()
	_world_resources_request = HTTPRequest.new()
	_world_entities_request = HTTPRequest.new()
	_reset_world_request = HTTPRequest.new()
	_player_utterance_request = HTTPRequest.new()
	add_child(_thought_request)
	add_child(_event_request)
	add_child(_plan_request)
	add_child(_execute_task_request)
	add_child(_simulation_tick_request)
	add_child(_npc_state_request)
	add_child(_npc_list_request)
	add_child(_event_catalog_request)
	add_child(_event_log_request)
	add_child(_npc_memories_request)
	add_child(_npc_beliefs_request)
	add_child(_npc_inventory_request)
	add_child(_village_warehouse_request)
	add_child(_warehouse_transactions_request)
	add_child(_production_orders_request)
	add_child(_dialogue_history_request)
	add_child(_world_resources_request)
	add_child(_world_entities_request)
	add_child(_reset_world_request)
	add_child(_player_utterance_request)
	_thought_request.request_completed.connect(_on_thought_request_completed)
	_event_request.request_completed.connect(_on_event_request_completed)
	_plan_request.request_completed.connect(_on_plan_request_completed)
	_execute_task_request.request_completed.connect(_on_execute_task_request_completed)
	_simulation_tick_request.request_completed.connect(_on_simulation_tick_request_completed)
	_npc_state_request.request_completed.connect(_on_npc_state_request_completed)
	_npc_list_request.request_completed.connect(_on_npc_list_request_completed)
	_event_catalog_request.request_completed.connect(_on_event_catalog_request_completed)
	_event_log_request.request_completed.connect(_on_event_log_request_completed)
	_npc_memories_request.request_completed.connect(_on_npc_memories_request_completed)
	_npc_beliefs_request.request_completed.connect(_on_npc_beliefs_request_completed)
	_npc_inventory_request.request_completed.connect(_on_npc_inventory_request_completed)
	_village_warehouse_request.request_completed.connect(_on_village_warehouse_request_completed)
	_warehouse_transactions_request.request_completed.connect(_on_warehouse_transactions_request_completed)
	_production_orders_request.request_completed.connect(_on_production_orders_request_completed)
	_dialogue_history_request.request_completed.connect(_on_dialogue_history_request_completed)
	_world_resources_request.request_completed.connect(_on_world_resources_request_completed)
	_world_entities_request.request_completed.connect(_on_world_entities_request_completed)
	_reset_world_request.request_completed.connect(_on_reset_world_request_completed)
	_player_utterance_request.request_completed.connect(_on_player_utterance_request_completed)


func request_thought(agent_state: AgentState) -> Error:
	var body := JSON.stringify(agent_state.to_dictionary())
	var headers := ["Content-Type: application/json"]
	return _thought_request.request("%s/thought" % service_base_url, headers, HTTPClient.METHOD_POST, body)


func request_thought_for_npc(npc_id: String) -> Error:
	return _thought_request.request("%s/npcs/%s/thought" % [service_base_url, npc_id])


func request_npc_state(npc_id: String) -> Error:
	return _npc_state_request.request("%s/npcs/%s" % [service_base_url, npc_id])


func request_all_npc_states() -> Error:
	return _npc_list_request.request("%s/npcs" % service_base_url)


func request_event_catalog() -> Error:
	return _event_catalog_request.request("%s/event-catalog" % service_base_url)


func request_event_log(limit: int = 50) -> Error:
	return _event_log_request.request("%s/events?limit=%d" % [service_base_url, limit])


func request_npc_memories(npc_id: String, include_expired: bool = false, limit: int = 50) -> Error:
	_pending_memory_npc_id = npc_id
	var expired_flag := "true" if include_expired else "false"
	return _npc_memories_request.request(
		"%s/npcs/%s/memories?include_expired=%s&limit=%d" % [
			service_base_url,
			npc_id,
			expired_flag,
			limit,
		]
	)


func request_npc_beliefs(npc_id: String, include_expired: bool = false, limit: int = 50) -> Error:
	_pending_belief_npc_id = npc_id
	var expired_flag := "true" if include_expired else "false"
	return _npc_beliefs_request.request(
		"%s/npcs/%s/beliefs?include_expired=%s&limit=%d" % [
			service_base_url,
			npc_id,
			expired_flag,
			limit,
		]
	)


func request_npc_inventory(npc_id: String) -> Error:
	_pending_inventory_npc_id = npc_id
	return _npc_inventory_request.request("%s/npcs/%s/inventory" % [service_base_url, npc_id])


func request_village_warehouse() -> Error:
	return _village_warehouse_request.request("%s/village/warehouse" % service_base_url)


func request_warehouse_transactions(limit: int = 8) -> Error:
	return _warehouse_transactions_request.request("%s/village/warehouse/transactions?limit=%d" % [service_base_url, limit])


func request_production_orders(include_completed: bool = false) -> Error:
	var completed_flag := "true" if include_completed else "false"
	return _production_orders_request.request("%s/village/production-orders?include_completed=%s" % [service_base_url, completed_flag])


func request_dialogue_history(npc_id: String, speaker_id: String = "player_001", recent_turn_limit: int = 6) -> Error:
	_pending_dialogue_history_npc_id = npc_id
	return _dialogue_history_request.request(
		"%s/npcs/%s/dialogue-history?speaker_id=%s&recent_turn_limit=%d" % [
			service_base_url,
			npc_id,
			speaker_id,
			recent_turn_limit,
		]
	)


func request_world_resources(location_id: String = "") -> Error:
	var url := "%s/world/resources" % service_base_url
	if location_id != "":
		url += "?location_id=%s" % location_id
	return _world_resources_request.request(url)


func request_world_entities(location_id: String = "") -> Error:
	var url := "%s/world/entities" % service_base_url
	if location_id != "":
		url += "?location_id=%s" % location_id
	return _world_entities_request.request(url)


func reset_world_state() -> Error:
	return _reset_world_request.request("%s/debug/reset" % service_base_url, [], HTTPClient.METHOD_POST)


func submit_player_utterance(npc_id: String, speaker_id: String, content: String, current_tick: int) -> Error:
	var body := JSON.stringify({
		"speaker_id": speaker_id,
		"content": content,
		"created_at_tick": current_tick,
	})
	var headers := ["Content-Type: application/json"]
	return _player_utterance_request.request(
		"%s/npcs/%s/utterances" % [service_base_url, npc_id],
		headers,
		HTTPClient.METHOD_POST,
		body
	)


func ingest_event(event: Dictionary) -> Error:
	var body := JSON.stringify(event)
	var headers := ["Content-Type: application/json"]
	return _event_request.request("%s/events" % service_base_url, headers, HTTPClient.METHOD_POST, body)


func plan_next_action_for_npc(npc_id: String) -> Error:
	return _plan_request.request("%s/npcs/%s/plan" % [service_base_url, npc_id], [], HTTPClient.METHOD_POST)


func execute_current_task_for_npc(npc_id: String) -> Error:
	return _execute_task_request.request("%s/npcs/%s/execute-task" % [service_base_url, npc_id], [], HTTPClient.METHOD_POST)


func run_simulation_tick(current_tick: int, npc_ids: Array[String] = [], enable_world_updates: bool = true) -> Error:
	var body := JSON.stringify({
		"current_tick": current_tick,
		"npc_ids": npc_ids,
		"include_profile": true,
		"enable_world_updates": enable_world_updates,
	})
	var headers := ["Content-Type: application/json"]
	return _simulation_tick_request.request("%s/simulation/tick" % service_base_url, headers, HTTPClient.METHOD_POST, body)


func _on_thought_request_completed(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if response_code < 200 or response_code >= 300 or typeof(parsed) != TYPE_DICTIONARY:
		thought_failed.emit(response_code, body.get_string_from_utf8())
		return

	thought_received.emit(ThoughtResult.from_dictionary(parsed))


func _on_event_request_completed(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if response_code < 200 or response_code >= 300 or typeof(parsed) != TYPE_DICTIONARY:
		event_failed.emit(response_code, body.get_string_from_utf8())
		return

	event_ingested.emit(parsed)


func _on_plan_request_completed(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if response_code < 200 or response_code >= 300 or typeof(parsed) != TYPE_DICTIONARY:
		plan_failed.emit(response_code, body.get_string_from_utf8())
		return

	plan_applied.emit(parsed)


func _on_execute_task_request_completed(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if response_code < 200 or response_code >= 300 or typeof(parsed) != TYPE_DICTIONARY:
		task_execution_failed.emit(response_code, body.get_string_from_utf8())
		return

	task_executed.emit(parsed)


func _on_simulation_tick_request_completed(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if response_code < 200 or response_code >= 300 or typeof(parsed) != TYPE_DICTIONARY:
		simulation_tick_failed.emit(response_code, body.get_string_from_utf8())
		return

	simulation_tick_completed.emit(parsed)


func _on_npc_state_request_completed(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if response_code < 200 or response_code >= 300 or typeof(parsed) != TYPE_DICTIONARY:
		npc_state_failed.emit(response_code, body.get_string_from_utf8())
		return

	npc_state_received.emit(AgentState.from_dictionary(parsed))


func _on_npc_list_request_completed(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if response_code < 200 or response_code >= 300 or typeof(parsed) != TYPE_ARRAY:
		npc_list_failed.emit(response_code, body.get_string_from_utf8())
		return

	var states: Array[AgentState] = []
	for item in parsed:
		if typeof(item) == TYPE_DICTIONARY:
			states.append(AgentState.from_dictionary(item))
	npc_list_received.emit(states)


func _on_event_catalog_request_completed(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if response_code < 200 or response_code >= 300 or typeof(parsed) != TYPE_ARRAY:
		event_catalog_failed.emit(response_code, body.get_string_from_utf8())
		return

	event_catalog_received.emit(parsed)


func _on_event_log_request_completed(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if response_code < 200 or response_code >= 300 or typeof(parsed) != TYPE_ARRAY:
		event_log_failed.emit(response_code, body.get_string_from_utf8())
		return

	event_log_received.emit(parsed)


func _on_npc_memories_request_completed(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if response_code < 200 or response_code >= 300 or typeof(parsed) != TYPE_ARRAY:
		npc_memories_failed.emit(response_code, body.get_string_from_utf8())
		return

	npc_memories_received.emit(_pending_memory_npc_id, parsed)


func _on_npc_beliefs_request_completed(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if response_code < 200 or response_code >= 300 or typeof(parsed) != TYPE_ARRAY:
		npc_beliefs_failed.emit(response_code, body.get_string_from_utf8())
		return

	npc_beliefs_received.emit(_pending_belief_npc_id, parsed)


func _on_npc_inventory_request_completed(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if response_code < 200 or response_code >= 300 or typeof(parsed) != TYPE_ARRAY:
		npc_inventory_failed.emit(response_code, body.get_string_from_utf8())
		return

	npc_inventory_received.emit(_pending_inventory_npc_id, parsed)


func _on_village_warehouse_request_completed(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if response_code < 200 or response_code >= 300 or typeof(parsed) != TYPE_ARRAY:
		village_warehouse_failed.emit(response_code, body.get_string_from_utf8())
		return

	village_warehouse_received.emit(parsed)


func _on_warehouse_transactions_request_completed(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if response_code < 200 or response_code >= 300 or typeof(parsed) != TYPE_ARRAY:
		warehouse_transactions_failed.emit(response_code, body.get_string_from_utf8())
		return

	warehouse_transactions_received.emit(parsed)


func _on_production_orders_request_completed(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if response_code < 200 or response_code >= 300 or typeof(parsed) != TYPE_ARRAY:
		production_orders_failed.emit(response_code, body.get_string_from_utf8())
		return

	production_orders_received.emit(parsed)


func _on_dialogue_history_request_completed(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if response_code < 200 or response_code >= 300 or typeof(parsed) != TYPE_DICTIONARY:
		dialogue_history_failed.emit(response_code, body.get_string_from_utf8())
		return

	dialogue_history_received.emit(_pending_dialogue_history_npc_id, parsed)


func _on_world_resources_request_completed(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if response_code < 200 or response_code >= 300 or typeof(parsed) != TYPE_ARRAY:
		world_resources_failed.emit(response_code, body.get_string_from_utf8())
		return

	world_resources_received.emit(parsed)


func _on_world_entities_request_completed(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if response_code < 200 or response_code >= 300 or typeof(parsed) != TYPE_ARRAY:
		world_entities_failed.emit(response_code, body.get_string_from_utf8())
		return

	world_entities_received.emit(parsed)


func _on_reset_world_request_completed(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if response_code < 200 or response_code >= 300 or typeof(parsed) != TYPE_DICTIONARY:
		world_reset_failed.emit(response_code, body.get_string_from_utf8())
		return

	world_reset.emit(parsed)


func _on_player_utterance_request_completed(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if response_code < 200 or response_code >= 300 or typeof(parsed) != TYPE_DICTIONARY:
		player_utterance_failed.emit(response_code, body.get_string_from_utf8())
		return

	player_utterance_received.emit(parsed)
