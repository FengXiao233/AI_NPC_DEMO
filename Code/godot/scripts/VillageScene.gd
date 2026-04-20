extends Node2D

const PLAYER_ID := "player_001"
const GUARD_ID := "npc_guard_001"
const MERCHANT_ID := "npc_merchant_001"
const HUNTER_ID := "npc_hunter_001"

const EVENT_TYPE_SUSPICIOUS := "suspicious_arrival"
const EVENT_TYPE_MONSTER := "monster_appeared"
const EVENT_TYPE_RESOURCE := "food_shortage"
const EVENT_TYPE_THEFT := "player_stole"
const DEFAULT_EVENT_TYPE := EVENT_TYPE_SUSPICIOUS
const SUSPICIOUS_UTTERANCE := "村口来了一个很可疑的商人。"

const PLAYER_SPEED := 260.0
const NPC_SPEED := 120.0
const INTERACT_DISTANCE := 90.0
const TICKS_PER_DAY := 24
const DAY_START_TICK := 6
const NIGHT_START_TICK := 18

const TASK_COLORS := {
	"idle": Color(0.95, 0.95, 0.95, 1.0),
	"patrol": Color(1.0, 0.72, 0.72, 1.0),
	"investigate": Color(1.0, 0.9, 0.5, 1.0),
	"report": Color(1.0, 0.93, 0.72, 1.0),
	"trade": Color(1.0, 0.94, 0.62, 1.0),
	"hunt": Color(0.7, 1.0, 0.74, 1.0),
	"gather": Color(0.66, 0.94, 0.84, 1.0),
	"flee": Color(1.0, 0.64, 0.64, 1.0),
	"talk": Color(0.82, 0.9, 1.0, 1.0),
	"rest": Color(0.83, 0.84, 1.0, 1.0),
	"help": Color(0.8, 1.0, 0.8, 1.0),
}

var location_points := {
	"village_gate": Vector2(260, 360),
	"market": Vector2(640, 360),
	"forest_edge": Vector2(1010, 360),
	"inn": Vector2(640, 560),
}

var npc_home_points := {
	GUARD_ID: Vector2(520, 600),
	MERCHANT_ID: Vector2(680, 600),
	HUNTER_ID: Vector2(1070, 585),
}

var npc_work_points := {
	GUARD_ID: Vector2(260, 320),
	MERCHANT_ID: Vector2(640, 320),
	HUNTER_ID: Vector2(1010, 320),
}

var npc_zone_offsets := {
	GUARD_ID: Vector2(-32, -18),
	MERCHANT_ID: Vector2(0, 30),
	HUNTER_ID: Vector2(18, 28),
}

var npc_home_labels := {
	GUARD_ID: "守卫宿舍",
	MERCHANT_ID: "商人住处",
	HUNTER_ID: "猎人木屋",
}

var npc_work_labels := {
	GUARD_ID: "岗哨",
	MERCHANT_ID: "摊位",
	HUNTER_ID: "狩猎点",
}

var npc_shift_schedules := {
	GUARD_ID: [
		{"start": 0, "end": 6, "label": "夜间巡岗", "target": "work"},
		{"start": 6, "end": 18, "label": "白天守门", "target": "work"},
		{"start": 18, "end": 24, "label": "傍晚巡岗", "target": "work"},
	],
	MERCHANT_ID: [
		{"start": 0, "end": 6, "label": "睡眠", "target": "home"},
		{"start": 6, "end": 8, "label": "开摊", "target": "work"},
		{"start": 8, "end": 17, "label": "交易", "target": "work"},
		{"start": 17, "end": 20, "label": "收摊回家", "target": "home"},
		{"start": 20, "end": 24, "label": "休息", "target": "home"},
	],
	HUNTER_ID: [
		{"start": 0, "end": 5, "label": "睡眠", "target": "home"},
		{"start": 5, "end": 12, "label": "清晨狩猎", "target": "work"},
		{"start": 12, "end": 15, "label": "市场补给", "target": "market"},
		{"start": 15, "end": 18, "label": "整理猎具", "target": "home"},
		{"start": 18, "end": 24, "label": "休息", "target": "home"},
	],
}

var event_presets := {
	EVENT_TYPE_SUSPICIOUS: {
		"button_text": "可疑人物 / O",
		"location_id": "village_gate",
		"actor_id": MERCHANT_ID,
		"target_id": null,
		"importance": 55,
		"payload": {
			"appearance": "hooded_merchant",
			"claimed_role": "travelling_merchant",
			"behavior": "watching_gate",
			"witness_ids": [GUARD_ID, MERCHANT_ID],
			"risk_hint": "medium",
			"related_ids": [GUARD_ID, MERCHANT_ID],
			"source": "godot_village_scene",
		},
	},
	EVENT_TYPE_MONSTER: {
		"button_text": "Monster at Gate",
		"location_id": "village_gate",
		"actor_id": "monster_wolf_pack_001",
		"target_id": null,
		"importance": 72,
		"payload": {
			"monster_kind": "wolf",
			"monster_id": "monster_wolf_pack_001",
			"count": 3,
			"severity": "medium",
			"entry_point": "north_gate",
			"related_ids": [GUARD_ID, HUNTER_ID, MERCHANT_ID],
			"source": "godot_village_scene",
		},
	},
	EVENT_TYPE_RESOURCE: {
		"button_text": "Resource Shortage",
		"location_id": "market",
		"actor_id": null,
		"target_id": null,
		"importance": 58,
		"payload": {
			"resource": "grain",
			"amount": 20,
			"severity": "high",
			"expected_duration": "2_days",
			"related_ids": [MERCHANT_ID, HUNTER_ID],
			"source": "godot_village_scene",
		},
	},
	EVENT_TYPE_THEFT: {
		"button_text": "Player Stole",
		"location_id": "market",
		"actor_id": PLAYER_ID,
		"target_id": MERCHANT_ID,
		"importance": 75,
		"payload": {
			"item": "healing_potion",
			"value": 35,
			"witness_ids": [MERCHANT_ID, GUARD_ID],
			"related_ids": [MERCHANT_ID, GUARD_ID],
			"source": "godot_village_scene",
		},
	},
}

var fallback_event_catalog := {
	EVENT_TYPE_SUSPICIOUS: {
		"event_type": EVENT_TYPE_SUSPICIOUS,
		"category": "suspicious_activity",
		"routing_roles": ["guard", "merchant"],
		"payload_fields": ["appearance", "claimed_role", "behavior", "witness_ids", "risk_hint"],
		"default_role_responses": [
			{"role": "guard", "task_type": "investigate", "location": "{event.location_id}", "priority": 82, "source": "event"},
			{"role": "merchant", "task_type": "report", "location": "village_gate", "priority": 72, "source": "event"},
		],
	},
	EVENT_TYPE_MONSTER: {
		"event_type": EVENT_TYPE_MONSTER,
		"category": "monster_incursion",
		"routing_roles": ["guard", "hunter", "merchant", "villager"],
		"payload_fields": ["monster_kind", "monster_id", "count", "severity", "entry_point"],
		"default_role_responses": [
			{"role": "guard", "task_type": "patrol", "location": "{event.location_id}", "priority": 86, "source": "event"},
			{"role": "hunter", "task_type": "hunt", "location": "{event.location_id}", "priority": 84, "source": "event"},
			{"role": "merchant", "task_type": "flee", "location": "market", "priority": 72, "source": "event"},
		],
	},
	EVENT_TYPE_RESOURCE: {
		"event_type": EVENT_TYPE_RESOURCE,
		"category": "resource_pressure",
		"routing_roles": ["hunter", "merchant"],
		"payload_fields": ["resource", "amount", "severity", "expected_duration"],
		"default_role_responses": [
			{"role": "merchant", "task_type": "trade", "location": "market", "priority": 78, "source": "event"},
			{"role": "hunter", "task_type": "gather", "location": "forest_edge", "priority": 74, "source": "event"},
		],
	},
	EVENT_TYPE_THEFT: {
		"event_type": EVENT_TYPE_THEFT,
		"category": "player_misconduct",
		"routing_roles": ["guard", "merchant"],
		"payload_fields": ["item", "value", "witness_ids"],
		"default_role_responses": [
			{"role": "guard", "task_type": "investigate", "location": "{event.location_id}", "priority": 84, "source": "event"},
			{"role": "merchant", "task_type": "report", "location": "village_gate", "priority": 74, "source": "event"},
		],
	},
}

var npc_nodes := {}
var npc_tasks := {}
var npc_state_cache := {}
var selected_npc_id := ""
var active_plan_npc_id := GUARD_ID
var current_tick := 0
var pending_plan_execute := false
var pending_investigation_execute := false
var last_verification := {}
var event_catalog := {}
var selected_event_type := DEFAULT_EVENT_TYPE
var latest_event_record := {}
var initialized_npc_positions := {}
var last_plan_result := {}
var last_thought_by_npc := {}
var guard_dialogue_lines: Array[String] = []
var npc_speech_bubbles := {}
var pending_dialogue_npc_id := ""

@onready var player: Node2D = %Player
@onready var guard: Node2D = %Guard
@onready var merchant: Node2D = %Merchant
@onready var hunter: Node2D = %Hunter
@onready var ground: ColorRect = %Ground
@onready var status_label: Label = %StatusLabel
@onready var selected_label: Label = %SelectedLabel
@onready var tick_label: Label = %TickLabel
@onready var dialogue_log: RichTextLabel = %DialogueLog
@onready var speech_input: LineEdit = %SpeechInput
@onready var event_log: RichTextLabel = %EventLog
@onready var event_detail_log: RichTextLabel = %EventDetailLog
@onready var task_log: RichTextLabel = %TaskLog
@onready var thought_log: RichTextLabel = %ThoughtLog
@onready var suspicious_event_button: Button = %SuspiciousEventButton
@onready var monster_event_button: Button = %MonsterEventButton
@onready var resource_event_button: Button = %ResourceEventButton
@onready var theft_event_button: Button = %TheftEventButton


func _ready() -> void:
	npc_nodes = {
		GUARD_ID: guard,
		MERCHANT_ID: merchant,
		HUNTER_ID: hunter,
	}
	_build_npc_speech_bubbles()
	_build_location_overlays()
	speech_input.text = SUSPICIOUS_UTTERANCE
	_configure_event_buttons()
	_connect_client()
	_update_tick_label()
	_update_world_lighting()
	_set_status("村庄切片已加载。WASD 移动，E 说话，O/P/T/R 触发动作。")
	ThoughtService.request_event_catalog()
	ThoughtService.request_all_npc_states()
	ThoughtService.request_event_log(5)
	_render_event_details()
	_render_thought_log()
	_append_guard_dialogue_line("Darin", "我在村口值守。你可以连续告诉我情况；涉及事件的说法会进入 belief 识别。")


func _process(delta: float) -> void:
	_move_player(delta)
	_update_selected_npc()
	_move_npcs(delta)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_E:
			_submit_speech_to_selected()
		elif event.keycode == KEY_R:
			_on_reset_button_pressed()
		elif event.keycode == KEY_P:
			_on_plan_execute_button_pressed()
		elif event.keycode == KEY_O:
			_on_suspicious_event_button_pressed()
		elif event.keycode == KEY_T:
			_on_advance_tick_button_pressed()


func _build_location_overlays() -> void:
	for npc_id in [GUARD_ID, MERCHANT_ID, HUNTER_ID]:
		_add_anchor_marker("%s_home_marker" % npc_id, npc_home_points[npc_id], Color(0.72, 0.82, 1.0, 0.45), npc_home_labels[npc_id])
		_add_anchor_marker("%s_work_marker" % npc_id, npc_work_points[npc_id], Color(1.0, 0.83, 0.45, 0.45), npc_work_labels[npc_id])


func _add_anchor_marker(marker_name: String, anchor_position: Vector2, color: Color, text: String) -> void:
	var marker := ColorRect.new()
	marker.name = marker_name
	marker.position = anchor_position - Vector2(18, 18)
	marker.size = Vector2(36, 36)
	marker.color = color
	add_child(marker)

	var label := Label.new()
	label.name = "%s_label" % marker_name
	label.position = anchor_position + Vector2(-34, 18)
	label.text = text
	add_child(label)


func _configure_event_buttons() -> void:
	suspicious_event_button.text = str(event_presets[EVENT_TYPE_SUSPICIOUS]["button_text"])
	monster_event_button.text = str(event_presets[EVENT_TYPE_MONSTER]["button_text"])
	resource_event_button.text = str(event_presets[EVENT_TYPE_RESOURCE]["button_text"])
	theft_event_button.text = str(event_presets[EVENT_TYPE_THEFT]["button_text"])


func _connect_client() -> void:
	ThoughtService.npc_list_received.connect(_on_npc_list_received)
	ThoughtService.npc_list_failed.connect(_on_request_failed.bind("NPC list"))
	ThoughtService.event_catalog_received.connect(_on_event_catalog_received)
	ThoughtService.event_catalog_failed.connect(_on_request_failed.bind("Event catalog"))
	ThoughtService.event_log_received.connect(_on_event_log_received)
	ThoughtService.event_log_failed.connect(_on_request_failed.bind("Event log"))
	ThoughtService.simulation_tick_completed.connect(_on_simulation_tick_completed)
	ThoughtService.simulation_tick_failed.connect(_on_request_failed.bind("Simulation tick"))
	ThoughtService.world_reset.connect(_on_world_reset)
	ThoughtService.world_reset_failed.connect(_on_request_failed.bind("World reset"))
	ThoughtService.player_utterance_received.connect(_on_player_utterance_received)
	ThoughtService.player_utterance_failed.connect(_on_request_failed.bind("Player utterance"))
	ThoughtService.event_ingested.connect(_on_event_ingested)
	ThoughtService.event_failed.connect(_on_request_failed.bind("Event ingest"))
	ThoughtService.plan_applied.connect(_on_plan_applied)
	ThoughtService.plan_failed.connect(_on_request_failed.bind("Plan"))
	ThoughtService.task_executed.connect(_on_task_executed)
	ThoughtService.task_execution_failed.connect(_on_request_failed.bind("Execute"))


func _move_player(delta: float) -> void:
	var direction := Vector2.ZERO
	if Input.is_key_pressed(KEY_A) or Input.is_key_pressed(KEY_LEFT):
		direction.x -= 1.0
	if Input.is_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT):
		direction.x += 1.0
	if Input.is_key_pressed(KEY_W) or Input.is_key_pressed(KEY_UP):
		direction.y -= 1.0
	if Input.is_key_pressed(KEY_S) or Input.is_key_pressed(KEY_DOWN):
		direction.y += 1.0
	if direction != Vector2.ZERO:
		player.position += direction.normalized() * PLAYER_SPEED * delta
		player.position.x = clamp(player.position.x, 80.0, 1200.0)
		player.position.y = clamp(player.position.y, 150.0, 650.0)


func _update_selected_npc() -> void:
	selected_npc_id = ""
	var nearest_id := ""
	var nearest_distance := INF
	for npc_id in npc_nodes.keys():
		var distance := player.position.distance_to(npc_nodes[npc_id].position)
		if distance < nearest_distance:
			nearest_distance = distance
			nearest_id = npc_id
	if nearest_distance <= INTERACT_DISTANCE:
		selected_npc_id = nearest_id
		selected_label.text = "附近 NPC: %s（按 E 说话）" % _npc_display_name(selected_npc_id)
	else:
		selected_label.text = "附近 NPC: 无"


func _move_npcs(delta: float) -> void:
	for npc_id in npc_nodes.keys():
		var target := _npc_target_position(npc_id)
		var npc: Node2D = npc_nodes[npc_id]
		if npc.position.distance_to(target) <= 3.0:
			continue
		npc.position = npc.position.move_toward(target, NPC_SPEED * delta)


func _npc_target_position(npc_id: String) -> Vector2:
	var state: AgentState = npc_state_cache.get(npc_id, null)
	if state == null:
		return npc_nodes[npc_id].position
	var current_task: Dictionary = state.current_task
	var task_type := str(current_task.get("task_type", "idle"))
	if task_type == "rest":
		return npc_home_points.get(npc_id, npc_nodes[npc_id].position)
	if _uses_shift_target(task_type):
		return _shift_target_position(npc_id, state)
	var location_id := str(current_task.get("location_id", state.location_id))
	var base_position := _position_for_location(npc_id, location_id)
	if task_type == "idle":
		return _shift_target_position(npc_id, state)
	return base_position


func _position_for_location(npc_id: String, location_id: String) -> Vector2:
	if location_id == "inn":
		return npc_home_points.get(npc_id, location_points["inn"])
	if location_points.has(location_id):
		return location_points[location_id] + npc_zone_offsets.get(npc_id, Vector2.ZERO)
	return npc_nodes[npc_id].position


func _rest_or_work_fallback(npc_id: String, state: AgentState) -> Vector2:
	var location_id := state.location_id
	if location_id == "inn":
		return npc_home_points.get(npc_id, location_points["inn"])
	var shift_target := _shift_target_position(npc_id, state)
	if shift_target != npc_nodes[npc_id].position:
		return shift_target
	if location_id == "market" and npc_id == MERCHANT_ID:
		return npc_work_points[npc_id]
	if location_id == "village_gate" and npc_id == GUARD_ID:
		return npc_work_points[npc_id]
	if location_id == "forest_edge" and npc_id == HUNTER_ID:
		return npc_work_points[npc_id]
	return _position_for_location(npc_id, location_id)


func _uses_shift_target(task_type: String) -> bool:
	return task_type in ["idle", "patrol", "trade", "hunt", "gather"]


func _shift_target_position(npc_id: String, state: AgentState) -> Vector2:
	var shift := _current_shift(npc_id)
	var target := str(shift.get("target", "work"))
	match target:
		"home":
			return npc_home_points.get(npc_id, _position_for_location(npc_id, state.location_id))
		"work":
			return npc_work_points.get(npc_id, _position_for_location(npc_id, state.location_id))
		"market":
			return _position_for_location(npc_id, "market")
		"location":
			return _position_for_location(npc_id, state.location_id)
		_:
			return _position_for_location(npc_id, state.location_id)


func _submit_speech_to_selected() -> void:
	if selected_npc_id == "":
		_set_status("先靠近一个 NPC，再提交话语。")
		return
	var content := speech_input.text.strip_edges()
	if content == "":
		_set_status("话语内容为空。")
		return
	var target_npc_id := selected_npc_id
	pending_dialogue_npc_id = target_npc_id
	current_tick += 1
	_update_tick_label()
	if target_npc_id == GUARD_ID:
		_append_guard_dialogue_line("Player", content)
	_show_npc_speech(target_npc_id, "...")
	ThoughtService.submit_player_utterance(target_npc_id, PLAYER_ID, content, current_tick)
	speech_input.clear()
	_set_status("正在把玩家话语提交给 %s。" % _npc_display_name(selected_npc_id))


func _on_submit_button_pressed() -> void:
	_submit_speech_to_selected()


func _on_reset_button_pressed() -> void:
	_set_status("正在重置后端世界状态。")
	ThoughtService.reset_world_state()


func _on_suspicious_event_button_pressed() -> void:
	_submit_event_preset(EVENT_TYPE_SUSPICIOUS)


func _on_monster_event_button_pressed() -> void:
	_submit_event_preset(EVENT_TYPE_MONSTER)


func _on_resource_event_button_pressed() -> void:
	_submit_event_preset(EVENT_TYPE_RESOURCE)


func _on_theft_event_button_pressed() -> void:
	_submit_event_preset(EVENT_TYPE_THEFT)


func _on_advance_tick_button_pressed() -> void:
	current_tick += 1
	_update_tick_label()
	_update_world_lighting()
	_set_status("正在推进时间到 tick %d。" % current_tick)
	ThoughtService.run_simulation_tick(current_tick)


func _submit_event_preset(event_type: String) -> void:
	selected_event_type = event_type
	latest_event_record = {}
	current_tick += 1
	_update_tick_label()
	_render_event_details()
	_set_status("正在创建客观世界事件：%s。" % _event_title(event_type))
	ThoughtService.ingest_event(_build_event_from_preset(event_type))


func _build_event_from_preset(event_type: String) -> Dictionary:
	var preset: Dictionary = event_presets.get(event_type, {})
	return {
		"event_id": "evt_%s_%d" % [event_type, current_tick],
		"event_type": event_type,
		"actor_id": preset.get("actor_id", null),
		"target_id": preset.get("target_id", null),
		"location_id": preset.get("location_id", null),
		"payload": preset.get("payload", {}).duplicate(true),
		"importance": int(preset.get("importance", 50)),
		"created_at_tick": current_tick,
	}


func _on_npc_list_received(states: Array) -> void:
	npc_state_cache.clear()
	for state in states:
		if not state is AgentState:
			continue
		npc_state_cache[state.npc_id] = state
		npc_tasks[state.npc_id] = state.current_task
		_sync_npc_position_from_state(state)
	_update_npc_visuals()
	_render_task_log()


func _sync_npc_position_from_state(state: AgentState) -> void:
	if not npc_nodes.has(state.npc_id):
		return
	var npc := npc_nodes[state.npc_id] as Node2D
	var desired := _rest_or_work_fallback(state.npc_id, state)
	var has_initialized := bool(initialized_npc_positions.get(state.npc_id, false))
	if not has_initialized:
		npc.position = desired
		initialized_npc_positions[state.npc_id] = true


func _on_event_catalog_received(entries: Array) -> void:
	event_catalog.clear()
	for entry in entries:
		if typeof(entry) == TYPE_DICTIONARY:
			event_catalog[str(entry.get("event_type", ""))] = entry
	_render_event_details()


func _on_event_log_received(events: Array) -> void:
	if not events.is_empty() and typeof(events[0]) == TYPE_DICTIONARY:
		latest_event_record = events[0]
		if selected_event_type == "":
			selected_event_type = str(latest_event_record.get("event_type", DEFAULT_EVENT_TYPE))
	_render_event_details()


func _on_simulation_tick_completed(result: Dictionary) -> void:
	var summary: Array[String] = []
	for npc_result in result.get("npc_results", []):
		if typeof(npc_result) != TYPE_DICTIONARY:
			continue
		var npc_id := str(npc_result.get("npc_id", ""))
		var execution_result = npc_result.get("execution_result", null)
		var plan_result = npc_result.get("plan_result", null)
		if typeof(execution_result) == TYPE_DICTIONARY:
			var next_task: Dictionary = execution_result.get("next_current_task", {})
			npc_tasks[npc_id] = next_task
			summary.append("%s: 执行后 -> %s" % [_npc_display_name(npc_id), _format_task(next_task)])
		if typeof(plan_result) == TYPE_DICTIONARY:
			_cache_plan_result(plan_result)
			var selected_task: Dictionary = plan_result.get("selected_task", {})
			if not selected_task.is_empty():
				summary.append("%s: 新规划 -> %s" % [_npc_display_name(npc_id), _format_task(selected_task)])
	event_log.text = "时间推进到 tick %d\n%s" % [int(result.get("current_tick", current_tick)), "\n".join(summary)]
	_set_status("时间推进完成。")
	_render_thought_log()
	ThoughtService.request_all_npc_states()
	ThoughtService.request_event_log(5)


func _on_world_reset(result: Dictionary) -> void:
	current_tick = 0
	pending_plan_execute = false
	pending_investigation_execute = false
	last_verification = {}
	latest_event_record = {}
	last_plan_result = {}
	last_thought_by_npc.clear()
	guard_dialogue_lines.clear()
	initialized_npc_positions.clear()
	_update_tick_label()
	_update_world_lighting()
	event_log.text = "世界已重置。初始 NPC 数量：%s" % str(result.get("seeded_npc_count", "?"))
	_set_status("世界重置完成。")
	ThoughtService.request_event_catalog()
	ThoughtService.request_all_npc_states()
	ThoughtService.request_event_log(5)
	_render_thought_log()
	_append_guard_dialogue_line("Darin", "世界状态已重置。我继续在村口值守。")


func _on_player_utterance_received(result: Dictionary) -> void:
	var belief = result.get("belief", null)
	var line := "玩家话语进入 NPC 消息队列。\n主题=%s 可信度=%s" % [
		_translate_topic(str(result.get("topic_hint", "none"))),
		str(result.get("credibility", "?")),
	]
	if typeof(belief) == TYPE_DICTIONARY:
		line += "\n生成主观 belief：%s 状态=%s" % [
			str(belief.get("belief_id", "")),
			_translate_truth_status(str(belief.get("truth_status", ""))),
		]
	var forwarded_to: Array = result.get("forwarded_to_npc_ids", [])
	if not forwarded_to.is_empty():
		line += "\n转告目标：%s" % _format_array(forwarded_to)
	var interpretation: Dictionary = result.get("interpretation", {})
	if not interpretation.is_empty():
		line += "\n输入理解：source=%s type=%s reason=%s" % [
			str(interpretation.get("source", "rule")),
			str(interpretation.get("utterance_type", "")),
			str(interpretation.get("reason", "")),
		]
	event_log.text = line
	_show_npc_speech(str(result.get("npc_id", "")), str(result.get("npc_reply", "")))
	pending_dialogue_npc_id = ""
	if str(result.get("npc_id", "")) == GUARD_ID:
		_append_guard_dialogue_line("Darin", _guard_reply_from_utterance_result(result))
	if not forwarded_to.is_empty():
		_set_status("玩家话语触发了商人上报，后续由守卫验证。")
	else:
		_set_status("玩家话语只生成主观 belief，不直接创建 world_event。")
	ThoughtService.request_all_npc_states()


func _on_event_ingested(result: Dictionary) -> void:
	event_log.text = "客观事件已保存并路由给 NPC：%s" % _format_array(result.get("recipient_npc_ids", []))
	_set_status("客观事件已写入后端。")
	ThoughtService.request_all_npc_states()
	ThoughtService.request_event_log(5)


func _on_plan_execute_button_pressed() -> void:
	active_plan_npc_id = selected_npc_id if selected_npc_id != "" else GUARD_ID
	pending_plan_execute = true
	pending_investigation_execute = false
	_set_status("正在为 %s 规划下一步行动。" % _npc_display_name(active_plan_npc_id))
	ThoughtService.plan_next_action_for_npc(active_plan_npc_id)


func _on_plan_applied(result: Dictionary) -> void:
	_cache_plan_result(result)
	npc_tasks[str(result.get("npc_id", GUARD_ID))] = result.get("selected_task", {})
	_render_task_log()
	_render_thought_log()
	if pending_plan_execute:
		_set_status("规划完成，正在执行 %s 的当前任务。" % _npc_display_name(active_plan_npc_id))
		ThoughtService.execute_current_task_for_npc(active_plan_npc_id)
	else:
		_set_status("规划结果已应用。")


func _on_task_executed(result: Dictionary) -> void:
	pending_plan_execute = false
	npc_tasks[str(result.get("npc_id", GUARD_ID))] = result.get("next_current_task", {})
	var verification = result.get("belief_verification", null)
	if typeof(verification) == TYPE_DICTIONARY:
		pending_investigation_execute = false
		last_verification = verification
		event_log.text = "belief 验证结果：%s -> %s\n客观证据：%s\n%s" % [
			str(verification.get("belief_id", "")),
			_translate_truth_status(str(verification.get("truth_status", ""))),
			_format_array(verification.get("evidence_event_ids", [])),
			_format_relationship_update(verification.get("relationship_update", null)),
		]
	else:
		event_log.text = "任务已执行，本次没有触发 belief 验证。"
	var report_result = result.get("report_result", null)
	if typeof(report_result) == TYPE_DICTIONARY:
		event_log.text = "报告已送达：%s -> %s\n主题=%s\n守卫形成待验证 belief：%s" % [
			_npc_display_name(str(report_result.get("from_npc_id", ""))),
			_npc_display_name(str(report_result.get("to_npc_id", ""))),
			_translate_topic(str(report_result.get("topic_hint", ""))),
			str(report_result.get("target_belief_id", "")),
		]
	_render_task_log()
	_render_thought_log()
	if _should_execute_followup_investigation(result):
		pending_investigation_execute = true
		_set_status("调查任务已成为当前任务，继续执行以拿到验证结果。")
		ThoughtService.execute_current_task_for_npc(str(result.get("npc_id", active_plan_npc_id)))
		return
	_set_status("NPC 任务已执行，场景目标已更新。")
	ThoughtService.request_all_npc_states()


func _on_request_failed(status_code: int, message: String, label: String) -> void:
	if label == "Player utterance" and pending_dialogue_npc_id != "":
		_show_npc_speech(pending_dialogue_npc_id, "")
		pending_dialogue_npc_id = ""
	if label == "Event catalog" and status_code == 404:
		event_catalog = fallback_event_catalog.duplicate(true)
		_render_event_details()
		_set_status("后端未提供 /event-catalog，已切换到本地事件目录。")
		event_log.text = "后端还是旧版路由，事件目录改用 Godot 内置 fallback。"
		return
	pending_plan_execute = false
	pending_investigation_execute = false
	_set_status("%s 请求失败（%d）。" % [label, status_code])
	event_log.text = "%s 请求失败（%d）：%s" % [label, status_code, message]


func _cache_plan_result(result: Dictionary) -> void:
	var npc_id := str(result.get("npc_id", active_plan_npc_id))
	last_plan_result = result.duplicate(true)
	var thought = result.get("thought", null)
	if typeof(thought) == TYPE_DICTIONARY:
		last_thought_by_npc[npc_id] = thought


func _build_npc_speech_bubbles() -> void:
	for npc_id in npc_nodes.keys():
		var npc: Node2D = npc_nodes[npc_id]
		var bubble := Label.new()
		bubble.name = "SpeechBubble"
		bubble.position = Vector2(-90, -74)
		bubble.size = Vector2(180, 42)
		bubble.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		bubble.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		bubble.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		bubble.text = ""
		npc.add_child(bubble)
		npc_speech_bubbles[npc_id] = bubble


func _show_npc_speech(npc_id: String, text: String) -> void:
	if not npc_speech_bubbles.has(npc_id):
		return
	var bubble: Label = npc_speech_bubbles[npc_id]
	bubble.text = text.strip_edges()


func _append_guard_dialogue_line(speaker: String, text: String) -> void:
	guard_dialogue_lines.append("%s: %s" % [speaker, text])
	while guard_dialogue_lines.size() > 8:
		guard_dialogue_lines.pop_front()
	_render_guard_dialogue_log()


func _render_guard_dialogue_log() -> void:
	if dialogue_log == null:
		return
	if guard_dialogue_lines.is_empty():
		dialogue_log.text = "靠近守卫后按 E，可以连续和 Darin 对话。事件类话语会由模型识别并生成 belief。"
		return
	dialogue_log.text = "\n".join(guard_dialogue_lines)


func _guard_reply_from_utterance_result(result: Dictionary) -> String:
	var npc_reply := str(result.get("npc_reply", "")).strip_edges()
	if npc_reply != "":
		return npc_reply
	var belief = result.get("belief", null)
	var interpretation: Dictionary = result.get("interpretation", {})
	var source := str(interpretation.get("source", "rule"))
	var topic := _translate_topic(str(result.get("topic_hint", "none")))
	if typeof(belief) == TYPE_DICTIONARY:
		return "我会把这当作待验证情报。topic=%s source=%s belief=%s" % [
			topic,
			source,
			str(belief.get("belief_id", "")),
		]
	if str(result.get("topic_hint", "")) != "":
		return "我听到了，但可信度还不足以形成 belief。topic=%s source=%s" % [topic, source]
	return "我听到了。这暂时不像可验证事件，不会生成 belief。source=%s" % source


func _should_execute_followup_investigation(result: Dictionary) -> bool:
	if pending_investigation_execute:
		return false
	var verification = result.get("belief_verification", null)
	if typeof(verification) == TYPE_DICTIONARY:
		return false
	var next_task = result.get("next_current_task", null)
	if typeof(next_task) != TYPE_DICTIONARY:
		return false
	return (
		str(next_task.get("task_type", "")) == "investigate"
		and str(next_task.get("target_id", "")).begins_with("belief_")
	)


func _update_npc_visuals() -> void:
	for npc_id in npc_nodes.keys():
		var npc: Node2D = npc_nodes[npc_id]
		var body := npc.get_node("Body") as Polygon2D
		var state: AgentState = npc_state_cache.get(npc_id, null)
		if state == null:
			body.modulate = Color(1, 1, 1, 1)
			npc.scale = Vector2.ONE
			continue
		var task_type := str(state.current_task.get("task_type", "idle"))
		body.modulate = TASK_COLORS.get(task_type, Color(1, 1, 1, 1))
		var has_event_queue := _find_first_event_task(state) != null
		npc.scale = Vector2.ONE * (1.08 if has_event_queue else 1.0)


func _render_task_log() -> void:
	var lines: Array[String] = []
	lines.append("操作：WASD 移动，E 说话，O 可疑人物，P 规划并执行，T 推进时间，R 重置。")
	lines.append("当前时段：%s" % _time_of_day_label())
	lines.append("半透明蓝块是住所，黄块是工作地。NPC 颜色表示当前任务。")
	lines.append("")
	for npc_id in [GUARD_ID, MERCHANT_ID, HUNTER_ID]:
		var state: AgentState = npc_state_cache.get(npc_id, null)
		lines.append("%s" % _npc_display_name(npc_id))
		lines.append("  住所：%s" % _vector_label(npc_home_points[npc_id]))
		lines.append("  工作地：%s" % _vector_label(npc_work_points[npc_id]))
		lines.append("  班次：%s -> %s" % [_current_shift_label(npc_id), _current_shift_target_label(npc_id)])
		lines.append("  当前：%s" % _format_task(npc_tasks.get(npc_id, {})))
		if state != null:
			lines.append("  后端 location_id：%s" % _translate_location(state.location_id))
			var event_task = _find_first_event_task(state)
			if event_task != null:
				lines.append("  事件队列：%s" % _format_task(event_task))
			else:
				lines.append("  事件队列：无")
	if not last_verification.is_empty():
		lines.append("")
		lines.append("最近验证：%s 置信度=%s" % [
			_translate_truth_status(str(last_verification.get("truth_status", ""))),
			str(last_verification.get("confidence", "?")),
		])
	task_log.text = "\n".join(lines)


func _render_thought_log() -> void:
	var lines: Array[String] = []
	lines.append("Thought / Planner")
	if last_plan_result.is_empty():
		lines.append("尚无规划结果。靠近 NPC 后按 P，或推进时间触发 NPC 自动规划。")
		lines.append("这里会显示：模型/规则思考 -> 候选行动 -> ActionPlanner 裁决。")
		thought_log.text = "\n".join(lines)
		return

	var npc_id := str(last_plan_result.get("npc_id", active_plan_npc_id))
	var thought: Dictionary = last_plan_result.get("thought", {})
	lines.append("NPC: %s" % _npc_display_name(npc_id))
	lines.append("Thought source: %s" % _thought_source_label(thought))
	lines.append("Goal: %s  Emotion: %s" % [
		str(thought.get("primary_goal", "")),
		str(thought.get("emotional_state", "")),
	])
	lines.append("Interrupt: %s" % _format_interrupt_decision(thought.get("interrupt_decision", {})))
	lines.append("Top action: %s" % _format_action(_top_candidate_action(thought)))
	lines.append("Planner selected: %s" % _format_task(last_plan_result.get("selected_task", {})))
	lines.append("Planner mode: %s" % str(last_plan_result.get("mode", "")))
	lines.append("Planner reason: %s" % str(last_plan_result.get("decision_reason", "")))
	var notes := str(thought.get("notes", ""))
	if notes != "":
		lines.append("Notes: %s" % notes)
	thought_log.text = "\n".join(lines)


func _thought_source_label(thought: Dictionary) -> String:
	var notes := str(thought.get("notes", ""))
	if notes.contains("route=model") or notes.contains("source=llm_thought"):
		return "LLM thought"
	if notes.contains("route=fallback"):
		return "Rule fallback"
	return "Unknown"


func _top_candidate_action(thought: Dictionary) -> Dictionary:
	var candidates: Array = thought.get("candidate_actions", [])
	for candidate in candidates:
		if typeof(candidate) == TYPE_DICTIONARY:
			return candidate
	return {}


func _format_action(action: Variant) -> String:
	if typeof(action) != TYPE_DICTIONARY or action.is_empty():
		return "无"
	return "%s target=%s location=%s score=%s reason=%s" % [
		_translate_task_type(str(action.get("action_type", ""))),
		str(action.get("target_id", "-")),
		_translate_location(str(action.get("location_id", "-"))),
		str(action.get("score", "?")),
		str(action.get("reason", "")),
	]


func _format_interrupt_decision(value: Variant) -> String:
	if typeof(value) != TYPE_DICTIONARY:
		return "none"
	return "should=%s reason=%s delta=%s" % [
		str(value.get("should_interrupt", false)),
		str(value.get("reason", "none")),
		str(value.get("priority_delta", 0)),
	]


func _render_event_details() -> void:
	var event_type := selected_event_type if selected_event_type != "" else DEFAULT_EVENT_TYPE
	var lines: Array[String] = []
	lines.append("事件控制台")
	lines.append("当前 tick：%d" % current_tick)
	lines.append("当前时段：%s" % _time_of_day_label())
	lines.append("当前预设：%s" % _event_title(event_type))
	var catalog_entry: Dictionary = event_catalog.get(event_type, {})
	if not catalog_entry.is_empty():
		lines.append("类别：%s" % str(catalog_entry.get("category", "misc")))
		lines.append("路由职业：%s" % _format_array(catalog_entry.get("routing_roles", [])))
		lines.append("payload_fields：%s" % _format_array(catalog_entry.get("payload_fields", [])))
		lines.append("默认职业任务：")
		var responses: Array = catalog_entry.get("default_role_responses", [])
		for response in responses:
			if typeof(response) != TYPE_DICTIONARY:
				continue
			lines.append(
				"  %s -> %s @ %s p=%s src=%s" % [
					str(response.get("role", "?")),
					_translate_task_type(str(response.get("task_type", ""))),
					str(response.get("location", "-")),
					str(response.get("priority", "?")),
					str(response.get("source", "?")),
				]
			)
	else:
		lines.append("事件目录尚未返回。")
	var preset: Dictionary = event_presets.get(event_type, {})
	if not preset.is_empty():
		lines.append("")
		lines.append("待提交 payload：%s" % JSON.stringify(preset.get("payload", {})))
	if not latest_event_record.is_empty() and str(latest_event_record.get("event_type", "")) == event_type:
		lines.append("")
		lines.append("最近入库 payload：%s" % JSON.stringify(latest_event_record.get("payload", {})))
	event_detail_log.text = "\n".join(lines)


func _find_first_event_task(state: AgentState):
	for task in state.task_queue:
		if str(task.get("source", "")) == "event":
			return task
	return null


func _format_task(task: Variant) -> String:
	if typeof(task) != TYPE_DICTIONARY or task.is_empty():
		return "无"
	var pieces: Array[String] = []
	pieces.append(_translate_task_type(str(task.get("task_type", "idle"))))
	pieces.append("目标=%s" % str(task.get("target_id", "-")))
	pieces.append("地点=%s" % _translate_location(str(task.get("location_id", "-"))))
	pieces.append("优先级=%s" % str(task.get("priority", "?")))
	if task.has("source"):
		pieces.append("source=%s" % str(task.get("source", "")))
	return " ".join(pieces)


func _format_array(value: Variant) -> String:
	if typeof(value) != TYPE_ARRAY:
		return "[]"
	var items: Array[String] = []
	for item in value:
		items.append(str(item))
	return "[%s]" % ", ".join(items)


func _format_relationship_update(value: Variant) -> String:
	if typeof(value) != TYPE_DICTIONARY:
		return "关系变化：无"
	return "关系变化：对象=%s trust=%s favor=%s hostility=%s" % [
		str(value.get("target_id", "-")),
		str(value.get("trust_delta", 0)),
		str(value.get("favor_delta", 0)),
		str(value.get("hostility_delta", 0)),
	]


func _vector_label(point: Vector2) -> String:
	return "(%d, %d)" % [int(point.x), int(point.y)]


func _npc_display_name(npc_id: String) -> String:
	match npc_id:
		GUARD_ID:
			return "Darin / 守卫"
		MERCHANT_ID:
			return "Mira / 商人"
		HUNTER_ID:
			return "Aren / 猎人"
		_:
			return npc_id


func _event_title(event_type: String) -> String:
	match event_type:
		EVENT_TYPE_SUSPICIOUS:
			return "可疑人物到来"
		EVENT_TYPE_MONSTER:
			return "Monster at Gate"
		EVENT_TYPE_RESOURCE:
			return "Resource Shortage"
		EVENT_TYPE_THEFT:
			return "Player Stole"
		_:
			return event_type


func _translate_task_type(task_type: String) -> String:
	match task_type:
		"investigate":
			return "调查"
		"report":
			return "报告"
		"patrol":
			return "巡逻"
		"trade":
			return "交易"
		"hunt":
			return "狩猎"
		"gather":
			return "采集"
		"rest":
			return "休息"
		"talk":
			return "交谈"
		"flee":
			return "逃离"
		"help":
			return "帮助"
		"idle":
			return "空闲"
		_:
			return task_type


func _translate_location(location_id: String) -> String:
	match location_id:
		"village_gate":
			return "村口"
		"market":
			return "市场"
		"forest_edge":
			return "森林边缘"
		"inn":
			return "旅店"
		_:
			return location_id


func _translate_truth_status(status: String) -> String:
	match status:
		"unverified":
			return "未验证"
		"confirmed":
			return "已确认"
		"disproven":
			return "已证伪"
		_:
			return status


func _translate_topic(topic: String) -> String:
	match topic:
		"suspicious_arrival":
			return "可疑人物到来"
		"monster_threat":
			return "怪物威胁"
		"food_shortage":
			return "食物短缺"
		"help_request":
			return "求助"
		_:
			return topic


func _current_hour() -> int:
	return current_tick % TICKS_PER_DAY


func _is_daytime() -> bool:
	var hour := _current_hour()
	return hour >= DAY_START_TICK and hour < NIGHT_START_TICK


func _prefers_home_at_current_time(npc_id: String) -> bool:
	if npc_id == GUARD_ID:
		return false
	return not _is_daytime()


func _current_shift(npc_id: String) -> Dictionary:
	var hour := _current_hour()
	for shift in npc_shift_schedules.get(npc_id, []):
		if hour >= int(shift.get("start", 0)) and hour < int(shift.get("end", 0)):
			return shift
	return {"label": "默认工作", "target": "work"}


func _current_shift_label(npc_id: String) -> String:
	return str(_current_shift(npc_id).get("label", "默认工作"))


func _current_shift_target_label(npc_id: String) -> String:
	match str(_current_shift(npc_id).get("target", "work")):
		"home":
			return "住所"
		"work":
			return "工作地"
		"market":
			return "市场"
		"location":
			return "当前位置"
		_:
			return str(_current_shift(npc_id).get("target", "work"))


func _time_of_day_label() -> String:
	var hour := _current_hour()
	if hour < DAY_START_TICK:
		return "凌晨 %02d:00" % hour
	if hour < 12:
		return "上午 %02d:00" % hour
	if hour < NIGHT_START_TICK:
		return "下午 %02d:00" % hour
	return "夜间 %02d:00" % hour


func _update_tick_label() -> void:
	tick_label.text = "Tick: %d  %s" % [current_tick, _time_of_day_label()]


func _update_world_lighting() -> void:
	if _is_daytime():
		ground.color = Color(0.188235, 0.294118, 0.196078, 1)
	else:
		ground.color = Color(0.105882, 0.14902, 0.188235, 1)


func _set_status(message: String) -> void:
	status_label.text = message
