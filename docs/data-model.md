# AI Panel Studio — 数据建模文档

> 版本：V1.0 | 数据库：SQLite | 字符集：UTF-8

---

## 1. 实体定义

### 1.1 Discussion（讨论会话）

用户发起的一次完整圆桌讨论。

| 字段 | 类型 | 必填 | 默认值 | 约束 | 说明 |
|------|------|------|--------|------|------|
| `id` | TEXT | 是 | — | PK, UUID v4 | 讨论唯一标识 |
| `topic` | TEXT | 是 | — | 长度 2–200 | 讨论话题 |
| `status` | TEXT | 是 | `'draft'` | CHECK IN (draft, lineup_ready, running, paused, ended) | 讨论生命周期状态 |
| `max_rounds` | INTEGER | 是 | `12` | CHECK 4–30 | 最大讨论轮次 |
| `current_round` | INTEGER | 是 | `0` | CHECK ≥ 0 | 当前已完成的轮次 |
| `created_at` | TEXT | 是 | — | ISO 8601 | 创建时间 |
| `updated_at` | TEXT | 是 | — | ISO 8601 | 最后更新时间 |

**状态机：**

```
draft → lineup_ready → running ⇄ paused
                           ↓
                         ended
```

---

### 1.2 Panelist（嘉宾，含主持人）

参与讨论的每一位角色，包括 1 名主持人及 N 名专家。

| 字段 | 类型 | 必填 | 默认值 | 约束 | 说明 |
|------|------|------|--------|------|------|
| `id` | TEXT | 是 | — | PK, UUID v4 | 嘉宾唯一标识 |
| `discussion_id` | TEXT | 是 | — | FK → discussions(id) ON DELETE CASCADE | 所属讨论 |
| `role` | TEXT | 是 | — | CHECK IN ('moderator', 'expert') | 角色类型 |
| `name` | TEXT | 是 | — | 长度 1–50 | 姓名 |
| `occupation` | TEXT | 是 | — | 长度 1–100 | 职业 |
| `title` | TEXT | 是 | — | 长度 1–100 | 头衔/职称 |
| `stance` | TEXT | 是 | — | 长度 1–200 | 立场描述 |
| `color` | TEXT | 是 | — | HEX 颜色 #RRGGBB | 专属颜色标识 |
| `sort_order` | INTEGER | 是 | — | CHECK ≥ 0，same discussion_id 内唯一 | 排列顺序 |
| `created_at` | TEXT | 是 | — | ISO 8601 | 创建时间 |

**约束**：每个 discussion 有且仅有 1 名 role='moderator' 的 Panelist。

---

### 1.3 Utterance（发言记录）

讨论中产生的每一条发言，记录完整自然语言内容。

| 字段 | 类型 | 必填 | 默认值 | 约束 | 说明 |
|------|------|------|--------|------|------|
| `id` | TEXT | 是 | — | PK, UUID v4 | 发言唯一标识 |
| `discussion_id` | TEXT | 是 | — | FK → discussions(id) ON DELETE CASCADE | 所属讨论 |
| `panelist_id` | TEXT | 是 | — | FK → panelists(id) ON DELETE CASCADE | 发言人 |
| `type` | TEXT | 是 | — | CHECK IN (opening, main, supplement, rebuttal, moderator_interjection, closing) | 发言类型 |
| `content` | TEXT | 是 | — | 长度 ≥ 1 | 自然语言发言内容 |
| `round` | INTEGER | 是 | — | CHECK ≥ 1 | 所属轮次号 |
| `seq` | INTEGER | 是 | — | CHECK ≥ 1，same discussion_id 内自增 | 全局序号 |
| `created_at` | TEXT | 是 | — | ISO 8601 | 发言时间 |

**发言类型枚举说明：**

| 值 | 发言人 | 含义 |
|----|--------|------|
| `opening` | 主持人 | 开场白，介绍话题与嘉宾 |
| `main` | 专家 | 发表新观点 |
| `supplement` | 专家 | 补充另一位专家的观点 |
| `rebuttal` | 专家 | 反驳另一位专家的观点 |
| `moderator_interjection` | 主持人 | 串联、追问、纠偏 |
| `closing` | 主持人 | 收尾总结 |

---

### 1.4 Consensus（共识点）

讨论中专家达成的共识，由 LLM 从发言内容中增量提取。

| 字段 | 类型 | 必填 | 默认值 | 约束 | 说明 |
|------|------|------|--------|------|------|
| `id` | TEXT | 是 | — | PK, UUID v4 | 共识唯一标识 |
| `discussion_id` | TEXT | 是 | — | FK → discussions(id) ON DELETE CASCADE | 所属讨论 |
| `content` | TEXT | 是 | — | 长度 ≥ 1 | 共识描述内容 |
| `source_utterance_ids` | TEXT | 是 | `'[]'` | JSON array of UUID strings | 支撑该共识的发言 ID 列表 |
| `version` | INTEGER | 是 | `1` | CHECK ≥ 1 | 版本号，增量合并时递增 |
| `created_at` | TEXT | 是 | — | ISO 8601 | 首次识别时间 |
| `updated_at` | TEXT | 是 | — | ISO 8601 | 最后更新时间 |

---

### 1.5 Divergence（分歧点）

讨论中专家之间的分歧，包含对立双方立场。由 LLM 从发言内容中增量提取。

| 字段 | 类型 | 必填 | 默认值 | 约束 | 说明 |
|------|------|------|--------|------|------|
| `id` | TEXT | 是 | — | PK, UUID v4 | 分歧唯一标识 |
| `discussion_id` | TEXT | 是 | — | FK → discussions(id) ON DELETE CASCADE | 所属讨论 |
| `content` | TEXT | 是 | — | 长度 ≥ 1 | 分歧描述内容 |
| `opposing_sides` | TEXT | 是 | `'[]'` | JSON array，每项为 `{ "side": "立场描述", "panelist_ids": ["uuid"] }` | 对立方及其所持立场 |
| `source_utterance_ids` | TEXT | 是 | `'[]'` | JSON array of UUID strings | 支撑该分歧的发言 ID 列表 |
| `version` | INTEGER | 是 | `1` | CHECK ≥ 1 | 版本号，增量合并时递增 |
| `created_at` | TEXT | 是 | — | ISO 8601 | 首次识别时间 |
| `updated_at` | TEXT | 是 | — | ISO 8601 | 最后更新时间 |

**opposing_sides 示例：**
```json
[
  { "side": "AI 应拥有有限法律人格，类比公司法人", "panelist_ids": ["uuid-1", "uuid-3"] },
  { "side": "AI 是工具，不应拥有任何法律人格", "panelist_ids": ["uuid-2"] }
]
```

---

### 1.6 PanelistState（专家实时状态）

运行时高频读写的专家状态，同时持久化以支持崩溃恢复。

| 字段 | 类型 | 必填 | 默认值 | 约束 | 说明 |
|------|------|------|--------|------|------|
| `panelist_id` | TEXT | 是 | — | PK, FK → panelists(id) ON DELETE CASCADE | 关联嘉宾 |
| `discussion_id` | TEXT | 是 | — | FK → discussions(id) ON DELETE CASCADE | 所属讨论 |
| `status` | TEXT | 是 | `'idle'` | CHECK IN ('idle', 'preparing', 'speaking') | 当前状态 |
| `focus` | TEXT | 否 | `NULL` | — | 当前关注点 / 公开思考摘要（不暴露隐藏 CoT） |
| `updated_at` | TEXT | 是 | — | ISO 8601 | 最后更新时间 |

---

## 2. ER 图

```mermaid
erDiagram
    Discussion ||--o{ Panelist : "has"
    Discussion ||--o{ Utterance : "contains"
    Discussion ||--o{ Consensus : "yields"
    Discussion ||--o{ Divergence : "yields"
    Discussion ||--o{ PanelistState : "tracks"

    Panelist ||--o{ Utterance : "speaks"
    Panelist ||--|| PanelistState : "owns state"

    Utterance }o--o{ Consensus : "supports"
    Utterance }o--o{ Divergence : "supports"

    Discussion {
        TEXT id PK "UUID"
        TEXT topic "话题"
        TEXT status "draft→lineup_ready→running→paused→ended"
        INTEGER max_rounds "默认12"
        INTEGER current_round "默认0"
        TEXT created_at
        TEXT updated_at
    }

    Panelist {
        TEXT id PK "UUID"
        TEXT discussion_id FK "CASCADE"
        TEXT role "moderator | expert"
        TEXT name
        TEXT occupation
        TEXT title
        TEXT stance
        TEXT color "#RRGGBB"
        INTEGER sort_order
        TEXT created_at
    }

    Utterance {
        TEXT id PK "UUID"
        TEXT discussion_id FK "CASCADE"
        TEXT panelist_id FK "CASCADE"
        TEXT type "opening|main|supplement|rebuttal|moderator_interjection|closing"
        TEXT content
        INTEGER round
        INTEGER seq "AUTO per discussion"
        TEXT created_at
    }

    Consensus {
        TEXT id PK "UUID"
        TEXT discussion_id FK "CASCADE"
        TEXT content
        TEXT source_utterance_ids "JSON array"
        INTEGER version "默认1"
        TEXT created_at
        TEXT updated_at
    }

    Divergence {
        TEXT id PK "UUID"
        TEXT discussion_id FK "CASCADE"
        TEXT content
        TEXT opposing_sides "JSON array"
        TEXT source_utterance_ids "JSON array"
        INTEGER version "默认1"
        TEXT created_at
        TEXT updated_at
    }

    PanelistState {
        TEXT panelist_id PK_FK "CASCADE"
        TEXT discussion_id FK "CASCADE"
        TEXT status "idle|preparing|speaking"
        TEXT focus "nullable"
        TEXT updated_at
    }
```

**基数关系：**

| 关系 | 基数 | 说明 |
|------|------|------|
| Discussion → Panelist | 1 : 2–9 | 每个讨论有 1 名主持人 + 1–8 名专家 |
| Discussion → Utterance | 1 : N | 每场讨论约有几十到上百条发言 |
| Discussion → Consensus | 1 : 0..N | 可能没有共识 |
| Discussion → Divergence | 1 : 0..N | 可能没有分歧 |
| Panelist → Utterance | 1 : N | 每位嘉宾可多次发言 |
| Panelist → PanelistState | 1 : 1 | 每个嘉宾有且仅有一个实时状态 |
| Utterance → Consensus | N : M | 一条发言可支撑多条共识，一条共识可由多条发言支撑 |
| Utterance → Divergence | N : M | 同上，通过 source_utterance_ids JSON 字段实现软关联 |

---

## 3. SQLite DDL

```sql
-- =================================================
-- AI Panel Studio — 数据库初始化 SQL
-- 引擎：SQLite 3.40+
-- 字符集：UTF-8
-- =================================================

-- 启用外键约束（SQLite 默认关闭）
PRAGMA foreign_keys = ON;

-- -------------------------------------------------
-- 讨论会话
-- -------------------------------------------------
CREATE TABLE discussions (
    id            TEXT NOT NULL PRIMARY KEY,
    topic         TEXT NOT NULL CHECK(length(topic) BETWEEN 2 AND 200),
    status        TEXT NOT NULL DEFAULT 'draft'
                  CHECK(status IN ('draft', 'lineup_ready', 'running', 'paused', 'ended')),
    max_rounds    INTEGER NOT NULL DEFAULT 12
                  CHECK(max_rounds BETWEEN 4 AND 30),
    current_round INTEGER NOT NULL DEFAULT 0
                  CHECK(current_round >= 0),
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE INDEX idx_discussions_status ON discussions(status);
CREATE INDEX idx_discussions_created_at ON discussions(created_at DESC);

-- -------------------------------------------------
-- 嘉宾（含主持人）
-- -------------------------------------------------
CREATE TABLE panelists (
    id            TEXT NOT NULL PRIMARY KEY,
    discussion_id TEXT NOT NULL,
    role          TEXT NOT NULL
                  CHECK(role IN ('moderator', 'expert')),
    name          TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 50),
    occupation    TEXT NOT NULL CHECK(length(occupation) BETWEEN 1 AND 100),
    title         TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 100),
    stance        TEXT NOT NULL CHECK(length(stance) BETWEEN 1 AND 200),
    color         TEXT NOT NULL CHECK(color GLOB '#[0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]'),
    sort_order    INTEGER NOT NULL CHECK(sort_order >= 0),
    created_at    TEXT NOT NULL,
    FOREIGN KEY (discussion_id) REFERENCES discussions(id) ON DELETE CASCADE,
    UNIQUE(discussion_id, sort_order)
);

CREATE INDEX idx_panelists_discussion ON panelists(discussion_id);
CREATE INDEX idx_panelists_role ON panelists(discussion_id, role);

-- -------------------------------------------------
-- 发言记录
-- -------------------------------------------------
CREATE TABLE utterances (
    id            TEXT NOT NULL PRIMARY KEY,
    discussion_id TEXT NOT NULL,
    panelist_id   TEXT NOT NULL,
    type          TEXT NOT NULL
                  CHECK(type IN ('opening', 'main', 'supplement', 'rebuttal', 'moderator_interjection', 'closing')),
    content       TEXT NOT NULL CHECK(length(content) >= 1),
    round         INTEGER NOT NULL CHECK(round >= 1),
    seq           INTEGER NOT NULL CHECK(seq >= 1),
    created_at    TEXT NOT NULL,
    FOREIGN KEY (discussion_id) REFERENCES discussions(id) ON DELETE CASCADE,
    FOREIGN KEY (panelist_id) REFERENCES panelists(id) ON DELETE CASCADE
);

CREATE INDEX idx_utterances_discussion ON utterances(discussion_id);
CREATE INDEX idx_utterances_panelist ON utterances(panelist_id);
CREATE INDEX idx_utterances_seq ON utterances(discussion_id, seq);
CREATE INDEX idx_utterances_round ON utterances(discussion_id, round);
CREATE INDEX idx_utterances_type ON utterances(discussion_id, type);

-- -------------------------------------------------
-- 共识点
-- -------------------------------------------------
CREATE TABLE consensus (
    id                   TEXT NOT NULL PRIMARY KEY,
    discussion_id        TEXT NOT NULL,
    content              TEXT NOT NULL CHECK(length(content) >= 1),
    source_utterance_ids TEXT NOT NULL DEFAULT '[]',  -- JSON array of UUIDs
    version              INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,
    FOREIGN KEY (discussion_id) REFERENCES discussions(id) ON DELETE CASCADE
);

CREATE INDEX idx_consensus_discussion ON consensus(discussion_id);
CREATE INDEX idx_consensus_version ON consensus(discussion_id, version);

-- -------------------------------------------------
-- 分歧点
-- -------------------------------------------------
CREATE TABLE divergences (
    id                   TEXT NOT NULL PRIMARY KEY,
    discussion_id        TEXT NOT NULL,
    content              TEXT NOT NULL CHECK(length(content) >= 1),
    opposing_sides       TEXT NOT NULL DEFAULT '[]',  -- JSON array of objects
    source_utterance_ids TEXT NOT NULL DEFAULT '[]',  -- JSON array of UUIDs
    version              INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,
    FOREIGN KEY (discussion_id) REFERENCES discussions(id) ON DELETE CASCADE
);

CREATE INDEX idx_divergences_discussion ON divergences(discussion_id);
CREATE INDEX idx_divergences_version ON divergences(discussion_id, version);

-- -------------------------------------------------
-- 专家实时状态
-- -------------------------------------------------
CREATE TABLE panelist_states (
    panelist_id   TEXT NOT NULL PRIMARY KEY,
    discussion_id TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'idle'
                  CHECK(status IN ('idle', 'preparing', 'speaking')),
    focus         TEXT,                         -- nullable
    updated_at    TEXT NOT NULL,
    FOREIGN KEY (panelist_id) REFERENCES panelists(id) ON DELETE CASCADE,
    FOREIGN KEY (discussion_id) REFERENCES discussions(id) ON DELETE CASCADE
);

CREATE INDEX idx_panelist_states_discussion ON panelist_states(discussion_id);
CREATE INDEX idx_panelist_states_status ON panelist_states(discussion_id, status);

-- -------------------------------------------------
-- 触发器：自动更新 discussion.updated_at
-- -------------------------------------------------
CREATE TRIGGER trg_discussions_updated
    AFTER UPDATE ON discussions
    FOR EACH ROW
BEGIN
    UPDATE discussions SET updated_at = datetime('now') WHERE id = OLD.id;
END;

-- 触发器：自动更新 consensus.updated_at
CREATE TRIGGER trg_consensus_updated
    AFTER UPDATE ON consensus
    FOR EACH ROW
BEGIN
    UPDATE consensus SET updated_at = datetime('now') WHERE id = OLD.id;
END;

-- 触发器：自动更新 divergences.updated_at
CREATE TRIGGER trg_divergences_updated
    AFTER UPDATE ON divergences
    FOR EACH ROW
BEGIN
    UPDATE divergences SET updated_at = datetime('now') WHERE id = OLD.id;
END;

-- 触发器：自动更新 panelist_states.updated_at
CREATE TRIGGER trg_panelist_states_updated
    AFTER UPDATE ON panelist_states
    FOR EACH ROW
BEGIN
    UPDATE panelist_states SET updated_at = datetime('now') WHERE panelist_id = OLD.panelist_id;
END;
```

---

## 4. RESTful API 契约

### 基础约定

| 项 | 值 |
|----|-----|
| Base URL | `http://localhost:8000/api` |
| 请求 Content-Type | `application/json` |
| 响应 Content-Type | `application/json` |
| SSE Content-Type | `text/event-stream` |
| 日期时间格式 | ISO 8601（带时区） |
| 统一错误响应体 | `{ "error": { "code": "...", "message": "..." } }` |

### 4.1 讨论管理

#### `GET /api/discussions`

获取讨论列表。

**Query 参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `status` | string | 否 | — | 筛选：draft \| lineup_ready \| running \| paused \| ended |
| `limit` | integer | 否 | 20 | 返回上限（1–100） |
| `offset` | integer | 否 | 0 | 分页偏移 |

**响应 200：**
```json
{
  "discussions": [
    {
      "id": "b1a2c3d4-...",
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

#### `POST /api/discussions`

创建新讨论。

**请求体：**
```json
{
  "topic": "AI 是否应该拥有法律人格？",
  "expert_count": 4,
  "max_rounds": 12
}
```

| 字段 | 类型 | 必填 | 默认值 | 校验 |
|------|------|------|--------|------|
| `topic` | string | 是 | — | 2–200 字符 |
| `expert_count` | integer | 否 | 4 | 1–8 |
| `max_rounds` | integer | 否 | 12 | 4–30 |

**响应 201：**
```json
{
  "id": "b1a2c3d4-...",
  "topic": "AI 是否应该拥有法律人格？",
  "status": "draft",
  "max_rounds": 12,
  "expert_count": 4,
  "created_at": "2026-07-05T10:00:00+08:00"
}
```

---

#### `GET /api/discussions/{discussion_id}`

获取讨论详情。

**响应 200：**
```json
{
  "id": "b1a2c3d4-...",
  "topic": "AI 是否应该拥有法律人格？",
  "status": "running",
  "max_rounds": 12,
  "current_round": 5,
  "total_utterances": 28,
  "created_at": "2026-07-05T10:00:00+08:00",
  "updated_at": "2026-07-05T10:15:30+08:00"
}
```

**错误响应 404：**
```json
{
  "error": {
    "code": "DISCUSSION_NOT_FOUND",
    "message": "讨论不存在"
  }
}
```

---

#### `DELETE /api/discussions/{discussion_id}`

删除讨论。仅 `ended` 状态可删除。

**响应 200：**
```json
{ "deleted": true }
```

**错误响应 409：**
```json
{
  "error": {
    "code": "INVALID_STATE",
    "message": "仅已结束的讨论可删除"
  }
}
```

---

### 4.2 嘉宾阵容

#### `POST /api/discussions/{discussion_id}/panel/generate`

生成主持人与专家阵容。

**请求体：**
```json
{
  "expert_count": 4
}
```

系统调用大模型生成 1 名主持人 + N 名专家，写入 panelists 表并覆盖已有阵容。

**响应 201：**
```json
{
  "panel": [
    {
      "id": "p1-...",
      "role": "moderator",
      "name": "陈锐",
      "occupation": "资深媒体人",
      "title": "《前沿对话》主持人",
      "stance": "中立，擅长引导多视角辩论",
      "color": "#4A90D9",
      "sort_order": 0
    },
    {
      "id": "p2-...",
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

#### `GET /api/discussions/{discussion_id}/panel`

获取阵容列表，按 sort_order 排列。

**响应 200：**
```json
{
  "panel": [ /* 同上结构 */ ]
}
```

---

#### `PUT /api/discussions/{discussion_id}/panel/{panelist_id}`

编辑单个嘉宾（所有字段可选，仅传需修改的字段）。

**请求体（PATCH 语义，部分更新）：**
```json
{
  "name": "林芳（已更新）",
  "stance": "调整为更强烈的支持立场",
  "color": "#C62828"
}
```

**响应 200：**
```json
{
  "id": "p2-...",
  "role": "expert",
  "name": "林芳（已更新）",
  "occupation": "法学教授",
  "title": "北京大学法学院",
  "stance": "调整为更强烈的支持立场",
  "color": "#C62828",
  "sort_order": 1
}
```

---

#### `DELETE /api/discussions/{discussion_id}/panel/{panelist_id}`

删除一位专家。不可删除 role='moderator' 的嘉宾。

**响应 200：**
```json
{ "deleted": true }
```

**错误响应 422：**
```json
{
  "error": {
    "code": "CANNOT_DELETE_MODERATOR",
    "message": "不可删除主持人"
  }
}
```

---

#### `POST /api/discussions/{discussion_id}/panel`

手动新增自定义专家。

**请求体：**
```json
{
  "name": "张伟",
  "occupation": "AI 伦理研究员",
  "title": "某科技公司伦理委员会",
  "stance": "反对赋予 AI 任何法律人格",
  "color": "#81C784"
}
```

**响应 201：**
```json
{
  "id": "p9-...",
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

#### `POST /api/discussions/{discussion_id}/panel/{panelist_id}/regenerate`

单独重新生成一位专家（保持 role 和 sort_order 不变）。

**响应 200：**
```json
{
  "id": "p2-...",
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

### 4.3 讨论控制

#### `POST /api/discussions/{discussion_id}/start`

开始讨论。前置条件：status = 'lineup_ready'（阵容已确认）。

**响应 202：**
```json
{
  "status": "running",
  "started_at": "2026-07-05T10:05:00+08:00"
}
```

> 引擎后台异步启动。前端应立刻连接 SSE 流。

---

#### `POST /api/discussions/{discussion_id}/pause`

暂停讨论。

**响应 200：**
```json
{ "status": "paused" }
```

---

#### `POST /api/discussions/{discussion_id}/resume`

恢复讨论。

**响应 200：**
```json
{ "status": "running" }
```

---

#### `POST /api/discussions/{discussion_id}/interject`

用户插入追问。

**请求体：**
```json
{
  "message": "专家们能否讨论一下数据隐私方面的考量？"
}
```

**响应 202：**
```json
{
  "accepted": true,
  "message": "追问已提交，主持人将在下一轮中引导讨论"
}
```

---

#### `POST /api/discussions/{discussion_id}/end`

手动结束讨论。引擎触发主持人收尾总结。

**响应 202：**
```json
{
  "status": "ending",
  "message": "主持人正在进行收尾总结…"
}
```

---

### 4.4 查询

#### `GET /api/discussions/{discussion_id}/consensus`

获取共识列表。

**响应 200：**
```json
{
  "items": [
    {
      "id": "c1-...",
      "content": "专家一致认为当前法律体系尚未准备好应对 AI 带来的挑战",
      "version": 2,
      "source_utterance_ids": ["u3-...", "u7-...", "u12-..."],
      "created_at": "2026-07-05T10:10:00+08:00",
      "updated_at": "2026-07-05T10:20:00+08:00"
    }
  ],
  "total": 3
}
```

---

#### `GET /api/discussions/{discussion_id}/divergences`

获取分歧列表。

**响应 200：**
```json
{
  "items": [
    {
      "id": "d1-...",
      "content": "在 AI 是否应拥有财产权的问题上存在根本分歧",
      "version": 1,
      "opposing_sides": [
        { "side": "AI 应拥有财产权以便独立承担责任", "panelist_ids": ["p2-...", "p4-..."] },
        { "side": "AI 作为工具不应拥有任何财产", "panelist_ids": ["p3-..."] }
      ],
      "source_utterance_ids": ["u5-...", "u9-..."],
      "created_at": "2026-07-05T10:12:00+08:00",
      "updated_at": "2026-07-05T10:12:00+08:00"
    }
  ],
  "total": 2
}
```

---

#### `GET /api/discussions/{discussion_id}/transcript`

获取完整 transcript（按 seq 排序）。

**Query 参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `limit` | integer | 否 | 100 | 1–500 |
| `offset` | integer | 否 | 0 | — |
| `after_seq` | integer | 否 | — | 增量拉取：仅返回 seq > N 的记录 |

**响应 200：**
```json
{
  "items": [
    {
      "id": "u1-...",
      "seq": 1,
      "round": 1,
      "panelist": {
        "id": "p1-...",
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

### 4.5 完整错误码

| HTTP 状态码 | code | 说明 |
|-------------|------|------|
| 400 | `INVALID_REQUEST` | 请求参数不合法或 JSON 解析失败 |
| 404 | `DISCUSSION_NOT_FOUND` | 讨论不存在 |
| 404 | `PANELIST_NOT_FOUND` | 嘉宾不存在 |
| 409 | `INVALID_STATE` | 当前讨论状态不允许此操作 |
| 422 | `PANEL_NOT_READY` | 阵容未就绪，无法开始讨论 |
| 422 | `EXPERT_COUNT_INVALID` | 专家人数不在 1–8 范围内 |
| 422 | `ROUNDS_INVALID` | 轮次不在 4–30 范围内 |
| 422 | `CANNOT_DELETE_MODERATOR` | 不可删除主持人 |
| 429 | `RATE_LIMITED` | 请求过于频繁 |
| 500 | `INTERNAL_ERROR` | 服务器内部错误 |
| 502 | `LLM_ERROR` | 大模型调用失败或超时 |
| 503 | `SERVICE_UNAVAILABLE` | 服务未就绪 |

---

## 5. SSE 事件类型枚举

### 5.1 连接

```
GET /api/discussions/{discussion_id}/stream
```

响应头：
```
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
```

### 5.2 事件定义

#### `panelist_status` — 专家状态变更

```
event: panelist_status
data: {
  "panelist_id": "p2-...",
  "panelist_name": "林芳",
  "role": "expert",
  "color": "#E57373",
  "status": "preparing",
  "focus": "正在思考数据隐私与 AI 法律人格的关系…"
}
```

| status 值 | 含义 | 前端表现 |
|-----------|------|----------|
| `idle` | 待机，等待调度 | 灰色指示，显示 focus 摘要 |
| `preparing` | 被调度选中，LLM 正在生成发言 | 脉冲动画，"正在组织观点…" |
| `speaking` | 发言已生成，正在展示 | 高亮闪烁 → 稳定，显示发言摘要 |

> **约束**：`focus` 字段仅包含公开思考摘要，不暴露真实 chain-of-thought。

---

#### `utterance` — 新发言

```
event: utterance
data: {
  "id": "u28-...",
  "discussion_id": "b1a2c3d4-...",
  "type": "rebuttal",
  "panelist": {
    "id": "p2-...",
    "name": "林芳",
    "occupation": "法学教授",
    "title": "北京大学法学院",
    "color": "#E57373",
    "role": "expert"
  },
  "content": "陈教授提到了经济效益优先，但我必须指出……",
  "round": 5,
  "seq": 28,
  "created_at": "2026-07-05T10:16:00+08:00"
}
```

---

#### `consensus_update` — 共识更新

```
event: consensus_update
data: {
  "action": "new",
  "consensus": {
    "id": "c3-...",
    "content": "专家一致认为，无论是否赋予法律人格，AI 的决策过程应保持可解释性",
    "version": 1,
    "source_utterance_ids": ["u25-...", "u28-..."]
  }
}
```

| action 值 | 含义 |
|-----------|------|
| `new` | 新增一条共识 |
| `update` | 已有共识版本更新（前后端应覆盖/合并显示） |

---

#### `divergence_update` — 分歧更新

```
event: divergence_update
data: {
  "action": "new",
  "divergence": {
    "id": "d2-...",
    "content": "专家在"AI 决策失误应由谁承担责任"的问题上存在根本分歧",
    "version": 1,
    "opposing_sides": [
      { "side": "责任应由 AI 开发者承担", "panelist_ids": ["p2-..."] },
      { "side": "责任应由使用 AI 的机构承担", "panelist_ids": ["p3-...", "p5-..."] }
    ],
    "source_utterance_ids": ["u22-...", "u26-..."]
  }
}
```

| action 值 | 含义 |
|-----------|------|
| `new` | 新增一条分歧 |
| `update` | 已有分歧版本更新 |

---

#### `summary` — 讨论总结

```
event: summary
data: {
  "discussion_id": "b1a2c3d4-...",
  "content": "本次讨论中，专家们围绕 AI 法律人格问题进行了深入交流。在以下方面达成了共识：首先，当前法律体系确实无法适配 AI 带来的新挑战……但在责任归属和财产权问题上存在明显分歧……",
  "total_rounds": 12,
  "total_utterances": 52,
  "consensus_count": 4,
  "divergence_count": 3,
  "ended_at": "2026-07-05T11:30:00+08:00"
}
```

> **约束**：`content` 为主持人自然语言总结文本，**禁止**在此字段中输出 JSON 结构数据。

---

#### `moderating` — 主持人介入提示

```
event: moderating
data: {
  "trigger": "round_interval",
  "message": "主持人正在串联第 4 轮讨论…"
}
```

| trigger 值 | 含义 |
|------------|------|
| `round_interval` | 每 3–4 轮专家发言后的例行串联 |
| `silence` | 检测到冷场，主持人追问引导 |
| `off_topic` | 检测到跑题，主持人纠正方向 |
| `user_interjection` | 用户插入追问，主持人转述并引导 |
| `closing` | 主持人正在进行收尾总结 |

---

#### `heartbeat` — 心跳

```
event: heartbeat
data: {"timestamp": "2026-07-05T10:16:30+08:00", "discussion_id": "b1a2c3d4-..."}
```

每 30 秒发送一次，用于保持 SSE 连接并检测断连。

---

## 6. 响应式统一封装

### 6.1 列表响应

```json
{
  "items": [ /* ... */ ],
  "total": 42
}
```

或按具体资源命名：
```json
{
  "discussions": [ /* ... */ ],
  "total": 42
}
```

### 6.2 单资源响应

直接返回资源对象（GET 单个 / PUT / POST 返回）。

### 6.3 操作响应

```json
{
  "status": "running",
  "message": "讨论已开始"
}
```

或：
```json
{
  "accepted": true,
  "message": "操作已接受"
}
```

### 6.4 错误响应

```json
{
  "error": {
    "code": "DISCUSSION_NOT_FOUND",
    "message": "讨论不存在",
    "details": "可选的补充说明"
  }
}
```

---

## 7. 多讨论隔离说明

每个 DiscussionEngine 实例持有：

| 资源 | 隔离方式 |
|------|----------|
| SQLite 操作 | 通过 discussion_id 过滤所有查询，WAL 模式保证读写不互锁 |
| SSE 事件 | `asyncio.Queue` 按 discussion_id 独立实例，事件仅推送至对应 stream 消费者 |
| LLM 调用 | 按 discussion_id 独立的 async task，共享 HTTP 连接池 |
| 状态管理 | DiscussionEngine 内部状态机，不受其他讨论影响 |

**API 层面保证：** 所有请求路径均包含 `{discussion_id}`，不存在跨讨论数据泄露路径。

**API Key 安全性：** API Key 通过后端环境变量 `LLM_API_KEY` 读取，前端无法通过任何 API 接口获取该值。
