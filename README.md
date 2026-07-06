# AI Panel Studio

AI 圆桌讨论本地 Web 应用。输入任意话题，系统调用大模型动态生成主持人与专家阵容，在演播厅中驱动一场 AI 主导、实时推进的多角色圆桌讨论。

## 技术选型

| 维度 | 方案 | 理由 |
|------|------|------|
| 前端 | 纯 HTML/CSS/JS（React + TypeScript 待开发） | 当前为可用的单页 demo |
| 后端 | Python FastAPI | LLM 生态丰富，异步/SSE 原生支持 |
| 实时通信 | SSE（Server-Sent Events） | 单向事件推送，比 WebSocket 简单，匹配讨论场景 |
| 数据库 | SQLite（单文件） | 本地应用首选，零配置 |
| 大模型 | DeepSeek V4 Flash（OpenAI 兼容协议） | 性价比高，支持多 provider 切换 |
| 测试 | pytest + pytest-asyncio（36 条） | 单元测试 + E2E 并行隔离测试 |

## 快速开始

### 1. 启动后端

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

启动成功后访问 `http://localhost:8000/health` 应返回 `{"status":"ok"}`。

### 2. 启动前端

后端启动后已自动挂载前端页面，直接浏览器访问：

```
http://localhost:8000/demo
```

无需单独启动前端服务器。

### 3. 配置 API Key

打开页面右上角「设置」，填写 DeepSeek API Key 保存。也可通过 API 配置：

```bash
curl -X PUT http://localhost:8000/api/settings/llm/key \
  -H "Content-Type: application/json" \
  -d '{"provider":"deepseek","api_key":"sk-你的key","base_url":"https://api.deepseek.com","model":"deepseek-v4-flash"}'
```

API Key 存储在本地文件中，不会上传到 git。

### 4. 运行测试

```bash
cd backend
python -m pytest tests/ -v
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key（优先级高于 UI 配置） | - |

环境变量优先级：环境变量 > config.json > Mock fallback。

**如果 API Key 有效**，系统调用 DeepSeek V4 Flash 实时生成嘉宾阵容、发言内容、共识与分歧。

**如果 API Key 无效或未配置**，系统自动 fallback 到固定 mock 数据，仍可完整体验讨论流程。

## 主要 API 列表

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/discussions` | 获取讨论列表 |
| `POST` | `/api/discussions` | 创建新讨论 |
| `GET` | `/api/discussions/{id}` | 讨论详情 |
| `DELETE` | `/api/discussions/{id}` | 删除讨论（仅已结束） |
| `POST` | `/api/discussions/{id}/panel/generate` | 生成主持人与专家阵容 |
| `GET` | `/api/discussions/{id}/panel` | 获取当前阵容 |
| `PUT` | `/api/discussions/{id}/panel/{pid}` | 编辑嘉宾 |
| `DELETE` | `/api/discussions/{id}/panel/{pid}` | 删除专家 |
| `POST` | `/api/discussions/{id}/panel` | 手动新增专家 |
| `POST` | `/api/discussions/{id}/start` | 开始讨论（启动引擎） |
| `POST` | `/api/discussions/{id}/pause` | 暂停讨论 |
| `POST` | `/api/discussions/{id}/resume` | 恢复讨论 |
| `POST` | `/api/discussions/{id}/interject` | 用户插入追问 |
| `POST` | `/api/discussions/{id}/end` | 手动结束讨论 |
| `GET` | `/api/discussions/{id}/stream` | SSE 事件流（实时推送） |
| `GET` | `/api/discussions/{id}/transcript` | 获取 transcript |
| `GET` | `/api/discussions/{id}/insights` | 获取共识/分歧列表 |
| `GET` | `/api/settings/llm` | 查看 LLM 配置（key 脱敏） |
| `PUT` | `/api/settings/llm/key` | 设置 API Key |
| `POST` | `/api/settings/llm/active` | 切换活跃 provider |

### SSE 事件类型

| 事件 | 说明 |
|------|------|
| `utterance` | 新发言（含发言人信息、内容、类型） |
| `panelist_status` | 专家状态变更（idle / preparing / speaking） |
| `consensus_update` | 共识增量更新 |
| `divergence_update` | 分歧增量更新 |
| `moderating` | 主持人介入提示 |
| `discussion_ended` | 讨论结束（含主持人总结） |

## 已完成功能

- 首页讨论列表（查看所有讨论、状态筛选、点击进入演播厅）
- 阵容生成向导（输入话题、指定专家人数、设置轮次，LLM 实时生成嘉宾）
- 阵容重新生成
- 演播厅模式（主持人发言区、专家状态小窗网格、共识与分歧区、实时 Transcript）
- 两步管道发言调度（调度决定谁发言 → 生成发言内容）
- 主持人条件触发（开场、轮次间隔、用户追问、收尾）
- 共识/分歧增量更新（讨论过程中持续提取，非仅在结束时）
- Transcript 实时展示（按发言人色块区分）
- 用户控制（暂停/继续/追问/结束）
- SSE 实时事件推送
- 多讨论并行隔离（独立引擎、独立 transcript、独立状态）
- SQLite 持久化（讨论、嘉宾、发言、共识、分歧）
- API Key 管理（UI 配置 + 环境变量，key 脱敏存储）
- Mock fallback（未配置 key 时自动使用模拟数据）

## 后续改进方向

### 功能完整性

1. **增设专家功能未实现** — API 已定义 `POST /api/discussions/{id}/panel` 端点，但前端向导中缺少对应的 UI 交互，用户无法手动新增自定义专家
2. **修改专家功能未实现** — API 已定义 `PUT /api/discussions/{id}/panel/{pid}` 端点，但前端阵容卡片缺少编辑入口

### 讨论机制

3. **不具备真正的讨论抢答插话功能** — 当前调度器主要产生 `main` 类型发言，`rebuttal` 和 `supplement` 类型占比较低，专家之间缺少自发打断和抢夺发言权的真实讨论感。调度 prompt 需进一步优化，使 LLM 在检测到观点冲突时更积极安排反驳和补充
4. **轮次定义可能需要设定** — 当前"轮次"概念与发言条数不完全对应，单轮内可能包含多条发言但 round 值不变。需明确轮次的语义（是专家每人发言一次为一轮？还是每次 LLM 调度为一轮？）

### UI 修复

5. **共识与分歧的 UI 界面不符合要求** — 共识和分歧区在内容较多时滚动体验不佳，需要更好的布局方案（如分区折叠、搜索筛选等）
6. **发言、项目等数据呈现有误问题** — 嘉宾头像显示为 `?` 而非姓名首字、部分讨论轮次计数与实际发言数不一致、已结束讨论的 transcript 部分为空

### 文档

7. **README 已编写完成** — 本文件

## 项目结构

```
├── backend/                 # Python FastAPI 后端
│   ├── app/
│   │   ├── core/            # 领域模型、引擎、调度器、主持人触发
│   │   ├── llm/             # LLM 客户端（DeepSeek + Mock）
│   │   ├── db/              # SQLite 数据库访问层
│   │   └── api/             # REST + SSE 路由
│   └── tests/               # 36 条测试
├── demo/                    # 前端 HTML demo
├── docs/                    # 文档（API、数据模型、样例数据）
├── data/                    # SQLite DB + API Key 配置（git ignored）
├── PDR.md                   # 产品需求文档
└── README.md                # 本文件
```
