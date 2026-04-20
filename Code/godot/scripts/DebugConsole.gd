extends Control

const MONSTER_EVENT_TYPE := "monster_appeared"
const MONSTER_ID := "monster_wolf_001"
const MONSTER_LOCATION := "village_gate"
const SUSPICIOUS_EVENT_TYPE := "suspicious_arrival"
const SUSPICIOUS_ACTOR_ID := "npc_merchant_001"
const SUSPICIOUS_LOCATION := "village_gate"
const SCENARIO_NPC_ID := "npc_guard_001"
const SCENARIO_PLAYER_ID := "player_001"
const SCENARIO_SUSPICIOUS_UTTERANCE := "A suspicious merchant came to the village gate."

const SCENARIO_NONE := ""
const SCENARIO_LIE := "lie"
const SCENARIO_TRUE := "true"
const SCENARIO_RESETTING := "resetting"
const SCENARIO_UTTERANCE := "utterance"
const SCENARIO_EVENT := "event"
const SCENARIO_PLAN := "plan"
const SCENARIO_EXECUTE := "execute"

@onready var tick_label: Label = %TickLabel
@onready var status_label: Label = %StatusLabel
@onready var npc_list: ItemList = %NpcList
@onready var npc_detail: TextEdit = %NpcDetail
@onready var memory_log: TextEdit = %MemoryLog
@onready var belief_log: TextEdit = %BeliefLog
@onready var event_log: TextEdit = %EventLog
@onready var tick_log: TextEdit = %TickLog
@onready var player_utterance_input: LineEdit = %PlayerUtteranceInput

var current_tick := 0
var selected_npc_id := ""
var npc_states: Array[AgentState] = []
var active_scenario := SCENARIO_NONE
var scenario_step := SCENARIO_NONE
var scenario_include_world_event := false
var scenario_lines: Array[String] = []


func _ready() -> void:
	_connect_client()
	_set_status("Ready. Make sure the FastAPI service is running at %s." % ThoughtService.service_base_url)
	_refresh_all()


func _connect_client() -> void:
	ThoughtService.npc_list_received.connect(_on_npc_list_received)
	ThoughtService.npc_list_failed.connect(_on_request_failed.bind("NPC list"))
	ThoughtService.npc_state_received.connect(_on_npc_state_received)
	ThoughtService.npc_state_failed.connect(_on_request_failed.bind("NPC state"))
	ThoughtService.event_ingested.connect(_on_event_ingested)
	ThoughtService.event_failed.connect(_on_request_failed.bind("Event ingest"))
	ThoughtService.plan_applied.connect(_on_plan_applied)
	ThoughtService.plan_failed.connect(_on_request_failed.bind("Plan selected"))
	ThoughtService.task_executed.connect(_on_task_executed)
	ThoughtService.task_execution_failed.connect(_on_request_failed.bind("Execute selected"))
	ThoughtService.event_log_received.connect(_on_event_log_received)
	ThoughtService.event_log_failed.connect(_on_request_failed.bind("Event log"))
	ThoughtService.npc_memories_received.connect(_on_npc_memories_received)
	ThoughtService.npc_memories_failed.connect(_on_request_failed.bind("NPC memories"))
	ThoughtService.npc_beliefs_received.connect(_on_npc_beliefs_received)
	ThoughtService.npc_beliefs_failed.connect(_on_request_failed.bind("NPC beliefs"))
	ThoughtService.simulation_tick_completed.connect(_on_simulation_tick_completed)
	ThoughtService.simulation_tick_failed.connect(_on_request_failed.bind("Simulation tick"))
	ThoughtService.world_reset.connect(_on_world_reset)
	ThoughtService.world_reset_failed.connect(_on_request_failed.bind("World reset"))
	ThoughtService.player_utterance_received.connect(_on_player_utterance_received)
	ThoughtService.player_utterance_failed.connect(_on_request_failed.bind("Player utterance"))


func _refresh_all() -> void:
	ThoughtService.request_all_npc_states()
	ThoughtService.request_event_log()
	if selected_npc_id != "":
		ThoughtService.request_npc_memories(selected_npc_id)
		ThoughtService.request_npc_beliefs(selected_npc_id, true)


func _on_refresh_pressed() -> void:
	_set_status("Refreshing backend state.")
	_refresh_all()


func _on_reset_pressed() -> void:
	_set_status("Resetting world state from seeds.")
	ThoughtService.reset_world_state()


func _on_monster_event_pressed() -> void:
	current_tick += 1
	_update_tick_label()
	var event_id := "evt_debug_monster_%d" % current_tick
	var event := {
		"event_id": event_id,
		"event_type": MONSTER_EVENT_TYPE,
		"actor_id": MONSTER_ID,
		"target_id": null,
		"location_id": MONSTER_LOCATION,
		"payload": {
			"severity": "debug",
			"source": "godot_debug_console",
		},
		"importance": 60,
		"created_at_tick": current_tick,
	}
	_set_status("Submitting event %s." % event_id)
	ThoughtService.ingest_event(event)


func _on_suspicious_event_pressed() -> void:
	current_tick += 1
	_update_tick_label()
	var event_id := _make_suspicious_event_id("debug")
	var event := _build_suspicious_event(event_id, current_tick)
	_set_status("Submitting event %s." % event_id)
	ThoughtService.ingest_event(event)


func _on_lie_scenario_pressed() -> void:
	_start_scenario(SCENARIO_LIE, false)


func _on_true_scenario_pressed() -> void:
	_start_scenario(SCENARIO_TRUE, true)


func _on_plan_selected_pressed() -> void:
	if selected_npc_id == "":
		_set_status("Select an NPC before planning.")
		return
	_set_status("Planning next action for %s." % selected_npc_id)
	ThoughtService.plan_next_action_for_npc(selected_npc_id)


func _on_execute_selected_pressed() -> void:
	if selected_npc_id == "":
		_set_status("Select an NPC before executing.")
		return
	_set_status("Executing current task for %s." % selected_npc_id)
	ThoughtService.execute_current_task_for_npc(selected_npc_id)


func _on_tick_pressed() -> void:
	current_tick += 1
	_update_tick_label()
	_set_status("Running simulation tick %d." % current_tick)
	ThoughtService.run_simulation_tick(current_tick)


func _on_submit_utterance_pressed() -> void:
	if selected_npc_id == "":
		_set_status("Select an NPC before submitting player speech.")
		return
	var content := player_utterance_input.text.strip_edges()
	if content == "":
		_set_status("Player speech is empty.")
		return
	current_tick += 1
	_update_tick_label()
	_set_status("Submitting player speech to %s." % selected_npc_id)
	ThoughtService.submit_player_utterance(selected_npc_id, "player_001", content, current_tick)


func _on_npc_selected(index: int) -> void:
	if index < 0 or index >= npc_states.size():
		return
	selected_npc_id = npc_states[index].npc_id
	_render_npc_detail(npc_states[index])
	ThoughtService.request_npc_memories(selected_npc_id)
	ThoughtService.request_npc_beliefs(selected_npc_id, true)


func _on_npc_list_received(states: Array) -> void:
	npc_states = []
	npc_list.clear()
	for state in states:
		if state is AgentState:
			npc_states.append(state)
			npc_list.add_item("%s  [%s]" % [state.name, state.role])
	if selected_npc_id == "" and npc_states.size() > 0:
		selected_npc_id = npc_states[0].npc_id
		npc_list.select(0)
		_render_npc_detail(npc_states[0])
		ThoughtService.request_npc_memories(selected_npc_id)
		ThoughtService.request_npc_beliefs(selected_npc_id, true)
	elif selected_npc_id != "":
		_select_known_npc()
	_set_status("Loaded %d NPCs." % npc_states.size())


func _on_npc_state_received(state: AgentState) -> void:
	selected_npc_id = state.npc_id
	_render_npc_detail(state)
	ThoughtService.request_npc_memories(selected_npc_id)
	ThoughtService.request_npc_beliefs(selected_npc_id, true)


func _on_event_ingested(result: Dictionary) -> void:
	var recipients: Array = result.get("recipient_npc_ids", [])
	_set_status("Event routed to %d NPCs." % recipients.size())
	if _scenario_is_waiting_for(SCENARIO_EVENT):
		_record_scenario_line("World event stored and routed to %d NPCs." % recipients.size())
		_scenario_plan_selected()
		return
	_refresh_all()


func _on_plan_applied(result: Dictionary) -> void:
	_set_status("Plan applied for %s. mode=%s" % [str(result.get("npc_id", selected_npc_id)), str(result.get("mode", ""))])
	tick_log.text = _format_manual_plan_result(result)
	if _scenario_is_waiting_for(SCENARIO_PLAN):
		_record_scenario_line("Plan selected: %s" % _format_task(result.get("selected_task", {})))
		_scenario_execute_selected()
		return
	_refresh_all()


func _on_task_executed(result: Dictionary) -> void:
	_set_status("Task executed for %s." % str(result.get("npc_id", selected_npc_id)))
	tick_log.text = _format_manual_execution_result(result)
	if _scenario_is_waiting_for(SCENARIO_EXECUTE):
		_finish_scenario(result)
		return
	_refresh_all()


func _on_event_log_received(events: Array) -> void:
	var lines: Array[String] = []
	for event in events:
		if typeof(event) != TYPE_DICTIONARY:
			continue
		lines.append(
			"t%s  %s  actor=%s  target=%s  location=%s  importance=%s" % [
				str(event.get("created_at_tick", "?")),
				str(event.get("event_type", "")),
				str(event.get("actor_id", "-")),
				str(event.get("target_id", "-")),
				str(event.get("location_id", "-")),
				str(event.get("importance", "?")),
			]
		)
	event_log.text = "\n".join(lines)


func _on_npc_memories_received(npc_id: String, memories: Array) -> void:
	if npc_id != selected_npc_id:
		return
	var lines: Array[String] = []
	for memory in memories:
		if typeof(memory) != TYPE_DICTIONARY:
			continue
		lines.append(
			"t%s->%s  [%s] %s" % [
				str(memory.get("created_at_tick", "?")),
				str(memory.get("expires_at_tick", "none")),
				str(memory.get("importance", "?")),
				str(memory.get("summary", "")),
			]
		)
	memory_log.text = "\n".join(lines)


func _on_npc_beliefs_received(npc_id: String, beliefs: Array) -> void:
	if npc_id != selected_npc_id:
		return
	var lines: Array[String] = []
	for belief in beliefs:
		if typeof(belief) != TYPE_DICTIONARY:
			continue
		lines.append(_format_belief_record(belief))
	belief_log.text = "\n\n".join(lines)


func _on_simulation_tick_completed(result: Dictionary) -> void:
	var results: Array = result.get("npc_results", [])
	_set_status("Tick %d updated %d NPCs." % [current_tick, results.size()])
	_render_tick_result(result)
	_refresh_all()


func _on_world_reset(result: Dictionary) -> void:
	current_tick = 0
	selected_npc_id = ""
	_update_tick_label()
	player_utterance_input.text = ""
	tick_log.text = "世界状态已重置。seed NPC 数量：%s" % str(result.get("seeded_npc_count", "?"))
	memory_log.text = ""
	belief_log.text = ""
	event_log.text = ""
	_set_status("World reset complete.")
	if _scenario_is_waiting_for(SCENARIO_RESETTING):
		selected_npc_id = SCENARIO_NPC_ID
		_record_scenario_line("World reset complete. Selected guard NPC.")
		_refresh_all()
		_scenario_submit_utterance()
		return
	_refresh_all()


func _on_request_failed(status_code: int, message: String, label: String) -> void:
	_set_status("%s failed (%d): %s" % [label, status_code, message])
	if active_scenario != SCENARIO_NONE:
		_record_scenario_line("%s failed (%d): %s" % [label, status_code, message])
		_stop_scenario()
		tick_log.text = "\n".join(scenario_lines)


func _on_player_utterance_received(result: Dictionary) -> void:
	var topic := str(result.get("topic_hint", "none"))
	var credibility := str(result.get("credibility", "?"))
	var accepted := str(result.get("accepted", false))
	_set_status("Player speech queued. topic=%s credibility=%s accepted=%s" % [topic, credibility, accepted])
	player_utterance_input.text = ""
	if _scenario_is_waiting_for(SCENARIO_UTTERANCE):
		_record_scenario_line("Player utterance queued as belief claim. topic=%s credibility=%s accepted=%s" % [topic, credibility, accepted])
		if scenario_include_world_event:
			_scenario_submit_world_event()
		else:
			_scenario_plan_selected()
		return
	_refresh_all()


func _select_known_npc() -> void:
	for index in range(npc_states.size()):
		if npc_states[index].npc_id == selected_npc_id:
			npc_list.select(index)
			_render_npc_detail(npc_states[index])
			ThoughtService.request_npc_memories(selected_npc_id)
			ThoughtService.request_npc_beliefs(selected_npc_id, true)
			return


func _render_npc_detail(state: AgentState) -> void:
	var task := state.current_task
	var needs := state.needs
	var lines := [
		"%s (%s)" % [state.name, state.npc_id],
		"role: %s" % state.role,
		"location: %s" % state.location_id,
		"needs: 体力=%s 饥饿压力=%s 安全感=%s 社交压力=%s" % [
			str(needs.get("energy", "?")),
			str(needs.get("hunger", "?")),
			str(needs.get("safety", "?")),
			str(needs.get("social", "?")),
		],
		"current task: %s target=%s location=%s priority=%s interruptible=%s" % [
			str(task.get("task_type", "idle")),
			str(task.get("target_id", "-")),
			str(task.get("location_id", "-")),
			str(task.get("priority", "?")),
			str(task.get("interruptible", "?")),
		],
		"queued tasks: %d" % state.task_queue.size(),
		"active memories: %d" % state.memory_summary.size(),
		"active beliefs: %d" % state.beliefs.size(),
	]
	npc_detail.text = "\n".join(lines)


func _render_tick_result(result: Dictionary) -> void:
	var lines: Array[String] = [
		"第 %s tick 推进结果" % str(result.get("current_tick", current_tick)),
		"",
	]
	var npc_results: Array = result.get("npc_results", [])
	for npc_result in npc_results:
		if typeof(npc_result) != TYPE_DICTIONARY:
			continue
		lines.append(_format_npc_tick_result(npc_result))
		lines.append("")
	tick_log.text = "\n".join(lines)


func _format_npc_tick_result(npc_result: Dictionary) -> String:
	var lines: Array[String] = []
	lines.append("NPC：%s" % str(npc_result.get("npc_id", "")))

	var skipped := str(npc_result.get("skipped_reason", ""))
	if skipped != "":
		lines.append("  本轮跳过：%s" % skipped)
		return "\n".join(lines)

	var passive_needs = npc_result.get("passive_needs", null)
	if typeof(passive_needs) == TYPE_DICTIONARY:
		lines.append("  自然状态变化后：%s" % _format_needs(passive_needs))

	var execution_result = npc_result.get("execution_result", null)
	if typeof(execution_result) == TYPE_DICTIONARY:
		lines.append_array(_format_execution_lines(execution_result, "本轮先执行当前任务"))

	var plan_result = npc_result.get("plan_result", null)
	if typeof(plan_result) == TYPE_DICTIONARY:
		lines.append_array(_format_plan_lines(plan_result, "本轮触发了思考/规划。"))
	else:
		lines.append("  本轮未重新思考：当前任务仍可继续，且未到思考冷却点。")

	return "\n".join(lines)


func _format_manual_plan_result(result: Dictionary) -> String:
	var lines: Array[String] = [
		"Manual Plan Result",
		"NPC：%s" % str(result.get("npc_id", selected_npc_id)),
	]
	lines.append_array(_format_plan_lines(result, "手动触发规划。"))
	return "\n".join(lines)


func _format_manual_execution_result(result: Dictionary) -> String:
	var lines: Array[String] = [
		"Manual Execution Result",
		"NPC：%s" % str(result.get("npc_id", selected_npc_id)),
	]
	lines.append_array(_format_execution_lines(result, "手动执行当前任务"))
	return "\n".join(lines)


func _format_plan_lines(plan_result: Dictionary, header: String) -> Array[String]:
	var lines: Array[String] = [
		"  %s" % header,
		"  规划结果：%s" % _translate_plan_mode(str(plan_result.get("mode", ""))),
		"  规则层理由：%s" % _translate_decision_reason(str(plan_result.get("decision_reason", ""))),
		"  被选中的任务倾向：%s" % _format_task(plan_result.get("selected_task", {})),
	]
	lines.append_array(_format_thought(plan_result.get("thought", {})))
	return lines


func _format_execution_lines(execution_result: Dictionary, task_label: String) -> Array[String]:
	var lines: Array[String] = [
		"  %s：%s" % [task_label, _format_task(execution_result.get("executed_task", {}))],
		"  执行后需求状态：%s" % _format_needs(execution_result.get("needs", {})),
	]
	var verification = execution_result.get("belief_verification", null)
	if typeof(verification) == TYPE_DICTIONARY:
		lines.append_array(_format_belief_verification(verification))
	lines.append("  任务执行后，下一项当前任务变为：%s" % _format_task(execution_result.get("next_current_task", {})))
	return lines


func _format_thought(thought: Variant) -> Array[String]:
	var lines: Array[String] = []
	if typeof(thought) != TYPE_DICTIONARY:
		return lines
	lines.append(
		"  思考倾向：目标=%s 情绪=%s 风险倾向=%s" % [
			_translate_goal(str(thought.get("primary_goal", ""))),
			_translate_emotion(str(thought.get("emotional_state", ""))),
			str(thought.get("risk_attitude", "")),
		]
	)
	lines.append("  打断倾向：%s" % _format_interrupt(thought.get("interrupt_decision", {})))
	var candidates: Array = thought.get("candidate_actions", [])
	if not candidates.is_empty():
		lines.append("  候选行动：")
		for candidate in candidates:
			if typeof(candidate) == TYPE_DICTIONARY:
				lines.append("    - %s" % _format_action(candidate))
	var notes := str(thought.get("notes", ""))
	if notes != "":
		lines.append("  调试备注：%s" % _translate_notes(notes))
	return lines


func _format_task(task: Variant) -> String:
	if typeof(task) != TYPE_DICTIONARY:
		return "none"
	if task.is_empty():
		return "none"
	var task_type := str(task.get("task_type", task.get("action_type", "")))
	return "%s target=%s location=%s priority=%s" % [
		_translate_task_type(task_type),
		str(task.get("target_id", "-")),
		str(task.get("location_id", "-")),
		str(task.get("priority", "?")),
	]


func _format_belief_verification(verification: Dictionary) -> Array[String]:
	var lines: Array[String] = []
	lines.append(
		"  belief verification: %s -> %s confidence=%s evidence=%s" % [
			str(verification.get("belief_id", "")),
			_translate_truth_status(str(verification.get("truth_status", ""))),
			str(verification.get("confidence", "?")),
			_format_id_array(verification.get("evidence_event_ids", [])),
		]
	)
	var follow_up = verification.get("follow_up_task", null)
	if typeof(follow_up) == TYPE_DICTIONARY:
		lines.append("  follow-up task: %s" % _format_task(follow_up))
	var relationship_update = verification.get("relationship_update", null)
	if typeof(relationship_update) == TYPE_DICTIONARY:
		lines.append(
			"  relationship update: target=%s favor=%s trust=%s hostility=%s" % [
				str(relationship_update.get("target_id", "-")),
				str(relationship_update.get("favor_delta", 0)),
				str(relationship_update.get("trust_delta", 0)),
				str(relationship_update.get("hostility_delta", 0)),
			]
		)
	var notes := str(verification.get("notes", ""))
	if notes != "":
		lines.append("  verification notes: %s" % _translate_verification_notes(notes))
	return lines


func _format_belief_record(belief: Dictionary) -> String:
	var lines: Array[String] = [
		"%s  %s  topic=%s confidence=%s" % [
			str(belief.get("belief_id", "")),
			_translate_truth_status(str(belief.get("truth_status", ""))),
			str(belief.get("topic_hint", "none")),
			str(belief.get("confidence", "?")),
		],
		"source=%s:%s  t%s->%s" % [
			str(belief.get("source_type", "")),
			str(belief.get("source_id", "")),
			str(belief.get("created_at_tick", "?")),
			str(belief.get("expires_at_tick", "none")),
		],
		"claim: %s" % str(belief.get("claim", "")),
	]
	return "\n".join(lines)


func _start_scenario(scenario_name: String, include_world_event: bool) -> void:
	active_scenario = scenario_name
	scenario_step = SCENARIO_RESETTING
	scenario_include_world_event = include_world_event
	scenario_lines = [
		"Scenario Runner",
		"Scenario: %s" % _format_scenario_name(scenario_name),
		"Goal: reset -> select guard -> submit suspicious utterance -> optional world_event -> plan -> execute -> refresh.",
		"Rule: player_utterance only creates an unverified npc_belief. Objective truth still requires a world_event.",
		"",
	]
	tick_log.text = "\n".join(scenario_lines)
	_set_status("Running scenario: %s." % _format_scenario_name(scenario_name))
	ThoughtService.reset_world_state()


func _scenario_submit_utterance() -> void:
	scenario_step = SCENARIO_UTTERANCE
	current_tick += 1
	_update_tick_label()
	_record_scenario_line("Submitting suspicious player utterance to %s at tick %d." % [SCENARIO_NPC_ID, current_tick])
	ThoughtService.submit_player_utterance(
		SCENARIO_NPC_ID,
		SCENARIO_PLAYER_ID,
		SCENARIO_SUSPICIOUS_UTTERANCE,
		current_tick
	)


func _scenario_submit_world_event() -> void:
	scenario_step = SCENARIO_EVENT
	current_tick += 1
	_update_tick_label()
	var event_id := _make_suspicious_event_id("scenario")
	_record_scenario_line("Submitting matching suspicious_arrival world_event %s at tick %d." % [event_id, current_tick])
	ThoughtService.ingest_event(_build_suspicious_event(event_id, current_tick))


func _scenario_plan_selected() -> void:
	scenario_step = SCENARIO_PLAN
	_record_scenario_line("Planning selected guard.")
	ThoughtService.plan_next_action_for_npc(SCENARIO_NPC_ID)


func _scenario_execute_selected() -> void:
	scenario_step = SCENARIO_EXECUTE
	_record_scenario_line("Executing selected guard current task.")
	ThoughtService.execute_current_task_for_npc(SCENARIO_NPC_ID)


func _finish_scenario(result: Dictionary) -> void:
	_record_scenario_line("")
	_record_scenario_line("Execution result:")
	scenario_lines.append_array(_format_execution_lines(result, "Scenario execution"))
	var verification = result.get("belief_verification", null)
	if typeof(verification) == TYPE_DICTIONARY:
		_record_scenario_line("")
		_record_scenario_line("Outcome: belief %s, confidence=%s." % [
			str(verification.get("truth_status", "")),
			str(verification.get("confidence", "?")),
		])
		var relationship_update = verification.get("relationship_update", null)
		if typeof(relationship_update) == TYPE_DICTIONARY:
			_record_scenario_line("Player relationship delta: trust=%s favor=%s hostility=%s." % [
				str(relationship_update.get("trust_delta", 0)),
				str(relationship_update.get("favor_delta", 0)),
				str(relationship_update.get("hostility_delta", 0)),
			])
	else:
		_record_scenario_line("")
		_record_scenario_line("Outcome: no belief verification was returned.")
	tick_log.text = "\n".join(scenario_lines)
	_stop_scenario()
	_set_status("Scenario complete. Refreshed beliefs, memories, events, and NPC state.")
	_refresh_all()


func _stop_scenario() -> void:
	active_scenario = SCENARIO_NONE
	scenario_step = SCENARIO_NONE
	scenario_include_world_event = false


func _scenario_is_waiting_for(step: String) -> bool:
	return active_scenario != SCENARIO_NONE and scenario_step == step


func _record_scenario_line(line: String) -> void:
	scenario_lines.append(line)
	tick_log.text = "\n".join(scenario_lines)


func _format_scenario_name(scenario_name: String) -> String:
	match scenario_name:
		SCENARIO_LIE:
			return "A. Player lies -> belief disproven -> player trust drops"
		SCENARIO_TRUE:
			return "B. Player tells truth + world_event exists -> belief confirmed"
		_:
			return scenario_name


func _make_suspicious_event_id(prefix: String) -> String:
	return "evt_%s_suspicious_%d" % [prefix, current_tick]


func _build_suspicious_event(event_id: String, event_tick: int) -> Dictionary:
	var related_ids: Array[String] = [SCENARIO_NPC_ID]
	if selected_npc_id != "" and selected_npc_id != SCENARIO_NPC_ID:
		related_ids.append(selected_npc_id)
	return {
		"event_id": event_id,
		"event_type": SUSPICIOUS_EVENT_TYPE,
		"actor_id": SUSPICIOUS_ACTOR_ID,
		"target_id": null,
		"location_id": SUSPICIOUS_LOCATION,
		"payload": {
			"related_ids": related_ids,
			"source": "godot_debug_console",
		},
		"importance": 55,
		"created_at_tick": event_tick,
	}


func _format_id_array(value: Variant) -> String:
	if typeof(value) != TYPE_ARRAY:
		return "[]"
	var ids: Array[String] = []
	for item in value:
		ids.append(str(item))
	return "[%s]" % ", ".join(ids)


func _format_action(action: Dictionary) -> String:
	var action_type := str(action.get("action_type", ""))
	return "%s target=%s location=%s score=%s reason=%s" % [
		_translate_task_type(action_type),
		str(action.get("target_id", "-")),
		str(action.get("location_id", "-")),
		str(action.get("score", "?")),
		_translate_action_reason(str(action.get("reason", ""))),
	]


func _format_needs(needs: Variant) -> String:
	if typeof(needs) != TYPE_DICTIONARY:
		return "none"
	return "体力=%s 饥饿压力=%s 安全感=%s 社交压力=%s" % [
		str(needs.get("energy", "?")),
		str(needs.get("hunger", "?")),
		str(needs.get("safety", "?")),
		str(needs.get("social", "?")),
	]


func _format_interrupt(interrupt_decision: Variant) -> String:
	if typeof(interrupt_decision) != TYPE_DICTIONARY:
		return "无"
	var should_interrupt := bool(interrupt_decision.get("should_interrupt", false))
	var reason := str(interrupt_decision.get("reason", "none"))
	var priority_delta := str(interrupt_decision.get("priority_delta", 0))
	if should_interrupt:
		return "想打断当前任务，原因=%s，优先级加成=%s" % [
			_translate_interrupt_reason(reason),
			priority_delta,
		]
	return "不主动打断当前任务，原因=%s，优先级加成=%s" % [
		_translate_interrupt_reason(reason),
		priority_delta,
	]


func _translate_plan_mode(mode: String) -> String:
	match mode:
		"interrupted":
			return "立即打断当前任务"
		"queued":
			return "加入任务队列，等待后续执行"
		"unchanged":
			return "已有等价任务，保持不变"
		"none":
			return "没有可执行候选行动"
		_:
			return mode


func _translate_decision_reason(reason: String) -> String:
	match reason:
		"Thought suggested a task but did not request interruption.":
			return "思考只提出了新倾向，但没有要求立刻打断当前任务。"
		"Current task is not interruptible; selected task was queued.":
			return "当前任务不可打断，所以新任务进入队列。"
		"Threat alert is allowed to interrupt immediately.":
			return "威胁警报允许立即打断当前任务。"
		"Urgent need exceeded current task priority by the switch threshold.":
			return "紧急需求的优先级明显超过当前任务，允许切换。"
		"Social request exceeded current task priority by the switch threshold.":
			return "社交请求的优先级明显超过当前任务，允许切换。"
		"System rules rejected interruption because switching benefit was too small.":
			return "系统规则认为切换收益不够大，所以只排队不打断。"
		"No executable candidate action was available.":
			return "没有找到能落地执行的候选行动。"
		_:
			return reason


func _translate_goal(goal: String) -> String:
	match goal:
		"survive":
			return "生存"
		"rest":
			return "休息"
		"get_food":
			return "寻找食物"
		"patrol":
			return "巡逻"
		"trade":
			return "交易"
		"seek_help":
			return "寻求帮助"
		"help_other":
			return "帮助他人"
		"hunt":
			return "狩猎"
		"avoid_threat":
			return "躲避威胁"
		"maintain_relationship":
			return "维持关系"
		"investigate":
			return "调查"
		_:
			return goal


func _translate_emotion(emotion: String) -> String:
	match emotion:
		"calm":
			return "平静"
		"tense":
			return "紧张"
		"afraid":
			return "害怕"
		"angry":
			return "愤怒"
		"curious":
			return "好奇"
		"hopeful":
			return "有希望"
		"frustrated":
			return "受挫"
		_:
			return emotion


func _translate_interrupt_reason(reason: String) -> String:
	match reason:
		"none":
			return "无"
		"urgent_need":
			return "紧急需求"
		"threat_alert":
			return "威胁警报"
		"social_request":
			return "社交请求"
		"better_opportunity":
			return "更好机会"
		"emotional_reaction":
			return "情绪反应"
		_:
			return reason


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


func _translate_task_type(task_type: String) -> String:
	match task_type:
		"idle":
			return "空闲"
		"rest":
			return "休息"
		"move":
			return "移动"
		"talk":
			return "交谈"
		"help":
			return "帮助"
		"patrol":
			return "巡逻"
		"gather":
			return "采集"
		"hunt":
			return "狩猎"
		"flee":
			return "逃离"
		"trade":
			return "交易"
		"investigate":
			return "调查"
		"warn":
			return "警告"
		_:
			return task_type


func _translate_action_reason(reason: String) -> String:
	match reason:
		"Threat pressure is high.":
			return "威胁压力很高。"
		"Warn nearby allies about danger.":
			return "提醒附近盟友注意危险。"
		"Food pressure is high.":
			return "食物压力很高。"
		"Ask a trusted person for food.":
			return "向信任的人寻求食物。"
		"A social request needs attention.":
			return "有社交请求需要回应。"
		"Energy is low.":
			return "体力较低。"
		"Trading fits the current role.":
			return "交易符合当前角色职责。"
		"Hunting fits the current role.":
			return "狩猎符合当前角色职责。"
		"Maintain local safety and routine.":
			return "维持本地安全和日常秩序。"
		"Low priority fallback action.":
			return "低优先级兜底行动。"
		"Social pressure is high.":
			return "社交压力很高。"
		_:
			return reason


func _translate_verification_notes(notes: String) -> String:
	match notes:
		"Investigation found matching objective world events.":
			return "调查找到了匹配的客观世界事件。"
		"Investigation found no matching objective evidence at the checked location.":
			return "调查地点没有发现匹配的客观证据。"
		_:
			return notes


func _translate_notes(notes: String) -> String:
	if notes.contains("route=fallback"):
		return "当前使用低成本伪思考。%s" % notes
	return notes


func _set_status(message: String) -> void:
	status_label.text = message


func _update_tick_label() -> void:
	tick_label.text = "Tick: %d" % current_tick
