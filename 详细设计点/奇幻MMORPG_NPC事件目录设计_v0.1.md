# 奇幻 MMORPG NPC 事件目录设计 v0.1

## 设计目标

NPC 事件目录不是为了记录世界里发生的一切，而是为了定义“哪些事情值得 NPC 感知、记住、传播，并影响后续行为”。

第一版事件系统应服务于这条链路：

```text
世界事件
  -> EventRouter 筛选接收 NPC
  -> MemorySummarizer 生成记忆
  -> FallbackRules / LLM Thought 影响行为倾向
  -> 行为结果回写关系、记忆、世界状态
```

因此，事件类型应优先覆盖会改变 NPC 决策的场景，而不是追求完整模拟整个世界。

## 设计原则

1. 事件结构固定，事件类型可逐步扩展。
2. 核心事件类型应尽量预定义，避免 Godot、SQLite、Python 各写各的字符串。
3. 第一版事件目录控制在 15 到 20 个以内。
4. 每个事件类型至少说明：
   - 触发场景
   - 主要接收 NPC
   - 记忆重要度倾向
   - 可能影响的行为或关系
5. 不要让事件默认广播给所有 NPC。事件应先经过路由，再进入记忆总结。

## 当前固定任务设计约束

后续新增事件、任务和 NPC 行为时，必须遵循以下流程。

### 1. 事件必须分类存储

事件目录不再把每个具体变体都拆成独立类型，而是采用：

```text
event_type + category + template_key + payload
```

其中：

```text
event_type
  代表稳定的规则入口，例如 monster_appeared、suspicious_arrival、player_stole。

category
  代表上层类别，例如 monster_incursion、suspicious_activity、player_misconduct。

template_key
  代表摘要和展示模板。

payload
  存储具体差异，例如怪物种类、数量、威胁等级、目击者、物品、价格、原因。
```

例如“怪物入侵”不应新增 `wolf_invasion`、`goblin_invasion`、`orc_invasion` 等事件类型，而应使用：

```json
{
  "event_type": "monster_appeared",
  "payload": {
    "monster_kind": "wolf",
    "monster_id": "monster_wolf_pack_001",
    "count": 3,
    "severity": "medium",
    "entry_point": "north_gate"
  }
}
```

要改变入侵内容，只改 payload，不改事件处理流程。

### 2. 每类事件必须定义职业默认处理流程

每个事件类型必须在事件目录中声明不同职业的默认响应。默认响应是底层兜底规则，目的是保证普通 NPC 在没有大模型思考时也能表现合理。

```text
monster_incursion:
  guard -> patrol / secure_area
  hunter -> hunt
  merchant -> flee / protect_goods
  villager -> flee

suspicious_activity:
  guard -> investigate
  merchant -> report_to_guard
  hunter -> low_priority_patrol

resource_pressure:
  merchant -> trade / allocate_supply
  hunter -> gather / hunt
  guard -> maintain_order

player_misconduct:
  guard -> investigate / confront
  merchant -> report_to_guard / refuse_trade
  villager -> flee / avoid_player
```

这些默认流程应进入 `task_queue`，并标记来源为：

```text
source: event
```

### 3. 默认规则是兜底，不是最终智能

事件默认流程只保证世界不沉默。它不应该替代重要 NPC 的思考。

最终行为优先级：

```text
客观 world_event
  -> EventRouter 路由给相关 NPC
  -> 写入记忆
  -> 写入职业默认响应任务
  -> 普通 NPC 可直接按默认任务行动
  -> 关键 NPC / 高价值场景进入 fallback/thought 或 LLM thought
  -> ActionPlanner 决定是否打断、排队、替换或忽略
  -> TaskExecutor 执行行为并回写结果
```

换句话说：

- 普通 NPC：默认规则足够时直接行动。
- 关键 NPC：默认规则只是候选背景，最终应通过思考决策。
- 大模型输出只能产生倾向或候选行动，最终仍由 ActionPlanner 规则层裁决。

### 4. 玩家话语不直接创建 world_event

玩家话语仍然只进入：

```text
player_utterance -> DialogueInterpreter/LLM -> credibility -> npc_belief -> thought/action
```

玩家话语接口可以返回 `npc_reply` 供前端展示连续对话，也可以在可信度足够时生成目标 NPC 自己的 `npc_belief`。无论由规则还是模型解释，都不能直接创建 `world_event`。

如果商人听到“村口有可疑陌生人”，最终稿中合理链路应是：

```text
玩家告诉商人
  -> 商人形成 unverified belief
  -> 商人 thought/fallback 判断这属于安全情报
  -> 商人生成 report 任务
  -> 商人执行 report，把消息交给守卫
  -> 守卫形成自己的 unverified belief
  -> 守卫 thought/fallback 决定 investigate
  -> 调查 objective world_event 或地点证据
  -> belief confirmed / disproven
```

不能在 dialogue_processor 中直接把商人的玩家话语硬编码转发给守卫。那只能作为临时原型，不是最终结构。

### 5. 新增事件时必须补齐的任务项

每次新增一个事件类型，必须同时完成：

```text
1. 在 event_catalog.py 中定义 EventDefinition。
2. 填写 category。
3. 填写 template_key。
4. 填写 payload_fields。
5. 填写 routing_roles。
6. 填写 summary_template。
7. 填写 default_role_responses。
8. 明确是否影响 relationship_delta。
9. 补测试：
   - 事件分类
   - payload 归一化
   - 路由结果
   - 默认职业任务
   - 记忆摘要
10. 如需 Godot 可视化，补 Godot 事件按钮或场景触发器。
```

没有默认职业响应的事件，应明确写空，并说明为什么该事件只记忆、不触发任务。

## 推荐事件结构

```json
{
  "event_id": "evt_monster_gate_001",
  "event_type": "monster_appeared",
  "actor_id": "monster_wolf_001",
  "target_id": null,
  "location_id": "village_gate",
  "payload": {},
  "importance": 60,
  "created_at_tick": 140
}
```

字段说明：

```text
event_id
  事件唯一 ID。

event_type
  事件类型。第一版建议从下方核心事件目录中选。

actor_id
  主动发起者。可以是 NPC、玩家、怪物、阵营、系统。

target_id
  被影响对象。可以为空。

location_id
  事件发生地点。

payload
  补充信息，例如 related_ids、resource_type、amount、faction_id。
  当前实现会自动补入 _category、_template、_payload_fields，供调试台和后续工具识别。

importance
  事件原始重要度，0 到 100。

created_at_tick
  事件发生时的世界 tick。
```

## 第一版核心事件目录

### 生存威胁类

#### monster_appeared

怪物出现在某个地点。

主要接收 NPC：

```text
同地点 NPC
guard
hunter
关键 NPC，若 importance 足够高
```

用途：

```text
护卫进入警戒或战斗
猎人前往调查
普通 NPC 产生恐惧或逃离倾向
地点被标记为危险
```

#### npc_attacked

NPC 遭到攻击。

主要接收 NPC：

```text
攻击者
受害者
同地点 NPC
guard
与受害者有关系的 NPC
```

用途：

```text
受害者产生敌意或恐惧
护卫介入
朋友或盟友传播消息
```

#### npc_injured

NPC 受伤。

主要接收 NPC：

```text
受伤 NPC
同地点 NPC
朋友、护卫、治疗者
```

用途：

```text
触发求助
改变后续行动优先级
影响关系和职责行为
```

#### danger_cleared

某个地点的威胁被清除。

主要接收 NPC：

```text
同地点 NPC
guard
hunter
受该地点影响的 NPC
```

用途：

```text
降低恐惧
允许 NPC 恢复日常行动
修正地点危险记忆
```

### 资源与经济类

#### food_shortage

食物短缺。

主要接收 NPC：

```text
merchant
hunter
guard
受影响地点 NPC
```

用途：

```text
商人调整交易态度
猎人倾向狩猎或采集
村民求助
饥饿 NPC 更容易中断当前任务
```

#### resource_found

发现资源。

主要接收 NPC：

```text
发现者
同地点 NPC
相关职业 NPC
```

用途：

```text
触发采集、交易、争夺
形成地点价值记忆
```

#### trade_completed

交易完成。

主要接收 NPC：

```text
交易双方
merchant
相关旁观者
```

用途：

```text
提高交易信任
形成短期经济记忆
```

#### trade_refused

交易被拒绝。

主要接收 NPC：

```text
交易双方
merchant
关系相关 NPC
```

用途：

```text
降低信任或好感
影响后续交易意愿
```

### 社交互动类

#### help_given

一方帮助另一方。

主要接收 NPC：

```text
帮助者
被帮助者
同地点旁观者
双方关系对象
```

用途：

```text
提升 favor / trust
增加合作倾向
形成正面记忆
```

#### help_refused

一方拒绝帮助另一方。

主要接收 NPC：

```text
请求者
拒绝者
同地点旁观者
双方关系对象
```

用途：

```text
降低 favor / trust
略微增加 hostility
影响后续求助意愿
```

#### rumor_spread

传闻传播。

主要接收 NPC：

```text
传闻发起者
接收者
与传闻对象有关系的 NPC
```

用途：

```text
让非现场 NPC 间接获得信息
制造二手记忆
改变声望和阵营态度
```

### 玩家声望类

#### player_helped

玩家帮助了某个 NPC 或地点。

主要接收 NPC：

```text
被帮助者
同地点 NPC
关系对象
关键 NPC
```

用途：

```text
提升 trust / favor
让 NPC 更愿意交易、求助、透露信息
```

#### player_harmed

玩家伤害了某个 NPC。

主要接收 NPC：

```text
受害者
同地点 NPC
guard
受害者关系对象
关键 NPC
```

用途：

```text
提高 hostility
触发护卫响应
让商人或村民更谨慎
```

#### player_stole

玩家偷窃。

主要接收 NPC：

```text
受害者
guard
merchant
同地点 NPC
```

用途：

```text
降低信任
触发追捕或拒绝交易
影响区域声望
```

### 地点与世界状态类

#### area_became_dangerous

地点变得危险。

主要接收 NPC：

```text
当前地点 NPC
常驻该地点 NPC
guard
hunter
关键 NPC
```

用途：

```text
改变路径选择
减少普通 NPC 活动
提高逃离和巡逻倾向
```

## 可选奇幻增强事件

这些事件可以在第一版核心链路跑通后加入。

#### magic_anomaly_detected

检测到魔法异常。

主要接收 NPC：

```text
法师
祭司
护卫
关键 NPC
同地点 NPC
```

用途：

```text
触发调查
引发恐慌或好奇
影响地点危险度
```

#### curse_spread

诅咒传播。

主要接收 NPC：

```text
受影响者
治疗者
祭司
guard
关键 NPC
```

用途：

```text
触发避险
触发求助
改变村庄状态
```

#### artifact_discovered

发现神器或遗物。

主要接收 NPC：

```text
发现者
学者
法师
商人
相关阵营 NPC
```

用途：

```text
触发争夺、交易、研究或护送任务
```

## 建议第一版事件清单

第一版先实现这些：

```text
monster_appeared
npc_attacked
npc_injured
danger_cleared
food_shortage
resource_found
trade_completed
trade_refused
help_given
help_refused
rumor_spread
player_helped
player_harmed
player_stole
area_became_dangerous
```

如果想更快体现奇幻风格，再加入：

```text
magic_anomaly_detected
curse_spread
artifact_discovered
```

## 后续扩展方向

```text
event_catalog.py
  把事件类型、category、payload_fields、默认 importance、默认 lifetime、路由职业、摘要模板、职业默认响应任务集中配置。

event_types.md
  给策划或后续设计使用的人类可读事件目录。

relationship_effects.py
  将事件转化为 favor / trust / hostility 的长期变化。

location_state.py
  将 area_became_dangerous 等事件转化为地点状态。
```

当前代码已将本目录升级为机器可读事件目录的第一版：EventRouter、MemorySummarizer、EventProcessor 共用 `event_catalog.py`。后续扩展事件时应优先改事件目录，而不是在路由、记忆、任务执行中散落新增 if/else。
