# AI Panel Studio — API 文档

> 版本：V1.0 | 协议：REST + SSE | 通信格式：JSON

---

## 基础约定

- **Base URL**：`http://localhost:8000/api`
- **请求体**：`Content-Type: application/json`
- **响应体**：`Content-Type: application/json`
- **SSE 端点**：`Content-Type: text/event-stream`
- **错误响应**：
```json
{
  "error": {
    "code": "DISCUSSION_NOT_FOUND",
    "message": "讨论不存在"
  }
}
```

---

## 1. 讨论管理

### 1.1 获取讨论列表

```
GET /api/discussions
```

**Query 参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| status | string | — | 筛选状态：draft / lineup_ready / running / paused / ended |
| limit | integer | 20 | 返回数量上限 |
| offset | integer | 0 | 分页偏移 |

**响应 200**：
```json
{
  "discussions": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "topic": "AI 是否应该拥有法律人格？",
      "status": "running",
      "max_rounds": 12,
      "current_round": 5,
      "panelist_count": 5,
      "created_at": "2026-07-05T10:00:00+08:00",
      "updated_at": "2026-07-05T10:15:30+08:00"
    }
  ],
  "total": 1
}
```

---

### 1.2 创建新讨论

```
POST /api/discussions
```

**请求体**：
```json
{
  "topic": "AI 是否应该拥有法律人格？",
  "expert_count": 4,
  "max_rounds": 12
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| topic | string | 是 | — | 讨论话题 |
| expert_count | integer | 否 | 4 | 专家人数（1-8） |
| max_rounds | integer | 否 | 12 | 最大讨论轮次（4-30） |

**响应 201**：
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "topic": "AI 是否应该拥有法律人格？",
  "status": "draft",
  "max_rounds": 12,
  "expert_count": 4,
  "created_at": "2026-07-05T10:00:00+08:00"
}
```

---

### 1.3 获取讨论详情

```
GET /api/discussions/{id}
```

**响应 200**：
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "topic": "AI 是否应该拥有法律人格？",
  "status": "running",
  "max_rounds": 12,
  "current_round": 5,
  "total_utterances": 28,
  "created_at": "2026-07-05T10:00:00+08:00",
  "updated_at": "2026-07-05T10:15:30+08:00"
}
```

---

### 1.4 删除讨论

```
DELETE /api/discussions/{id}
```

**约束**：仅 `ended` 状态的讨论可删除。

**响应 200**：
```json
{
  "deleted": true
}
```

---

## 2. 嘉宾阵容

### 2.1 生成阵容

```
POST /api/discussions/{id}/panel/generate
```

**请求体**：
```json
{
  "expert_count": 4
}
```

系统调用大模型生成 1 名主持人 + N 名专家，写入数据库。

**响应 201**：
```json
{
  "panel": [
    {
      "id": "uuid-moderator",
      "role": "moderator",
      "name": "陈锐",
      "occupation": "资深媒体人",
      "title": "《前沿对话》主持人",
      "stance": "中立，擅长引导多视角辩论",
      "color": "#4A90D9",
      "sort_order": 0
    },
    {
      "id": "uuid-expert-1",
      "role": "expert",
      "name": "林芳",
      "occupation": "法学教授",
      "title": "北京大学法学院",
      "stance": "倾向于支持 AI 有限法律人格",
      "color": "#E57373",
      "sort_order": 1
    }
  ]
}
```

---

### 2.2 获取阵容

```
GET /api/discussions/{id}/panel
```

**响应 200**：
```json
{
  "panel": [ /* 同上结构，按 sort_order 排列 */ ]
}
```

---

### 2.3 编辑嘉宾

```
PUT /api/discussions/{id}/panel/{panelist_id}
```

**请求体**（所有字段可选，只传要修改的）：
```json
{
  "name": "林芳（修改后）",
  "occupation": "法学教授",
  "title": "清华大学法学院",
  "stance": "倾向于全面支持 AI 法律人格",
  "color": "#C62828"
}
```

**响应 200**：
```json
{
  "id": "uuid-expert-1",
  "role": "expert",
  "name": "林芳（修改后）",
  "occupation": "法学教授",
  "title": "清华大学法学院",
  "stance": "倾向于全面支持 AI 法律人格",
  "color": "#C62828",
  "sort_order": 1
}
```

---

### 2.4 删除专家

```
DELETE /api/discussions/{id}/panel/{panelist_id}
```

**约束**：不可删除主持人（role = moderator）。

**响应 200**：
```json
{
  "deleted": true
}
```

---

### 2.5 手动新增专家

```
POST /api/discussions/{id}/panel
```

**请求体**：
```json
{
  "name": "张伟",
  "occupation": "AI 伦理研究员",
  "title": "某科技公司伦理委员会",
  "stance": "反对赋予 AI 任何法律人格",
  "color": "#81C784"
}
```

**响应 201**：
```json
{
  "id": "uuid-new-expert",
  "role": "expert",
  "name": "张伟",
  "occupation": "AI 伦理研究员",
  "title": "某科技公司伦理委员会",
  "stance": "反对赋予 AI 任何法律人格",
  "color": "#81C784",
  "sort_order": 5
}
```

---

### 2.6 单独重新生成一位专家

```
POST /api/discussions/{id}/panel/{panelist_id}/regenerate
```

系统调用大模型重新生成该专家的全部字段，保持 `role` 和 `sort_order` 不变。

**响应 200**：
```json
{
  "id": "uuid-expert-1",
  "role": "expert",
  "name": "王雪（重新生成）",
  "occupation": "科技政策研究员",
  "title": "中国科学院",
  "stance": "关注 AI 法律人格对社会治理的冲击",
  "color": "#FFB74D",
  "sort_order": 1
}
```

---

## 3. 讨论控制

### 3.1 开始讨论

```
POST /api/discussions/{id}/start
```

**前置条件**：讨论状态为 `lineup_ready`（阵容已确认）。

**响应 202**：
```json
{
  "status": "running",
  "started_at": "2026-07-05T10:05:00+08:00"
}
```

> 讨论引擎在后台异步启动。前端应立即连接到 SSE 流以接收事件。

---

### 3.2 暂停讨论

```
POST /api/discussions/{id}/pause
```

**响应 200**：
```json
{
  "status": "paused"
}
```

---

### 3.3 恢复讨论

```
POST /api/discussions/{id}/resume
```

**响应 200**：
```json
{
  "status": "running"
}
```

---

### 3.4 用户插入追问

```
POST /api/discussions/{id}/interject
```

**请求体**：
```json
{
  "message": "我注意到专家们忽略了数据隐私方面的讨论，能否请主持人引导一下这个话题？"
}
```

**响应 202**：
```json
{
  "accepted": true,
  "message": "追问已提交，主持人将在下一轮中引导讨论"
}
```

> 用户追问在引擎内部排队。主持人将在下一触发周期优先处理用户追问。

---

### 3.5 手动结束讨论

```
POST /api/discussions/{id}/end
```

引擎将触发主持人进行收尾总结，总结完成后状态变为 `ended`。

**响应 202**：
```json
{
  "status": "ending",
  "message": "主持人正在进行收尾总结…"
}
```

---

## 4. SSE 事件流

### 4.1 连接流

```
GET /api/discussions/{id}/stream
```

**响应头**：
```
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
```

### 4.2 事件类型

#### `utterance` — 新发言

```
event: utterance
data: {
  "id": "uuid-utt-001",
  "discussion_id": "550e8400-...",
  "panelist_id": "uuid-expert-1",
  "panelist": {
    "name": "林芳",
    "occupation": "法学教授",
    "title": "北京大学法学院",
    "color": "#E57373",
    "role": "expert"
  },
  "type": "rebuttal",
  "content": "陈教授提到了经济效益优先，但我必须指出，如果我们仅仅从经济角度衡量 AI 的法律地位，那本质上是在走欧洲殖民时期将人视为财产的老路。",
  "round": 5,
  "seq": 28,
  "created_at": "2026-07-05T10:16:00+08:00"
}
```

#### `panelist_state` — 专家状态变更

```
event: panelist_state
data: {
  "panelist_id": "uuid-expert-1",
  "panelist_name": "林芳",
  "status": "preparing",
  "focus": "正在思考数据隐私与 AI 法律人格的关系…"
}
```

| status 值 | 说明 |
|-----------|------|
| `idle` | 待机，等待被调度选中 |
| `preparing` | 被调度选中，正在生成发言内容 |
| `speaking` | 发言已生成，正在前端展示 |

#### `insight_update` — 共识/分歧更新

```
event: insight_update
data: {
  "type": "divergence",
  "action": "new",
  "insight": {
    "id": "uuid-insight-003",
    "content": "专家在"AI 法律人格是否应类比公司法人"这一问题上存在根本分歧",
    "version": 1,
    "source_utterance_ids": ["uuid-utt-025", "uuid-utt-028"]
  }
}
```

`action` 值：
- `new` — 新增一条共识/分歧
- `update` — 已有条目版本更新（合并到之前的条目）

#### `moderating` — 主持人介入提示

```
event: moderating
data: {
  "trigger": "round_interval",
  "message": "主持人正在串联第 4 轮讨论…"
}
```

`trigger` 值：
- `round_interval` — 每 3-4 轮专家发言后的串联
- `silence` — 检测到冷场
- `off_topic` — 检测到跑题
- `user_interjection` — 用户插入追问
- `closing` — 即将收尾

#### `discussion_ended` — 讨论结束

```
event: discussion_ended
data: {
  "discussion_id": "550e8400-...",
  "summary": "本次讨论中，专家们围绕 AI 法律人格问题展开了激烈辩论。林芳教授从法理角度主张有限人格…然而在具体权利边界上，专家们未能达成一致…",
  "total_rounds": 12,
  "total_utterances": 52,
  "ended_at": "2026-07-05T11:30:00+08:00"
}
```

#### `heartbeat` — 心跳

```
event: heartbeat
data: {"timestamp": "2026-07-05T10:16:30+08:00"}
```

> 每 30 秒发送一次，用于保持连接并检测断连。

---

## 5. 查询

### 5.1 获取共识/分歧列表

```
GET /api/discussions/{id}/insights
```

**响应 200**：
```json
{
  "consensus": [
    {
      "id": "uuid-insight-001",
      "type": "consensus",
      "content": "专家一致认为当前法律体系尚未准备好应对 AI 带来的挑战",
      "version": 2,
      "source_utterance_ids": ["uuid-utt-003", "uuid-utt-007", "uuid-utt-012"],
      "created_at": "2026-07-05T10:10:00+08:00",
      "updated_at": "2026-07-05T10:20:00+08:00"
    }
  ],
  "divergence": [
    {
      "id": "uuid-insight-002",
      "type": "divergence",
      "content": "在 AI 是否应拥有财产权的问题上存在根本分歧",
      "version": 1,
      "source_utterance_ids": ["uuid-utt-005", "uuid-utt-009"],
      "created_at": "2026-07-05T10:12:00+08:00",
      "updated_at": "2026-07-05T10:12:00+08:00"
    }
  ]
}
```

---

### 5.2 获取完整 Transcript

```
GET /api/discussions/{id}/transcript
```

**Query 参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| limit | integer | 100 | 返回数量上限 |
| offset | integer | 0 | 分页偏移（按 seq 排序） |
| after_seq | integer | — | 仅返回 seq > N 的记录（增量拉取） |

**响应 200**：
```json
{
  "transcript": [
    {
      "id": "uuid-utt-001",
      "seq": 1,
      "round": 1,
      "panelist": {
        "id": "uuid-moderator",
        "name": "陈锐",
        "occupation": "资深媒体人",
        "title": "《前沿对话》主持人",
        "color": "#4A90D9",
        "role": "moderator"
      },
      "type": "opening",
      "content": "大家好，欢迎来到《前沿对话》。今天我们讨论的话题是…",
      "created_at": "2026-07-05T10:05:00+08:00"
    }
  ],
  "total": 52
}
```

---

## 6. 错误码

| HTTP 状态码 | code | 说明 |
|-------------|------|------|
| 400 | `INVALID_REQUEST` | 请求参数不合法 |
| 404 | `DISCUSSION_NOT_FOUND` | 讨论不存在 |
| 404 | `PANELIST_NOT_FOUND` | 嘉宾不存在 |
| 409 | `INVALID_STATE` | 当前状态不允许该操作 |
| 422 | `PANEL_NOT_READY` | 阵容未就绪，无法开始讨论 |
| 422 | `EXPERT_COUNT_INVALID` | 专家人数不在 1-8 范围内 |
| 500 | `INTERNAL_ERROR` | 服务器内部错误 |
| 502 | `LLM_ERROR` | 大模型调用失败 |
