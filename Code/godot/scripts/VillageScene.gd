extends Node2D

const PLAYER_ID := "player_001"
const PLAYER_SPEED := 340.0
const NPC_VISUAL_SPEED := 185.0
const WORLD_WIDTH := 1344.0
const WORLD_HEIGHT := 1080.0
const SPEECH_BUBBLE_DURATION := 10.0
const NPC_INTERACTION_DISTANCE := 120.0
const HOTSPOT_INTERACTION_DISTANCE := 118.0

const AREA_VILLAGE_ENTRANCE := "village_entrance"
const AREA_VILLAGE_SQUARE := "village_square"
const AREA_VILLAGE_MARKET := "village_market"
const AREA_HUNTING_FOREST := "hunting_forest"
const AREA_VILLAGE_REST_AREA := "village_rest_area"

const NPC_GUARD := "npc_guard_001"
const NPC_MERCHANT := "npc_merchant_001"
const NPC_HUNTER := "npc_hunter_001"
const NPC_FARMER := "npc_farmer_001"
const NPC_BLACKSMITH := "npc_blacksmith_001"
const NPC_PHYSICIAN := "npc_physician_001"
const NPC_VILLAGE_CHIEF := "npc_village_chief_001"

const AREA_BY_LOCATION := {
	"village_gate": AREA_VILLAGE_ENTRANCE,
	"village_square": AREA_VILLAGE_SQUARE,
	"market": AREA_VILLAGE_MARKET,
	"forest_edge": AREA_HUNTING_FOREST,
	"inn": AREA_VILLAGE_REST_AREA,
}

const LOCATION_BY_AREA := {
	AREA_VILLAGE_ENTRANCE: "village_gate",
	AREA_VILLAGE_SQUARE: "village_square",
	AREA_VILLAGE_MARKET: "market",
	AREA_HUNTING_FOREST: "forest_edge",
	AREA_VILLAGE_REST_AREA: "inn",
}

const NPC_NAMES := {
	NPC_GUARD: "Darin 守卫",
	NPC_MERCHANT: "Mira 商人",
	NPC_HUNTER: "Aren 猎人",
	NPC_FARMER: "Lysa 农夫",
	NPC_BLACKSMITH: "Bran 铁匠",
	NPC_PHYSICIAN: "Sena 医师",
	NPC_VILLAGE_CHIEF: "Orlen 村长",
}

const SPRITE_SHEET := preload("res://assets/characters/ittybitty_npc_6.png")
const SPRITE_FRAME_SIZE := Vector2i(16, 16)
const SPRITE_GROUP_SIZE := Vector2i(48, 64)
const SPRITE_SCALE := Vector2(4.0, 4.0)
const PLAYER_ACTOR_ID := "player"
const MONSTER_ACTOR_ID := "monster"
const TRAVELER_ACTOR_ID := "traveler"
const ROLE_SPRITES := {
	PLAYER_ACTOR_ID: Vector2i(2, 0),
	NPC_HUNTER: Vector2i(0, 0),
	NPC_MERCHANT: Vector2i(3, 0),
	NPC_GUARD: Vector2i(4, 0),
	NPC_FARMER: Vector2i(1, 0),
	NPC_BLACKSMITH: Vector2i(2, 0),
	NPC_PHYSICIAN: Vector2i(1, 1),
	NPC_VILLAGE_CHIEF: Vector2i(2, 1),
	MONSTER_ACTOR_ID: Vector2i(0, 1),
	TRAVELER_ACTOR_ID: Vector2i(3, 0),
}

const AREA_META := {
	AREA_VILLAGE_ENTRANCE: {
		"name": "村庄入口",
		"subtitle": "城门、哨塔和水渠在这里，适合展示安保与来客检查。",
		"background": preload("res://assets/backgrounds/01_village_entrance_2048x1152.png"),
	},
	AREA_VILLAGE_SQUARE: {
		"name": "村庄广场",
		"subtitle": "喷泉和公告厅是公共交流中心，适合观察人群流动。",
		"background": preload("res://assets/backgrounds/02_village_square_2048x1152.png"),
	},
	AREA_VILLAGE_MARKET: {
		"name": "村庄集市",
		"subtitle": "摊位和货箱对应交易、短缺与偷窃等事件。",
		"background": preload("res://assets/backgrounds/03_village_market_2048x1152.png"),
	},
	AREA_HUNTING_FOREST: {
		"name": "狩猎森林",
		"subtitle": "猎人营地和兽道连接巡逻、狩猎与怪物事件。",
		"background": preload("res://assets/backgrounds/04_hunting_forest_2048x1152.png"),
	},
	AREA_VILLAGE_REST_AREA: {
		"name": "村庄休息处",
		"subtitle": "营火、小屋与瀑布平台适合休整和连续对话展示。",
		"background": preload("res://assets/backgrounds/05_village_rest_area_2048x1152.png"),
	},
}

const AREA_SPAWN_POINTS := {
	AREA_VILLAGE_ENTRANCE: Vector2(460, 780),
	AREA_VILLAGE_SQUARE: Vector2(655, 800),
	AREA_VILLAGE_MARKET: Vector2(640, 820),
	AREA_HUNTING_FOREST: Vector2(635, 835),
	AREA_VILLAGE_REST_AREA: Vector2(625, 815),
}

const TRANSITION_SPAWN_POINTS := {
	"village_entrance->village_square": Vector2(640, 560),
	"village_square->village_entrance": Vector2(580, 570),
	"village_square->village_market": Vector2(930, 615),
	"village_market->village_square": Vector2(710, 845),
	"village_market->hunting_forest": Vector2(965, 360),
	"hunting_forest->village_market": Vector2(980, 560),
	"village_square->village_rest_area": Vector2(390, 720),
	"village_rest_area->village_square": Vector2(360, 650),
	"hunting_forest->village_rest_area": Vector2(320, 610),
	"village_rest_area->hunting_forest": Vector2(840, 290),
}

const NPC_AREA_POSITIONS := {
	NPC_GUARD: {
		AREA_VILLAGE_ENTRANCE: Vector2(720, 640),
		AREA_VILLAGE_SQUARE: Vector2(1030, 645),
		AREA_VILLAGE_MARKET: Vector2(1030, 720),
	},
	NPC_MERCHANT: {
		AREA_VILLAGE_MARKET: Vector2(810, 650),
		AREA_VILLAGE_SQUARE: Vector2(980, 660),
		AREA_VILLAGE_REST_AREA: Vector2(1020, 710),
	},
	NPC_HUNTER: {
		AREA_HUNTING_FOREST: Vector2(900, 610),
		AREA_VILLAGE_MARKET: Vector2(1080, 710),
		AREA_VILLAGE_REST_AREA: Vector2(980, 760),
	},
	NPC_FARMER: {
		AREA_VILLAGE_SQUARE: Vector2(520, 700),
		AREA_VILLAGE_MARKET: Vector2(480, 800),
	},
	NPC_BLACKSMITH: {
		AREA_VILLAGE_SQUARE: Vector2(610, 705),
		AREA_VILLAGE_ENTRANCE: Vector2(880, 660),
	},
	NPC_PHYSICIAN: {
		AREA_VILLAGE_SQUARE: Vector2(700, 710),
		AREA_VILLAGE_REST_AREA: Vector2(820, 735),
	},
	NPC_VILLAGE_CHIEF: {
		AREA_VILLAGE_SQUARE: Vector2(790, 690),
		AREA_VILLAGE_ENTRANCE: Vector2(840, 620),
		AREA_VILLAGE_MARKET: Vector2(910, 690),
	},
}

const AREA_HOTSPOTS := {
	AREA_VILLAGE_ENTRANCE: [
		{"label": "进入广场", "kind": "transition", "target_area": AREA_VILLAGE_SQUARE, "pos": Vector2(580, 470), "detail": "穿过城门后进入广场。"},
		{"label": "守卫哨塔", "kind": "focus_npc", "npc_id": NPC_GUARD, "pos": Vector2(910, 310), "detail": "守卫在这里观察来客与出入口。"},
		{"label": "水渠磨坊", "kind": "inspect", "pos": Vector2(1080, 470), "detail": "这里可承接供水、民生或事故类事件。"},
		{"label": "村外小路", "kind": "inspect", "pos": Vector2(180, 860), "detail": "这里通向村外，可作为后续地图扩展入口。"},
	],
	AREA_VILLAGE_SQUARE: [
		{"label": "回到入口", "kind": "transition", "target_area": AREA_VILLAGE_ENTRANCE, "pos": Vector2(640, 455), "detail": "从这里可以回到村庄入口。"},
		{"label": "前往集市", "kind": "transition", "target_area": AREA_VILLAGE_MARKET, "pos": Vector2(1020, 520), "detail": "沿街巷前往商铺最密集的区域。"},
		{"label": "前往休息处", "kind": "transition", "target_area": AREA_VILLAGE_REST_AREA, "pos": Vector2(320, 660), "detail": "沿树荫与长椅区前往休息处。"},
		{"label": "中央喷泉", "kind": "inspect", "pos": Vector2(650, 575), "detail": "喷泉适合展示闲聊、传闻与公共聚集。"},
		{"label": "公告大厅", "kind": "inspect", "pos": Vector2(780, 260), "detail": "这里可承接任务发布与公共事件说明。"},
	],
	AREA_VILLAGE_MARKET: [
		{"label": "商人摊位", "kind": "focus_npc", "npc_id": NPC_MERCHANT, "pos": Vector2(760, 470), "detail": "商人在这里交易，也适合展示市场传闻。"},
		{"label": "补给货箱", "kind": "inspect", "pos": Vector2(530, 840), "detail": "这里适合展示资源短缺、偷窃与物资调度。"},
		{"label": "回到广场", "kind": "transition", "target_area": AREA_VILLAGE_SQUARE, "pos": Vector2(640, 930), "detail": "从集市下方回到广场。"},
		{"label": "前往森林", "kind": "transition", "target_area": AREA_HUNTING_FOREST, "pos": Vector2(1060, 260), "detail": "从集市旁林道进入狩猎森林。"},
	],
	AREA_HUNTING_FOREST: [
		{"label": "猎人营地", "kind": "focus_npc", "npc_id": NPC_HUNTER, "pos": Vector2(860, 390), "detail": "猎人会在这里巡查、休整和讨论林地情况。"},
		{"label": "林间兽道", "kind": "inspect", "pos": Vector2(700, 720), "detail": "兽道可承接怪物出现、追踪与调查。"},
		{"label": "去休息处", "kind": "transition", "target_area": AREA_VILLAGE_REST_AREA, "pos": Vector2(250, 520), "detail": "沿营火旁小路返回休息处。"},
		{"label": "回到集市", "kind": "transition", "target_area": AREA_VILLAGE_MARKET, "pos": Vector2(1110, 520), "detail": "沿林边棚屋可回到集市。"},
	],
	AREA_VILLAGE_REST_AREA: [
		{"label": "休息小屋", "kind": "rest", "pos": Vector2(1030, 360), "detail": "这里适合承接休息、恢复与夜间驻留。"},
		{"label": "营火区", "kind": "rest", "pos": Vector2(690, 760), "detail": "营火适合慢节奏对话、总结与队伍集合。"},
		{"label": "回到广场", "kind": "transition", "target_area": AREA_VILLAGE_SQUARE, "pos": Vector2(250, 590), "detail": "从木桌区可快速回到广场。"},
		{"label": "进入森林", "kind": "transition", "target_area": AREA_HUNTING_FOREST, "pos": Vector2(860, 180), "detail": "从瀑布旁路口进入森林。"},
	],
}

@onready var player: Node2D = %Player
@onready var guard: Node2D = %Guard
@onready var merchant: Node2D = %Merchant
@onready var hunter: Node2D = %Hunter
@onready var tick_label: Label = %TickLabel
@onready var status_label: Label = %StatusLabel
@onready var selected_label: Label = %SelectedLabel
@onready var dialogue_log: RichTextLabel = %DialogueLog
@onready var speech_input: LineEdit = %SpeechInput
@onready var thought_log: RichTextLabel = %ThoughtLog
@onready var task_log: RichTextLabel = %TaskLog
@onready var event_log: RichTextLabel = %EventLog
@onready var event_detail_log: RichTextLabel = %EventDetailLog
@onready var auto_tick_button: Button = %AutoTickButton
@onready var auto_tick_interval_spin_box: SpinBox = %AutoTickIntervalSpinBox
@onready var auto_tick_timer: Timer = %AutoTickTimer

var current_tick := 0
var current_area_id := AREA_VILLAGE_ENTRANCE
var selected_npc_id := ""
var target_npc_id := ""
var pending_dialogue_npc_id := ""
var pending_plan_then_execute := false
var tick_request_in_flight := false
var auto_tick_enabled := false

var npc_nodes: Dictionary = {}
var npc_states_by_id: Dictionary = {}
var npc_visual_areas: Dictionary = {}
var npc_target_areas: Dictionary = {}
var npc_travel_states: Dictionary = {}
var dialogue_history_by_npc: Dictionary = {}
var npc_name_labels: Dictionary = {}
var npc_reply_labels: Dictionary = {}
var npc_prompt_labels: Dictionary = {}
var speech_hide_timers: Dictionary = {}
var hotspot_markers: Array[Dictionary] = []
var current_hotspot_index := -1
var current_interactable_type := ""
var actor_sprite_nodes: Dictionary = {}
var actor_last_direction: Dictionary = {}
var monster_node: Node2D
var monster_area_id := AREA_HUNTING_FOREST
var resource_layer: Control
var entity_layer: Node2D
var resource_marker_nodes: Dictionary = {}
var dynamic_entity_nodes: Dictionary = {}
var world_resources_by_id: Dictionary = {}
var world_entities_by_id: Dictionary = {}
var npc_inventory_by_id: Dictionary = {}
var village_warehouse: Array = []
var production_orders: Array = []
var warehouse_transactions: Array = []
var last_economy_summary := ""

var world_background: TextureRect
var hotspot_layer: Control
var player_bounds := Rect2(Vector2(40, 120), Vector2(WORLD_WIDTH - 80, WORLD_HEIGHT - 180))


func _ready() -> void:
	npc_nodes = {
		NPC_GUARD: guard,
		NPC_MERCHANT: merchant,
		NPC_HUNTER: hunter,
	}
	_hide_legacy_scenery()
	_setup_monster_node()
	_setup_world_layers()
	_setup_actor_sprites()
	_setup_npc_overlays()
	_initialize_npc_scene_state()
	_connect_client_signals()
	_connect_ui_signals()
	_apply_static_ui_text()
	_switch_area(AREA_VILLAGE_ENTRANCE, "初始展示村庄入口。")
	_update_tick_label()
	_update_auto_tick_button()
	_set_status("正在读取后端状态。")
	_refresh_backend_state()


func _process(delta: float) -> void:
	_move_player(delta)
	_advance_npc_travel(delta)
	_refresh_interaction_state()


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		match event.keycode:
			KEY_E:
				_interact_with_current_target()
			KEY_T:
				_on_advance_tick_button_pressed()
			KEY_O:
				_on_suspicious_event_button_pressed()
			KEY_P:
				_on_plan_execute_button_pressed()
			KEY_R:
				_on_reset_button_pressed()


func _hide_legacy_scenery() -> void:
	var keep := {
		"VillageScene": true,
		"WorldBanner": true,
		"Player": true,
		"Guard": true,
		"Merchant": true,
		"Hunter": true,
		"UI": true,
		"AutoTickTimer": true,
	}
	for child in get_children():
		if child is CanvasLayer:
			continue
		if keep.has(child.name):
			continue
		if child == auto_tick_timer:
			continue
		if child is CanvasItem:
			child.visible = false


func _setup_world_layers() -> void:
	world_background = TextureRect.new()
	world_background.position = Vector2.ZERO
	world_background.size = Vector2(WORLD_WIDTH, WORLD_HEIGHT)
	world_background.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	world_background.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	world_background.mouse_filter = Control.MOUSE_FILTER_IGNORE
	world_background.z_index = -50
	add_child(world_background)
	move_child(world_background, 0)

	hotspot_layer = Control.new()
	hotspot_layer.position = Vector2.ZERO
	hotspot_layer.size = Vector2(WORLD_WIDTH, WORLD_HEIGHT)
	hotspot_layer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	$UI.add_child(hotspot_layer)

	resource_layer = Control.new()
	resource_layer.position = Vector2.ZERO
	resource_layer.size = Vector2(WORLD_WIDTH, WORLD_HEIGHT)
	resource_layer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(resource_layer)
	move_child(resource_layer, get_children().find($UI) - 2)

	entity_layer = Node2D.new()
	entity_layer.name = "DynamicEntities"
	add_child(entity_layer)
	move_child(entity_layer, get_children().find($UI) - 1)


func _setup_monster_node() -> void:
	monster_node = Node2D.new()
	monster_node.name = "Monster"
	monster_node.position = Vector2(760, 610)
	var shadow := Polygon2D.new()
	shadow.color = Color(0, 0, 0, 0.22)
	shadow.polygon = PackedVector2Array([Vector2(-20, 10), Vector2(0, 16), Vector2(20, 10), Vector2(0, 4)])
	monster_node.add_child(shadow)
	var label := Label.new()
	label.name = "Label"
	label.offset_left = -34.0
	label.offset_top = 20.0
	label.offset_right = 52.0
	label.offset_bottom = 45.0
	label.text = "Monster"
	label.add_theme_color_override("font_color", Color(0.972549, 0.964706, 0.886275, 1))
	label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.55))
	label.add_theme_constant_override("outline_size", 4)
	monster_node.add_child(label)
	add_child(monster_node)
	move_child(monster_node, get_children().find($UI) - 1)


func _setup_actor_sprites() -> void:
	_configure_actor_sprite(PLAYER_ACTOR_ID, player)
	_configure_actor_sprite(NPC_GUARD, guard)
	_configure_actor_sprite(NPC_MERCHANT, merchant)
	_configure_actor_sprite(NPC_HUNTER, hunter)
	_configure_actor_sprite(MONSTER_ACTOR_ID, monster_node)
	_set_actor_idle(PLAYER_ACTOR_ID)
	_set_actor_idle(NPC_GUARD)
	_set_actor_idle(NPC_MERCHANT)
	_set_actor_idle(NPC_HUNTER)
	_set_actor_idle(MONSTER_ACTOR_ID, "left")


func _configure_actor_sprite(actor_id: String, node: Node2D) -> void:
	var body := node.get_node_or_null("Body")
	if body is CanvasItem:
		body.visible = false
	var sprite := AnimatedSprite2D.new()
	sprite.name = "Sprite"
	sprite.sprite_frames = _build_sprite_frames(ROLE_SPRITES.get(actor_id, Vector2i(0, 0)))
	sprite.position = Vector2(0, -28)
	sprite.scale = SPRITE_SCALE
	sprite.animation = "down"
	sprite.frame = 1
	node.add_child(sprite)
	actor_sprite_nodes[actor_id] = sprite
	actor_last_direction[actor_id] = "down"


func _build_sprite_frames(group: Vector2i) -> SpriteFrames:
	var frames := SpriteFrames.new()
	var directions := ["down", "left", "right", "up"]
	var origin := Vector2i(group.x * SPRITE_GROUP_SIZE.x, group.y * SPRITE_GROUP_SIZE.y)
	for row in range(directions.size()):
		var anim: String = directions[row]
		frames.add_animation(anim)
		frames.set_animation_speed(anim, 7.0)
		for column in range(3):
			var atlas := AtlasTexture.new()
			atlas.atlas = SPRITE_SHEET
			atlas.region = Rect2(
				origin.x + column * SPRITE_FRAME_SIZE.x,
				origin.y + row * SPRITE_FRAME_SIZE.y,
				SPRITE_FRAME_SIZE.x,
				SPRITE_FRAME_SIZE.y
			)
			frames.add_frame(anim, atlas)
	return frames


func _set_actor_idle(actor_id: String, direction: String = "") -> void:
	var sprite: AnimatedSprite2D = actor_sprite_nodes.get(actor_id)
	if sprite == null:
		return
	var facing := direction if direction != "" else str(actor_last_direction.get(actor_id, "down"))
	sprite.play(facing)
	sprite.stop()
	sprite.frame = 1
	actor_last_direction[actor_id] = facing


func _set_actor_walk(actor_id: String, direction: String) -> void:
	var sprite: AnimatedSprite2D = actor_sprite_nodes.get(actor_id)
	if sprite == null:
		return
	if sprite.animation != direction or not sprite.is_playing():
		sprite.play(direction)
	actor_last_direction[actor_id] = direction


func _direction_to_animation(direction: Vector2) -> String:
	if absf(direction.x) > absf(direction.y):
		return "right" if direction.x > 0.0 else "left"
	return "down" if direction.y > 0.0 else "up"


func _move_actor_toward(actor_id: String, node: Node2D, target: Vector2, delta: float) -> bool:
	var offset := target - node.position
	if offset.length() <= 3.0:
		node.position = target
		_set_actor_idle(actor_id)
		return true
	_set_actor_walk(actor_id, _direction_to_animation(offset))
	node.position = node.position.move_toward(target, NPC_VISUAL_SPEED * delta)
	return node.position.distance_to(target) <= 3.0


func _setup_npc_overlays() -> void:
	for npc_id in npc_nodes.keys():
		var npc_node: Node2D = npc_nodes[npc_id]
		var name_label := npc_node.get_node("Label") as Label
		name_label.text = NPC_NAMES.get(npc_id, npc_id)
		name_label.position = Vector2(-56, -84)
		npc_name_labels[npc_id] = name_label

		var prompt := Label.new()
		prompt.visible = false
		prompt.position = Vector2(-56, -108)
		prompt.size = Vector2(112, 18)
		prompt.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		prompt.text = "按 E 交互"
		prompt.add_theme_color_override("font_color", Color(1.0, 0.94, 0.62))
		prompt.add_theme_color_override("font_outline_color", Color(0.05, 0.05, 0.05, 0.96))
		prompt.add_theme_constant_override("outline_size", 4)
		npc_node.add_child(prompt)
		npc_prompt_labels[npc_id] = prompt

		var bubble := Label.new()
		bubble.visible = false
		bubble.position = Vector2(-92, -140)
		bubble.size = Vector2(184, 56)
		bubble.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		bubble.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		bubble.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		bubble.add_theme_color_override("font_color", Color(0.10, 0.10, 0.10))
		bubble.add_theme_color_override("font_outline_color", Color(1, 1, 1, 0.96))
		bubble.add_theme_constant_override("outline_size", 6)
		npc_node.add_child(bubble)
		npc_reply_labels[npc_id] = bubble

		var timer := Timer.new()
		timer.one_shot = true
		timer.timeout.connect(_on_speech_hide_timeout.bind(npc_id))
		add_child(timer)
		speech_hide_timers[npc_id] = timer


func _ensure_npc_node(state: AgentState) -> void:
	if npc_nodes.has(state.npc_id):
		return
	var npc_node := Node2D.new()
	npc_node.name = state.npc_id
	add_child(npc_node)
	move_child(npc_node, max(0, get_children().find($UI) - 1))
	var name_label := Label.new()
	name_label.name = "Label"
	npc_node.add_child(name_label)
	npc_nodes[state.npc_id] = npc_node
	_configure_actor_sprite(state.npc_id, npc_node)
	_set_actor_idle(state.npc_id)
	_setup_dynamic_npc_overlay(state.npc_id, npc_node, state.name)
	var area := _area_for_npc_state(state.npc_id, state)
	npc_visual_areas[state.npc_id] = area
	npc_target_areas[state.npc_id] = area
	npc_node.position = _npc_stand_position(state.npc_id, area)


func _setup_dynamic_npc_overlay(npc_id: String, npc_node: Node2D, display_name: String) -> void:
	var name_label := npc_node.get_node("Label") as Label
	name_label.text = NPC_NAMES.get(npc_id, display_name)
	name_label.position = Vector2(-56, -84)
	npc_name_labels[npc_id] = name_label

	var prompt := Label.new()
	prompt.visible = false
	prompt.position = Vector2(-56, -108)
	prompt.size = Vector2(112, 18)
	prompt.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	prompt.text = "按 E 交互"
	prompt.add_theme_color_override("font_color", Color(1.0, 0.94, 0.62))
	prompt.add_theme_color_override("font_outline_color", Color(0.05, 0.05, 0.05, 0.96))
	prompt.add_theme_constant_override("outline_size", 4)
	npc_node.add_child(prompt)
	npc_prompt_labels[npc_id] = prompt

	var bubble := Label.new()
	bubble.visible = false
	bubble.position = Vector2(-92, -140)
	bubble.size = Vector2(184, 56)
	bubble.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	bubble.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	bubble.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	bubble.add_theme_color_override("font_color", Color(0.10, 0.10, 0.10))
	bubble.add_theme_color_override("font_outline_color", Color(1, 1, 1, 0.96))
	bubble.add_theme_constant_override("outline_size", 6)
	npc_node.add_child(bubble)
	npc_reply_labels[npc_id] = bubble

	var timer := Timer.new()
	timer.one_shot = true
	timer.timeout.connect(_on_speech_hide_timeout.bind(npc_id))
	add_child(timer)
	speech_hide_timers[npc_id] = timer


func _initialize_npc_scene_state() -> void:
	for npc_id in npc_nodes.keys():
		var area := _area_for_npc_state(npc_id, null)
		npc_visual_areas[npc_id] = area
		npc_target_areas[npc_id] = area
		npc_travel_states.erase(npc_id)
		var npc_node: Node2D = npc_nodes[npc_id]
		npc_node.position = _npc_stand_position(npc_id, area)


func _connect_client_signals() -> void:
	_safe_connect(ThoughtService.npc_list_received, _on_npc_list_received)
	_safe_connect(ThoughtService.npc_list_failed, _on_request_failed.bind("NPC 列表"))
	_safe_connect(ThoughtService.npc_state_received, _on_npc_state_received)
	_safe_connect(ThoughtService.npc_state_failed, _on_request_failed.bind("NPC 状态"))
	_safe_connect(ThoughtService.dialogue_history_received, _on_dialogue_history_received)
	_safe_connect(ThoughtService.dialogue_history_failed, _on_request_failed.bind("对话历史"))
	_safe_connect(ThoughtService.npc_inventory_received, _on_npc_inventory_received)
	_safe_connect(ThoughtService.npc_inventory_failed, _on_request_failed.bind("NPC Inventory"))
	_safe_connect(ThoughtService.village_warehouse_received, _on_village_warehouse_received)
	_safe_connect(ThoughtService.village_warehouse_failed, _on_request_failed.bind("共享仓库"))
	_safe_connect(ThoughtService.production_orders_received, _on_production_orders_received)
	_safe_connect(ThoughtService.production_orders_failed, _on_request_failed.bind("生产订单"))
	_safe_connect(ThoughtService.warehouse_transactions_received, _on_warehouse_transactions_received)
	_safe_connect(ThoughtService.warehouse_transactions_failed, _on_request_failed.bind("仓库流水"))
	_safe_connect(ThoughtService.world_resources_received, _on_world_resources_received)
	_safe_connect(ThoughtService.world_resources_failed, _on_request_failed.bind("World Resources"))
	_safe_connect(ThoughtService.world_entities_received, _on_world_entities_received)
	_safe_connect(ThoughtService.world_entities_failed, _on_request_failed.bind("World Entities"))
	_safe_connect(ThoughtService.player_utterance_received, _on_player_utterance_received)
	_safe_connect(ThoughtService.player_utterance_failed, _on_request_failed.bind("玩家发言"))
	_safe_connect(ThoughtService.plan_applied, _on_plan_applied)
	_safe_connect(ThoughtService.plan_failed, _on_request_failed.bind("行动规划"))
	_safe_connect(ThoughtService.task_executed, _on_task_executed)
	_safe_connect(ThoughtService.task_execution_failed, _on_request_failed.bind("任务执行"))
	_safe_connect(ThoughtService.event_ingested, _on_event_ingested)
	_safe_connect(ThoughtService.event_failed, _on_request_failed.bind("事件注入"))
	_safe_connect(ThoughtService.event_log_received, _on_event_log_received)
	_safe_connect(ThoughtService.event_log_failed, _on_request_failed.bind("事件日志"))
	_safe_connect(ThoughtService.simulation_tick_completed, _on_simulation_tick_completed)
	_safe_connect(ThoughtService.simulation_tick_failed, _on_simulation_tick_failed)
	_safe_connect(ThoughtService.world_reset, _on_world_reset)
	_safe_connect(ThoughtService.world_reset_failed, _on_request_failed.bind("世界重置"))
	if not auto_tick_timer.timeout.is_connected(_on_auto_tick_timer_timeout):
		auto_tick_timer.timeout.connect(_on_auto_tick_timer_timeout)


func _connect_ui_signals() -> void:
	if not speech_input.text_submitted.is_connected(_on_speech_input_text_submitted):
		speech_input.text_submitted.connect(_on_speech_input_text_submitted)


func _safe_connect(signal_ref: Signal, callable_ref: Callable) -> void:
	if not signal_ref.is_connected(callable_ref):
		signal_ref.connect(callable_ref)


func _apply_static_ui_text() -> void:
	var title := get_node("UI/Panel/VBox/TitleRow/Title") as Label
	title.text = "AI NPC 多场景演示"
	dialogue_log.text = "靠近 NPC 或热点后按 E 交互。输入内容后按回车发送。"
	thought_log.text = "思考与规划结果会显示在这里。"
	task_log.text = "任务执行结果会显示在这里。"
	event_log.text = "世界事件记录会显示在这里。"
	event_detail_log.text = "建筑、入口和热点说明会显示在这里。"
	speech_input.placeholder_text = "输入对话，按回车发送"

	var submit_button := get_node("UI/Panel/VBox/ButtonRow/SubmitButton") as Button
	var suspicious_button := get_node("UI/Panel/VBox/ButtonRow/SuspiciousEventButton") as Button
	var plan_button := get_node("UI/Panel/VBox/ButtonRow/PlanExecuteButton") as Button
	var reset_button := get_node("UI/Panel/VBox/ButtonRow/ResetButton") as Button
	var advance_button := get_node("UI/Panel/VBox/TickControlRow/AdvanceTickButton") as Button
	var monster_button := get_node("UI/Panel/VBox/EventRow/MonsterEventButton") as Button
	var resource_button := get_node("UI/Panel/VBox/EventRow/ResourceEventButton") as Button
	var theft_button := get_node("UI/Panel/VBox/EventRow/TheftEventButton") as Button
	submit_button.text = "发送对话 / Enter"
	suspicious_button.text = "可疑 / O"
	plan_button.text = "规划 / P"
	reset_button.text = "重置 / R"
	advance_button.text = "推进 Tick / T"
	monster_button.text = "怪物"
	resource_button.text = "短缺"
	theft_button.text = "偷窃"

	for node_name in ["GateLabel", "MarketLabel", "ForestLabel", "InnLabel"]:
		var node := get_node_or_null(node_name)
		if node is CanvasItem:
			node.visible = false


func _refresh_backend_state() -> void:
	ThoughtService.request_all_npc_states()
	ThoughtService.request_world_resources(_location_id_for_area(current_area_id))
	ThoughtService.request_world_entities(_location_id_for_area(current_area_id))
	ThoughtService.request_event_log()
	_refresh_economy_state()
	if selected_npc_id != "":
		ThoughtService.request_dialogue_history(selected_npc_id, PLAYER_ID, 6)
		ThoughtService.request_npc_inventory(selected_npc_id)


func _refresh_economy_state() -> void:
	ThoughtService.request_village_warehouse()
	ThoughtService.request_production_orders()
	ThoughtService.request_warehouse_transactions(8)


func _move_player(delta: float) -> void:
	var direction := Vector2.ZERO
	direction.x = Input.get_action_strength("ui_right") - Input.get_action_strength("ui_left")
	direction.y = Input.get_action_strength("ui_down") - Input.get_action_strength("ui_up")
	if Input.is_key_pressed(KEY_A):
		direction.x -= 1.0
	if Input.is_key_pressed(KEY_D):
		direction.x += 1.0
	if Input.is_key_pressed(KEY_W):
		direction.y -= 1.0
	if Input.is_key_pressed(KEY_S):
		direction.y += 1.0
	if direction == Vector2.ZERO:
		_set_actor_idle(PLAYER_ACTOR_ID)
		return
	_set_actor_walk(PLAYER_ACTOR_ID, _direction_to_animation(direction))
	player.position += direction.normalized() * PLAYER_SPEED * delta
	player.position.x = clampf(player.position.x, player_bounds.position.x, player_bounds.end.x)
	player.position.y = clampf(player.position.y, player_bounds.position.y, player_bounds.end.y)


func _switch_area(area_id: String, status_text: String = "", spawn_position: Variant = null) -> void:
	if not AREA_META.has(area_id):
		return
	var previous_area_id := current_area_id
	current_area_id = area_id
	if spawn_position != null and typeof(spawn_position) == TYPE_VECTOR2:
		player.position = spawn_position
	else:
		var transition_key := "%s->%s" % [previous_area_id, area_id]
		player.position = TRANSITION_SPAWN_POINTS.get(transition_key, AREA_SPAWN_POINTS.get(area_id, Vector2(620, 800)))
	var meta: Dictionary = AREA_META[area_id]
	world_background.texture = meta.get("background")
	var title := get_node("WorldBanner/WorldBannerVBox/WorldTitle") as Label
	var subtitle := get_node("WorldBanner/WorldBannerVBox/WorldSubtitle") as Label
	title.text = str(meta.get("name", area_id))
	subtitle.text = str(meta.get("subtitle", ""))
	_rebuild_hotspots()
	ThoughtService.request_world_resources(_location_id_for_area(area_id))
	ThoughtService.request_world_entities(_location_id_for_area(area_id))
	_update_npc_visibility()
	_update_monster_visibility()
	_refresh_interaction_state()
	if status_text != "":
		_set_status(status_text)
	_append_event_detail("[%s] %s" % [meta.get("name", area_id), meta.get("subtitle", "")])


func _rebuild_hotspots() -> void:
	hotspot_markers.clear()
	current_hotspot_index = -1
	for child in hotspot_layer.get_children():
		child.queue_free()
	for hotspot in AREA_HOTSPOTS.get(current_area_id, []):
		var marker := Label.new()
		marker.text = "!"
		marker.position = hotspot.get("pos", Vector2.ZERO)
		marker.size = Vector2(34, 40)
		marker.mouse_filter = Control.MOUSE_FILTER_IGNORE
		marker.pivot_offset = marker.size * 0.5
		marker.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		marker.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		marker.modulate = Color(1.0, 0.84, 0.16, 0.82)
		marker.add_theme_font_size_override("font_size", 30)
		marker.add_theme_color_override("font_color", Color(1.0, 0.84, 0.16))
		marker.add_theme_color_override("font_outline_color", Color(0.08, 0.06, 0.02, 0.96))
		marker.add_theme_constant_override("outline_size", 5)
		var hint := Label.new()
		hint.visible = false
		hotspot_layer.add_child(marker)
		hotspot_markers.append({
			"hotspot": hotspot,
			"marker": marker,
			"hint": hint,
			"center": Vector2(marker.position.x + marker.size.x * 0.5, marker.position.y + marker.size.y * 0.5),
		})


func _refresh_interaction_state() -> void:
	_update_target_npc()
	_update_target_hotspot()
	_apply_interaction_highlights()
	_update_selected_label()


func _update_target_npc() -> void:
	target_npc_id = ""
	var nearest_distance := NPC_INTERACTION_DISTANCE
	for npc_id in npc_nodes.keys():
		var npc_node: Node2D = npc_nodes[npc_id]
		if not npc_node.visible:
			continue
		var distance := player.position.distance_to(npc_node.position)
		if distance < nearest_distance:
			nearest_distance = distance
			target_npc_id = npc_id


func _update_target_hotspot() -> void:
	current_hotspot_index = -1
	var nearest_distance := HOTSPOT_INTERACTION_DISTANCE
	for index in range(hotspot_markers.size()):
		var center: Vector2 = hotspot_markers[index].get("center", Vector2.ZERO)
		var distance := player.position.distance_to(center)
		if distance < nearest_distance:
			nearest_distance = distance
			current_hotspot_index = index


func _apply_interaction_highlights() -> void:
	current_interactable_type = ""
	for npc_id in npc_nodes.keys():
		var npc_node: Node2D = npc_nodes[npc_id]
		npc_node.modulate = Color(1, 1, 1, 1)
		var prompt: Label = npc_prompt_labels.get(npc_id)
		if prompt != null:
			prompt.visible = false
	for item in hotspot_markers:
		var marker: Control = item.get("marker")
		var hint: Label = item.get("hint")
		marker.visible = true
		marker.scale = Vector2.ONE
		marker.modulate = Color(1.0, 0.84, 0.16, 0.82)
		if hint != null:
			hint.visible = false

	var npc_distance := INF
	if target_npc_id != "":
		var target_node: Node2D = npc_nodes.get(target_npc_id)
		if target_node != null and target_node.visible:
			npc_distance = player.position.distance_to(target_node.position)
	var hotspot_distance := INF
	if current_hotspot_index >= 0:
		hotspot_distance = player.position.distance_to(hotspot_markers[current_hotspot_index].get("center", Vector2.ZERO))

	if npc_distance <= hotspot_distance and target_npc_id != "":
		var npc_node: Node2D = npc_nodes.get(target_npc_id)
		if npc_node != null and npc_node.visible:
			npc_node.modulate = Color(1.08, 1.08, 0.82, 1)
			var npc_prompt: Label = npc_prompt_labels.get(target_npc_id)
			if npc_prompt != null:
				npc_prompt.visible = true
			current_interactable_type = "npc"
	elif current_hotspot_index >= 0:
		var hotspot_item: Dictionary = hotspot_markers[current_hotspot_index]
		var hotspot_marker: Control = hotspot_item.get("marker")
		var hotspot_hint: Label = hotspot_item.get("hint")
		hotspot_marker.scale = Vector2(1.16, 1.16)
		hotspot_marker.modulate = Color(1.0, 0.95, 0.67, 0.96)
		if hotspot_hint != null:
			hotspot_hint.visible = false
		current_interactable_type = "hotspot"


func _interact_with_current_target() -> void:
	if current_interactable_type == "npc" and target_npc_id != "":
		_select_npc(target_npc_id, true, false)
		return
	if current_interactable_type == "hotspot" and current_hotspot_index >= 0:
		_activate_hotspot(hotspot_markers[current_hotspot_index].get("hotspot", {}))


func _activate_hotspot(hotspot: Dictionary) -> void:
	var center: Vector2 = hotspot.get("pos", player.position)
	player.position = Vector2(center.x + 30.0, center.y + 76.0)
	var detail := str(hotspot.get("detail", ""))
	match str(hotspot.get("kind", "")):
		"transition":
			var target_area := str(hotspot.get("target_area", AREA_VILLAGE_SQUARE))
			var transition_key := "%s->%s" % [current_area_id, target_area]
			var spawn_position: Variant = TRANSITION_SPAWN_POINTS.get(transition_key, null)
			_switch_area(target_area, detail, spawn_position)
		"focus_npc":
			var npc_id := str(hotspot.get("npc_id", ""))
			if npc_id != "":
				_select_npc(npc_id, true, false)
			_append_event_detail(detail)
		"rest":
			task_log.text = "已到达%s。\n\n这里适合承接休息、恢复和慢节奏对话。" % str(hotspot.get("label", "休息点"))
			_set_status("已到达%s。" % str(hotspot.get("label", "休息点")))
			_append_event_detail(detail)
		_:
			_set_status("已查看%s。" % str(hotspot.get("label", "热点")))
			_append_event_detail(detail)


func _update_npc_visibility() -> void:
	for npc_id in npc_nodes.keys():
		var npc_node: Node2D = npc_nodes[npc_id]
		if not npc_visual_areas.has(npc_id):
			var fallback_area := _area_for_npc_state(npc_id, npc_states_by_id.get(npc_id))
			npc_visual_areas[npc_id] = fallback_area
			npc_target_areas[npc_id] = fallback_area
			npc_node.position = _npc_stand_position(npc_id, fallback_area)
		var npc_area := str(npc_visual_areas.get(npc_id, AREA_VILLAGE_SQUARE))
		var visible_here := npc_area == current_area_id
		npc_node.visible = visible_here
		if visible_here:
			var name_label: Label = npc_name_labels.get(npc_id)
			if name_label != null:
				name_label.text = NPC_NAMES.get(npc_id, npc_id)
			var prompt: Label = npc_prompt_labels.get(npc_id)
			if prompt != null:
				prompt.visible = false
			npc_node.modulate = Color(1, 1, 1, 1)
			if not npc_travel_states.has(npc_id):
				_set_actor_idle(npc_id)
		else:
			_hide_speech_bubble(npc_id)
			var hidden_prompt: Label = npc_prompt_labels.get(npc_id)
			if hidden_prompt != null:
				hidden_prompt.visible = false


func _sync_npc_target_area(npc_id: String, target_area: String) -> void:
	if target_area == "" or not AREA_META.has(target_area):
		return
	if not npc_visual_areas.has(npc_id):
		npc_visual_areas[npc_id] = target_area
		npc_target_areas[npc_id] = target_area
		var npc_node: Node2D = npc_nodes.get(npc_id)
		if npc_node != null:
			npc_node.position = _npc_stand_position(npc_id, target_area)
		return
	npc_target_areas[npc_id] = target_area
	if str(npc_visual_areas.get(npc_id, "")) != target_area and not npc_travel_states.has(npc_id):
		_start_next_npc_travel_leg(npc_id)
	elif str(npc_visual_areas.get(npc_id, "")) == target_area and not npc_travel_states.has(npc_id):
		var npc_node: Node2D = npc_nodes.get(npc_id)
		if npc_node != null and npc_node.position.distance_to(_npc_stand_position(npc_id, target_area)) > 3.0:
			npc_travel_states[npc_id] = {
				"phase": "local",
				"target_area": target_area,
				"target_pos": _npc_stand_position(npc_id, target_area),
			}


func _start_next_npc_travel_leg(npc_id: String) -> void:
	var from_area := str(npc_visual_areas.get(npc_id, _area_for_npc_state(npc_id, null)))
	var final_area := str(npc_target_areas.get(npc_id, from_area))
	var npc_node: Node2D = npc_nodes.get(npc_id)
	if npc_node == null:
		return
	if from_area == final_area:
		npc_travel_states[npc_id] = {
			"phase": "local",
			"target_area": final_area,
			"target_pos": _npc_stand_position(npc_id, final_area),
		}
		return
	var next_area := _next_area_toward(from_area, final_area)
	if next_area == "":
		npc_visual_areas[npc_id] = final_area
		npc_node.position = _npc_stand_position(npc_id, final_area)
		npc_travel_states.erase(npc_id)
		_update_npc_visibility()
		return
	var exit_pos := _transition_position(from_area, next_area, npc_node.position)
	var entry_pos := _entry_position(from_area, next_area)
	var target_pos := _npc_stand_position(npc_id, next_area)
	if from_area == current_area_id:
		npc_travel_states[npc_id] = {
			"phase": "exit",
			"from_area": from_area,
			"to_area": next_area,
			"exit_pos": exit_pos,
			"entry_pos": entry_pos,
			"target_pos": target_pos,
		}
	else:
		npc_visual_areas[npc_id] = next_area
		npc_node.position = entry_pos
		npc_travel_states[npc_id] = {
			"phase": "enter",
			"from_area": from_area,
			"to_area": next_area,
			"target_pos": target_pos,
		}
		_update_npc_visibility()


func _advance_npc_travel(delta: float) -> void:
	for npc_id in npc_travel_states.keys():
		var npc_node: Node2D = npc_nodes.get(npc_id)
		if npc_node == null:
			continue
		var travel: Dictionary = npc_travel_states.get(npc_id, {})
		var phase := str(travel.get("phase", ""))
		match phase:
			"exit":
				var exit_pos: Vector2 = travel.get("exit_pos", npc_node.position)
				if _move_actor_toward(npc_id, npc_node, exit_pos, delta):
					var to_area := str(travel.get("to_area", npc_visual_areas.get(npc_id, "")))
					npc_visual_areas[npc_id] = to_area
					npc_node.position = travel.get("entry_pos", _npc_stand_position(npc_id, to_area))
					travel["phase"] = "enter"
					npc_travel_states[npc_id] = travel
					_update_npc_visibility()
			"enter", "local":
				var target_pos: Vector2 = travel.get("target_pos", npc_node.position)
				if _move_actor_toward(npc_id, npc_node, target_pos, delta):
					var visual_area := str(npc_visual_areas.get(npc_id, ""))
					var final_area := str(npc_target_areas.get(npc_id, visual_area))
					npc_travel_states.erase(npc_id)
					if visual_area != final_area:
						_start_next_npc_travel_leg(npc_id)
					else:
						_update_npc_visibility()
			_:
				npc_travel_states.erase(npc_id)


func _npc_stand_position(npc_id: String, area_id: String) -> Vector2:
	var area_positions: Dictionary = NPC_AREA_POSITIONS.get(npc_id, {})
	return area_positions.get(area_id, AREA_SPAWN_POINTS.get(area_id, Vector2(760, 700)))


func _transition_position(from_area: String, to_area: String, fallback: Vector2) -> Vector2:
	for hotspot in AREA_HOTSPOTS.get(from_area, []):
		if typeof(hotspot) == TYPE_DICTIONARY and str(hotspot.get("kind", "")) == "transition" and str(hotspot.get("target_area", "")) == to_area:
			return hotspot.get("pos", fallback)
	return fallback


func _entry_position(from_area: String, to_area: String) -> Vector2:
	var transition_key := "%s->%s" % [from_area, to_area]
	return TRANSITION_SPAWN_POINTS.get(transition_key, AREA_SPAWN_POINTS.get(to_area, Vector2(620, 800)))


func _next_area_toward(from_area: String, target_area: String) -> String:
	if from_area == target_area:
		return from_area
	var visited := {from_area: true}
	var queue: Array[Dictionary] = [{"area": from_area, "first": ""}]
	while not queue.is_empty():
		var item: Dictionary = queue.pop_front()
		var area := str(item.get("area", ""))
		var first := str(item.get("first", ""))
		for next_area in _transition_targets(area):
			if visited.has(next_area):
				continue
			var first_step := next_area if first == "" else first
			if next_area == target_area:
				return first_step
			visited[next_area] = true
			queue.append({"area": next_area, "first": first_step})
	return ""


func _transition_targets(area_id: String) -> Array[String]:
	var targets: Array[String] = []
	for hotspot in AREA_HOTSPOTS.get(area_id, []):
		if typeof(hotspot) == TYPE_DICTIONARY and str(hotspot.get("kind", "")) == "transition":
			var target_area := str(hotspot.get("target_area", ""))
			if target_area != "":
				targets.append(target_area)
	return targets


func _update_monster_visibility() -> void:
	if monster_node == null:
		return
	monster_node.visible = current_area_id == monster_area_id
	if monster_node.visible:
		monster_node.modulate = Color(1, 1, 1, 1)
		_set_actor_idle(MONSTER_ACTOR_ID, "left")


func _area_for_npc_state(npc_id: String, state: AgentState) -> String:
	if state != null:
		var current_task_location := ""
		if typeof(state.current_task) == TYPE_DICTIONARY:
			current_task_location = str(state.current_task.get("location_id", ""))
		if current_task_location != "" and AREA_BY_LOCATION.has(current_task_location):
			return str(AREA_BY_LOCATION[current_task_location])
		if AREA_BY_LOCATION.has(state.location_id):
			return str(AREA_BY_LOCATION[state.location_id])
	match npc_id:
		NPC_GUARD:
			return AREA_VILLAGE_ENTRANCE
		NPC_MERCHANT:
			return AREA_VILLAGE_MARKET
		NPC_HUNTER:
			return AREA_HUNTING_FOREST
		_:
			return AREA_VILLAGE_SQUARE


func _select_npc(npc_id: String, fetch_history: bool, switch_area_to_npc: bool) -> void:
	selected_npc_id = npc_id
	if switch_area_to_npc:
		var npc_area := str(npc_visual_areas.get(npc_id, _area_for_npc_state(npc_id, npc_states_by_id.get(npc_id))))
		if npc_area != current_area_id:
			_set_status("%s 不在当前场景，请通过入口前往。" % NPC_NAMES.get(npc_id, npc_id))
	if fetch_history:
		ThoughtService.request_dialogue_history(npc_id, PLAYER_ID, 6)
		ThoughtService.request_npc_inventory(npc_id)
	if dialogue_history_by_npc.has(npc_id):
		_render_dialogue_history(npc_id)
	_update_selected_label()


func _can_talk_to_npc(npc_id: String) -> bool:
	var npc_node: Node2D = npc_nodes.get(npc_id)
	if npc_node == null or not npc_node.visible:
		return false
	if str(npc_visual_areas.get(npc_id, "")) != current_area_id:
		return false
	return player.position.distance_to(npc_node.position) <= NPC_INTERACTION_DISTANCE


func _update_selected_label() -> void:
	var area_name := str(AREA_META.get(current_area_id, {}).get("name", current_area_id))
	var nearby := "无"
	if current_interactable_type == "npc" and target_npc_id != "":
		nearby = NPC_NAMES.get(target_npc_id, target_npc_id)
	elif current_interactable_type == "hotspot" and current_hotspot_index >= 0:
		nearby = str(hotspot_markers[current_hotspot_index].get("hotspot", {}).get("label", "热点"))
	var selected := "无"
	if selected_npc_id != "":
		selected = NPC_NAMES.get(selected_npc_id, selected_npc_id)
	selected_label.text = "当前区域：%s | 可交互：%s | 已选目标：%s" % [area_name, nearby, selected]


func _on_npc_list_received(states: Array) -> void:
	for state in states:
		if state is AgentState:
			_ensure_npc_node(state)
			npc_states_by_id[state.npc_id] = state
			npc_inventory_by_id[state.npc_id] = state.inventory
			_sync_npc_target_area(state.npc_id, _area_for_npc_state(state.npc_id, state))
	_update_npc_visibility()
	if selected_npc_id != "" and dialogue_history_by_npc.has(selected_npc_id):
		_render_dialogue_history(selected_npc_id)
	_set_status("已加载 %d 个 NPC 状态。" % npc_states_by_id.size())


func _on_npc_state_received(state: AgentState) -> void:
	_ensure_npc_node(state)
	npc_states_by_id[state.npc_id] = state
	npc_inventory_by_id[state.npc_id] = state.inventory
	_sync_npc_target_area(state.npc_id, _area_for_npc_state(state.npc_id, state))
	_update_npc_visibility()


func _on_dialogue_history_received(npc_id: String, history: Dictionary) -> void:
	dialogue_history_by_npc[npc_id] = history
	if npc_id == selected_npc_id:
		_render_dialogue_history(npc_id)


func _render_dialogue_history(npc_id: String) -> void:
	var history: Dictionary = dialogue_history_by_npc.get(npc_id, {})
	var lines: Array[String] = []
	var summary := str(history.get("summary", "")).strip_edges()
	if summary != "":
		lines.append("摘要：%s" % summary)
		lines.append("")
	for turn in history.get("recent_turns", []):
		if typeof(turn) != TYPE_DICTIONARY:
			continue
		lines.append("[%s] %s：%s" % [
			str(turn.get("created_at_tick", "?")),
			str(turn.get("speaker_label", turn.get("role", ""))),
			str(turn.get("content", "")),
		])
	if lines.is_empty():
		lines.append("还没有对话记录。")
	dialogue_log.text = "\n".join(lines)


func _on_speech_input_text_submitted(_value: String) -> void:
	_on_submit_button_pressed()


func _on_submit_button_pressed() -> void:
	var npc_id := target_npc_id
	if npc_id == "" and selected_npc_id != "" and _can_talk_to_npc(selected_npc_id):
		npc_id = selected_npc_id
	if npc_id == "":
		_set_status("附近没有可对话 NPC。")
		return
	var content := speech_input.text.strip_edges()
	if content == "":
		_set_status("请输入对话内容。")
		return
	current_tick += 1
	_update_tick_label()
	pending_dialogue_npc_id = npc_id
	_select_npc(npc_id, false, false)
	_show_speech_bubble(npc_id, "...")
	_set_status("正在向 %s 发送对话。" % NPC_NAMES.get(npc_id, npc_id))
	ThoughtService.submit_player_utterance(npc_id, PLAYER_ID, content, current_tick)


func _on_player_utterance_received(result: Dictionary) -> void:
	var npc_id := str(result.get("npc_id", pending_dialogue_npc_id))
	var reply := str(result.get("npc_reply", ""))
	if npc_id != "":
		_show_speech_bubble(npc_id, reply)
		ThoughtService.request_dialogue_history(npc_id, PLAYER_ID, 6)
	speech_input.text = ""
	pending_dialogue_npc_id = ""
	_set_status("对话已返回。来源=%s" % str(result.get("source", "?")))
	ThoughtService.request_all_npc_states()


func _on_plan_execute_button_pressed() -> void:
	var npc_id := selected_npc_id
	if npc_id == "":
		_set_status("请先靠近并按 E 选择一个 NPC。")
		return
	pending_plan_then_execute = true
	_set_status("正在为 %s 规划并执行任务。" % NPC_NAMES.get(npc_id, npc_id))
	ThoughtService.plan_next_action_for_npc(npc_id)


func _on_plan_applied(result: Dictionary) -> void:
	var npc_id := str(result.get("npc_id", selected_npc_id))
	task_log.text = "规划 NPC：%s\n模式：%s\n任务：%s" % [
		NPC_NAMES.get(npc_id, npc_id),
		str(result.get("mode", "")),
		_format_task(result.get("selected_task", {})),
	]
	thought_log.text = _format_thought(result.get("thought", {}))
	if pending_plan_then_execute and npc_id != "":
		pending_plan_then_execute = false
		ThoughtService.execute_current_task_for_npc(npc_id)
		return
	_set_status("%s 的规划已更新。" % NPC_NAMES.get(npc_id, npc_id))
	ThoughtService.request_all_npc_states()


func _on_task_executed(result: Dictionary) -> void:
	var npc_id := str(result.get("npc_id", selected_npc_id))
	var world_effects: Variant = result.get("world_effects", {})
	task_log.text = "执行 NPC：%s\n当前任务：%s\n下一任务：%s" % [
		NPC_NAMES.get(npc_id, npc_id),
		_format_task(result.get("executed_task", {})),
		_format_task(result.get("next_current_task", {})),
	]
	_set_status("%s 已执行当前任务。" % NPC_NAMES.get(npc_id, npc_id))
	if typeof(world_effects) == TYPE_DICTIONARY and not world_effects.is_empty():
		task_log.text += "\nworld=%s" % JSON.stringify(world_effects)
	ThoughtService.request_all_npc_states()
	ThoughtService.request_event_log()
	ThoughtService.request_world_resources(_location_id_for_area(current_area_id))
	ThoughtService.request_world_entities(_location_id_for_area(current_area_id))
	_refresh_economy_state()


func _on_advance_tick_button_pressed() -> void:
	_request_next_tick(false)


func _request_next_tick(from_auto: bool) -> void:
	if tick_request_in_flight:
		if auto_tick_enabled and from_auto:
			_schedule_next_auto_tick()
		return
	tick_request_in_flight = true
	current_tick += 1
	_update_tick_label()
	_set_status("正在推进 tick %d。" % current_tick)
	ThoughtService.run_simulation_tick(current_tick)


func _on_simulation_tick_completed(result: Dictionary) -> void:
	tick_request_in_flight = false
	current_tick = int(result.get("current_tick", current_tick))
	_update_tick_label()
	thought_log.text = _format_tick_profile(result.get("profile", {}))
	task_log.text = _format_tick_results(result.get("npc_results", []))
	var world_update: Variant = result.get("world_update", {})
	if typeof(world_update) == TYPE_DICTIONARY and not world_update.is_empty():
		_append_event_detail(_format_world_update(world_update))
	_set_status("tick %d 已完成。" % current_tick)
	ThoughtService.request_all_npc_states()
	ThoughtService.request_event_log()
	ThoughtService.request_world_resources(_location_id_for_area(current_area_id))
	ThoughtService.request_world_entities(_location_id_for_area(current_area_id))
	_refresh_economy_state()
	if auto_tick_enabled:
		_schedule_next_auto_tick()


func _on_simulation_tick_failed(status_code: int, message: String) -> void:
	tick_request_in_flight = false
	_stop_auto_tick()
	_on_request_failed(status_code, message, "Tick 推进")


func _on_auto_tick_button_pressed() -> void:
	auto_tick_enabled = not auto_tick_enabled
	_update_auto_tick_button()
	if auto_tick_enabled:
		_schedule_next_auto_tick()
		_set_status("自动推进已启动。")
	else:
		auto_tick_timer.stop()
		_set_status("自动推进已暂停。")


func _schedule_next_auto_tick() -> void:
	auto_tick_timer.stop()
	auto_tick_timer.wait_time = maxf(float(auto_tick_interval_spin_box.value), 0.2)
	auto_tick_timer.start()


func _stop_auto_tick() -> void:
	auto_tick_enabled = false
	auto_tick_timer.stop()
	_update_auto_tick_button()


func _on_auto_tick_timer_timeout() -> void:
	if auto_tick_enabled:
		_request_next_tick(true)


func _update_auto_tick_button() -> void:
	auto_tick_button.text = "自动推进：开" if auto_tick_enabled else "自动推进：关"


func _on_reset_button_pressed() -> void:
	_stop_auto_tick()
	ThoughtService.reset_world_state()
	_set_status("正在重置世界。")


func _on_world_reset(_result: Dictionary) -> void:
	current_tick = 0
	selected_npc_id = ""
	target_npc_id = ""
	dialogue_history_by_npc.clear()
	npc_states_by_id.clear()
	npc_visual_areas.clear()
	npc_target_areas.clear()
	npc_travel_states.clear()
	_initialize_npc_scene_state()
	monster_area_id = AREA_HUNTING_FOREST
	speech_input.text = ""
	dialogue_log.text = "世界已重置，等待重新载入 NPC 状态。"
	thought_log.text = "思考与规划结果会显示在这里。"
	task_log.text = "任务执行结果会显示在这里。"
	event_log.text = "世界事件记录会显示在这里。"
	event_detail_log.text = "建筑、入口和热点说明会显示在这里。"
	for npc_id in npc_nodes.keys():
		_hide_speech_bubble(npc_id)
	_switch_area(AREA_VILLAGE_ENTRANCE, "世界已重置，回到村庄入口。")
	_update_tick_label()
	_refresh_backend_state()
	_update_monster_visibility()


func _on_suspicious_event_button_pressed() -> void:
	_submit_world_event("suspicious_arrival", "traveler_unknown", "发现可疑来客")


func _on_monster_event_button_pressed() -> void:
	_submit_world_event("monster_appeared", "monster_wolf_001", "林地出现怪物")


func _on_resource_event_button_pressed() -> void:
	_submit_world_event("food_shortage", "market_supply", "集市补给短缺")


func _on_theft_event_button_pressed() -> void:
	_submit_world_event("player_stole", PLAYER_ID, "有人报告偷窃")


func _submit_world_event(event_type: String, actor_id: String, detail: String) -> void:
	current_tick += 1
	_update_tick_label()
	var location_id := str(LOCATION_BY_AREA.get(current_area_id, "village_square"))
	if event_type == "monster_appeared":
		monster_area_id = current_area_id
		_update_monster_visibility()
	var event := {
		"event_id": "%s_%d" % [event_type, current_tick],
		"event_type": event_type,
		"actor_id": actor_id,
		"target_id": null,
		"location_id": location_id,
		"payload": {"detail": detail, "source": "godot_scene_demo"},
		"importance": 70,
		"created_at_tick": current_tick,
	}
	ThoughtService.ingest_event(event)
	_set_status("正在注入事件：%s。" % detail)


func _on_event_ingested(result: Dictionary) -> void:
	ThoughtService.request_world_resources(_location_id_for_area(current_area_id))
	ThoughtService.request_world_entities(_location_id_for_area(current_area_id))
	_append_event_detail("事件已注入：%s" % str(result))
	ThoughtService.request_event_log()
	ThoughtService.request_all_npc_states()
	_refresh_economy_state()


func _on_event_log_received(events: Array) -> void:
	var lines: Array[String] = []
	for event in events:
		if typeof(event) != TYPE_DICTIONARY:
			continue
		lines.append("[t%s] %s | actor=%s | location=%s" % [
			str(event.get("created_at_tick", "?")),
			str(event.get("event_type", "")),
			str(event.get("actor_id", "-")),
			str(event.get("location_id", "-")),
		])
	event_log.text = "\n".join(lines) if not lines.is_empty() else "暂无世界事件。"


func _on_npc_inventory_received(npc_id: String, inventory: Array) -> void:
	npc_inventory_by_id[npc_id] = inventory
	if npc_id == selected_npc_id and not inventory.is_empty():
		_append_event_detail(_format_inventory_summary(npc_id, inventory))


func _on_village_warehouse_received(items: Array) -> void:
	village_warehouse = items
	_render_economy_summary()


func _on_production_orders_received(orders: Array) -> void:
	production_orders = orders
	_render_economy_summary()


func _on_warehouse_transactions_received(transactions: Array) -> void:
	warehouse_transactions = transactions
	_render_economy_summary()


func _on_world_resources_received(resources: Array) -> void:
	world_resources_by_id.clear()
	for item in resources:
		if typeof(item) != TYPE_DICTIONARY:
			continue
		world_resources_by_id[str(item.get("node_id", ""))] = item
	_rebuild_resource_markers(resources)


func _on_world_entities_received(entities: Array) -> void:
	world_entities_by_id.clear()
	for item in entities:
		if typeof(item) != TYPE_DICTIONARY:
			continue
		world_entities_by_id[str(item.get("entity_id", ""))] = item
	_rebuild_entity_markers(entities)


func _on_request_failed(status_code: int, message: String, label: String) -> void:
	_set_status("%s失败（%d）：%s" % [label, status_code, message])
	_append_event_detail("%s失败：%s" % [label, message])


func _show_speech_bubble(npc_id: String, text: String) -> void:
	var bubble: Label = npc_reply_labels.get(npc_id)
	if bubble == null:
		return
	bubble.text = text
	bubble.visible = text != ""
	var timer: Timer = speech_hide_timers.get(npc_id)
	if timer != null:
		timer.stop()
		if text != "":
			timer.start(SPEECH_BUBBLE_DURATION)


func _hide_speech_bubble(npc_id: String) -> void:
	var bubble: Label = npc_reply_labels.get(npc_id)
	if bubble != null:
		bubble.text = ""
		bubble.visible = false
	var timer: Timer = speech_hide_timers.get(npc_id)
	if timer != null:
		timer.stop()


func _on_speech_hide_timeout(npc_id: String) -> void:
	_hide_speech_bubble(npc_id)


func _update_tick_label() -> void:
	tick_label.text = "Tick %d" % current_tick


func _set_status(text: String) -> void:
	status_label.text = "状态：%s" % text


func _append_event_detail(text: String) -> void:
	var current := event_detail_log.text.strip_edges()
	event_detail_log.text = text if current == "" else "%s\n\n%s" % [text, current]


func _location_id_for_area(area_id: String) -> String:
	return str(LOCATION_BY_AREA.get(area_id, "village_square"))


func _rebuild_resource_markers(resources: Array) -> void:
	for child in resource_layer.get_children():
		child.queue_free()
	resource_marker_nodes.clear()
	var index := 0
	for item in resources:
		if typeof(item) != TYPE_DICTIONARY:
			continue
		var marker := Label.new()
		marker.text = "%s x%s" % [
			str(item.get("display_name", item.get("resource_type", "resource"))),
			str(item.get("available_quantity", 0)),
		]
		marker.position = _resource_marker_position(index)
		marker.size = Vector2(190, 24)
		marker.mouse_filter = Control.MOUSE_FILTER_IGNORE
		marker.add_theme_color_override("font_color", Color(0.86, 0.96, 0.72))
		marker.add_theme_color_override("font_outline_color", Color(0.05, 0.08, 0.03, 0.92))
		marker.add_theme_constant_override("outline_size", 4)
		resource_layer.add_child(marker)
		resource_marker_nodes[str(item.get("node_id", ""))] = marker
		index += 1


func _resource_marker_position(index: int) -> Vector2:
	match current_area_id:
		AREA_HUNTING_FOREST:
			return Vector2(120, 180 + index * 28)
		AREA_VILLAGE_MARKET:
			return Vector2(150, 820 + index * 28)
		_:
			return Vector2(120, 160 + index * 28)


func _rebuild_entity_markers(entities: Array) -> void:
	for child in entity_layer.get_children():
		child.queue_free()
	dynamic_entity_nodes.clear()
	var index := 0
	for item in entities:
		if typeof(item) != TYPE_DICTIONARY:
			continue
		var node := Node2D.new()
		node.position = _entity_marker_position(index)
		var body := Polygon2D.new()
		body.color = Color(0.88, 0.34, 0.28, 0.92) if str(item.get("entity_type", "")) == "monster" else Color(0.48, 0.78, 0.98, 0.9)
		body.polygon = PackedVector2Array([Vector2(-18, 8), Vector2(0, -24), Vector2(18, 8), Vector2(0, 18)])
		node.add_child(body)
		var label := Label.new()
		label.text = "%s [%s]" % [
			str(item.get("display_name", item.get("entity_id", ""))),
			str(item.get("state", "")),
		]
		label.position = Vector2(-78, 20)
		label.size = Vector2(156, 28)
		label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		label.add_theme_color_override("font_color", Color(0.98, 0.96, 0.90))
		label.add_theme_color_override("font_outline_color", Color(0.05, 0.05, 0.05, 0.95))
		label.add_theme_constant_override("outline_size", 4)
		node.add_child(label)
		entity_layer.add_child(node)
		dynamic_entity_nodes[str(item.get("entity_id", ""))] = node
		index += 1


func _entity_marker_position(index: int) -> Vector2:
	match current_area_id:
		AREA_HUNTING_FOREST:
			return Vector2(880 + float(index % 2) * 80.0, 430 + float(index / 2) * 90.0)
		AREA_VILLAGE_ENTRANCE:
			return Vector2(860 + float(index % 2) * 70.0, 540 + float(index / 2) * 86.0)
		AREA_VILLAGE_MARKET:
			return Vector2(960 + float(index % 2) * 72.0, 520 + float(index / 2) * 90.0)
		_:
			return Vector2(940 + float(index % 2) * 72.0, 440 + float(index / 2) * 90.0)


func _format_inventory_summary(npc_id: String, inventory: Array) -> String:
	var parts: Array[String] = []
	for item in inventory:
		if typeof(item) != TYPE_DICTIONARY:
			continue
		parts.append("%s x%s" % [str(item.get("item_type", "")), str(item.get("quantity", 0))])
	return "%s inventory: %s" % [NPC_NAMES.get(npc_id, npc_id), ", ".join(parts)]


func _render_economy_summary() -> void:
	var summary := _format_economy_summary()
	if summary == "" or summary == last_economy_summary:
		return
	last_economy_summary = summary
	_append_event_detail(summary)


func _format_economy_summary() -> String:
	var warehouse_parts: Array[String] = []
	var warehouse_count := 0
	for item in village_warehouse:
		if typeof(item) != TYPE_DICTIONARY:
			continue
		if warehouse_count >= 8:
			break
		warehouse_parts.append("%s x%s" % [
			str(item.get("item_type", "")),
			str(item.get("quantity", 0)),
		])
		warehouse_count += 1

	var order_parts: Array[String] = []
	var order_count := 0
	for order in production_orders:
		if typeof(order) != TYPE_DICTIONARY:
			continue
		if order_count >= 4:
			break
		order_parts.append("%s->%s x%s @t%s" % [
			str(order.get("order_type", "")),
			str(order.get("output_item_type", "")),
			str(order.get("output_quantity", 0)),
			str(order.get("completes_at_tick", "?")),
		])
		order_count += 1

	var transaction_parts: Array[String] = []
	var transaction_count := 0
	for transaction in warehouse_transactions:
		if typeof(transaction) != TYPE_DICTIONARY:
			continue
		if transaction_count >= 3:
			break
		var delta := int(transaction.get("quantity_delta", 0))
		var sign := "+" if delta > 0 else ""
		transaction_parts.append("[t%s] %s %s%s" % [
			str(transaction.get("created_at_tick", "?")),
			str(transaction.get("reason", "")),
			sign,
			str(delta),
		])
		transaction_count += 1

	var warehouse_text := ", ".join(warehouse_parts) if not warehouse_parts.is_empty() else "空"
	var order_text := ", ".join(order_parts) if not order_parts.is_empty() else "无待完成订单"
	var transaction_text := ", ".join(transaction_parts) if not transaction_parts.is_empty() else "暂无流水"
	return "经济状态\n仓库：%s\n生产：%s\n流水：%s" % [
		warehouse_text,
		order_text,
		transaction_text,
	]


func _format_world_update(world_update: Dictionary) -> String:
	var lines := ["world_update"]
	var refreshed: Variant = world_update.get("refreshed_resources", [])
	if typeof(refreshed) == TYPE_ARRAY and not refreshed.is_empty():
		lines.append("resources=%s" % JSON.stringify(refreshed))
	var matured: Variant = world_update.get("matured_production_order_ids", [])
	if typeof(matured) == TYPE_ARRAY and not matured.is_empty():
		lines.append("production_done=%s" % JSON.stringify(matured))
	var moved: Variant = world_update.get("moved_entity_ids", [])
	if typeof(moved) == TYPE_ARRAY and not moved.is_empty():
		lines.append("moved=%s" % JSON.stringify(moved))
	var generated: Variant = world_update.get("generated_event_ids", [])
	if typeof(generated) == TYPE_ARRAY and not generated.is_empty():
		lines.append("events=%s" % JSON.stringify(generated))
	var spawned: Variant = world_update.get("spawned_entity_ids", [])
	if typeof(spawned) == TYPE_ARRAY and not spawned.is_empty():
		lines.append("spawned=%s" % JSON.stringify(spawned))
	return "\n".join(lines)


func _format_task(task: Variant) -> String:
	if typeof(task) != TYPE_DICTIONARY or task.is_empty():
		return "无"
	return "%s | target=%s | location=%s | priority=%s" % [
		str(task.get("task_type", task.get("action_type", "idle"))),
		str(task.get("target_id", "-")),
		str(task.get("location_id", "-")),
		str(task.get("priority", "?")),
	]


func _format_thought(thought: Variant) -> String:
	if typeof(thought) != TYPE_DICTIONARY or thought.is_empty():
		return "没有额外思考结果。"
	var lines := [
		"主目标：%s" % str(thought.get("primary_goal", "")),
		"情绪：%s" % str(thought.get("emotional_state", "")),
		"风险倾向：%s" % str(thought.get("risk_attitude", "")),
	]
	var notes := str(thought.get("notes", "")).strip_edges()
	if notes != "":
		lines.append("备注：%s" % notes)
	return "\n".join(lines)


func _format_tick_results(npc_results: Variant) -> String:
	if typeof(npc_results) != TYPE_ARRAY or npc_results.is_empty():
		return "本轮没有 NPC 结果。"
	var lines: Array[String] = []
	for npc_result in npc_results:
		if typeof(npc_result) != TYPE_DICTIONARY:
			continue
		var npc_id := str(npc_result.get("npc_id", ""))
		lines.append(NPC_NAMES.get(npc_id, npc_id))
		var execution_result: Variant = npc_result.get("execution_result", {})
		var executed_task: Variant = {}
		if typeof(execution_result) == TYPE_DICTIONARY:
			executed_task = execution_result.get("executed_task", {})
		lines.append("  执行：%s" % _format_task(executed_task))
		var plan_result: Variant = npc_result.get("plan_result", {})
		if typeof(plan_result) == TYPE_DICTIONARY and not plan_result.is_empty():
			lines.append("  规划：%s" % _format_task(plan_result.get("selected_task", {})))
	return "\n".join(lines)


func _format_tick_profile(profile: Variant) -> String:
	if typeof(profile) != TYPE_DICTIONARY or profile.is_empty():
		return "本轮没有 profile 数据。"
	return "总耗时：%sms\n执行阶段：%sms\n规划阶段：%sms\n计划 NPC：%s\n最慢 NPC：%s" % [
		str(profile.get("total_ms", "?")),
		str(profile.get("execution_phase_ms", "?")),
		str(profile.get("planning_phase_ms", "?")),
		str(profile.get("planned_npc_ids", [])),
		str(profile.get("slowest_npc_id", "-")),
	]
