AI Panel Studio — 项目进度与完成清单
=====================================

## 已完成

### 文档
- [x] PDR.md — 产品需求文档
- [x] docs/API.md — API 契约文档  
- [x] docs/data-model.md — 数据建模文档（ER图 + DDL + 字段定义）
- [x] TODO.md — 本文件

### 测试（36条，全部通过，0 warnings）
- [x] backend/tests/test_scheduler.py — 30条单元测试：调度器、主持人触发、发言统计、边界场景、Schema校验
- [x] backend/tests/test_e2e_parallel.py — 6条E2E测试：多讨论并行隔离、transcript无交叉污染、共识增量更新、SSE无内部事件、发言长度截断

### 后端 (Python FastAPI)
- [x] app/core/models.py — 领域模型、枚举、SSEEvent
- [x] app/core/dispatch.py — 上下文窗口、频率控制、发言截断、候选人排序
- [x] app/core/scheduler.py — 发言调度器门面
- [x] app/core/speaking_stats.py — 发言统计计算
- [x] app/core/moderator.py — 主持人触发条件逻辑
- [x] app/core/engine.py — DiscussionEngine 编排器（开场→调度→发言→共识/分歧→收尾）
- [x] app/core/manager.py — DiscussionManager 多讨论并行管理
- [x] app/core/config.py — API Key 配置持久化到 data/config.json
- [x] app/llm/client.py — LLM 抽象接口 + MockLLMClient + DeepSeekClient
- [x] app/llm/factory.py — LLM 客户端工厂（按config创建）
- [x] app/db/database.py — SQLite 6表 + 6索引
- [x] app/api/routes.py — 15个REST端点 + SSE流 + 4个API Key管理端点
- [x] app/main.py — FastAPI入口、CORS、生命周期
- [x] 已验证：真实DeepSeek V4 Flash调用成功，discussions/panelists/utterances/consensus/divergences 数据持久化到SQLite

### UI原型
- [x] mockups/index.html — 首页+演播厅完整HTML原型（浅色演播厅蓝调主题，3个响应式断点，专家卡片状态驱动视觉，静态指示灯，底部控制栏状态联动）

### 数据库验证
- [x] 数据库引擎: SQLite (WAL mode, 单文件 data/ai_panel_studio.db)
- [x] 无 PostgreSQL / MySQL / MongoDB / Redis 依赖
- [x] 6 张表: discussions, panelists, utterances, consensus, divergences, panelist_states
- [x] 数据正常持久化: 2 discussions / 11 panelists / 17 utterances / 2 consensus / 2 divergences

### 基础设施
- [x] .gitignore — 已排除 data/ *.db *.sqlite3 __pycache__ .pytest_cache .tox .ruff_cache 等
- [x] data/config.json — API Key 存储（不受git追踪）
- [x] data/ai_panel_studio.db — SQLite数据库（不受git追踪）
- [x] 后端在 localhost:8000 运行，已配置 DeepSeek V4 Flash

## 待完成

### 前端 (React + TypeScript)
- [ ] 项目脚手架（Vite + React + TypeScript）
- [ ] 首页讨论列表
- [ ] 阵容生成向导
- [ ] 演播厅页面（4区域布局 + SSE消费）
- [ ] API Key 设置页面
- [ ] 状态管理（Zustand/Jotai）
- [ ] SSE 流式事件消费
- [ ] 前端dev server启动脚本

### 文档
- [ ] README.md

### 产品增强（V1.1+）
- [ ] 讨论回放（时间轴重放transcript）
- [ ] 讨论导出（Markdown/PDF）
- [ ] 多LLM Provider切换UI
- [ ] 预设话题模板
- [ ] 专家人设库
