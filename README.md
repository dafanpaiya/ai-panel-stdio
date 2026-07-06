# AI Panel Studio — 启动指南

## 项目结构

```
D:\ai panel stdio\
├── backend/                 # Python FastAPI 后端
│   ├── app/                 # 应用代码
│   ├── tests/               # 36条单元+E2E测试
│   └── requirements.txt
├── demo/                    # 前端 HTML demo
│   └── index.html           # 可直接在浏览器打开使用
├── data/                    # SQLite 数据库 + API Key 配置 (git ignored)
├── docs/                    # 文档
├── mockups/                 # UI 原型
├── PDR.md                   # 产品需求文档
└── TODO.md                  # 项目进度
```

## 启动后端

```bash
cd backend

# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动（首次启动会自动创建 SQLite 数据库）
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 3. 健康检查
curl http://localhost:8000/health
```

### 配置 API Key

首次启动后，后端没有 API Key，使用 Mock 模式。有两种方式配置：

**方式一：通过前端 UI**
打开 `demo/index.html`，点击右上角「设置」，填写 DeepSeek API Key 并保存。

**方式二：通过 API**
```bash
curl -X PUT http://localhost:8000/api/settings/llm/key \
  -H "Content-Type: application/json" \
  -d '{"provider":"deepseek","api_key":"sk-your-key","base_url":"https://api.deepseek.com","model":"deepseek-v4-flash"}'
```

API Key 保存在 `data/config.json`，不会被 git 追踪。

## 打开前端 Demo

直接用浏览器打开 `demo/index.html`。

或者在项目根目录启动静态服务器：
```bash
cd D:\ai panel stdio
python -m http.server 8080 --directory demo
# 浏览器访问 http://localhost:8080
```

## 运行测试

```bash
cd backend
python -m pytest tests/ -v    # 36条测试
```

## 关键 API 端点

| 用途 | 端点 |
|------|------|
| 讨论列表 | `GET /api/discussions` |
| 创建讨论 | `POST /api/discussions` |
| 生成嘉宾 | `POST /api/discussions/{id}/panel/generate` |
| 开始讨论 | `POST /api/discussions/{id}/start` |
| SSE 实时流 | `GET /api/discussions/{id}/stream` |
| Transcript | `GET /api/discussions/{id}/transcript` |
| 共识/分歧 | `GET /api/discussions/{id}/insights` |
| 追问 | `POST /api/discussions/{id}/interject` |
| API Key 管理 | `GET/PUT /api/settings/llm/key` |

## 技术栈

- 前端: 纯 HTML/CSS/JS (React+TS 版本待开发)
- 后端: Python FastAPI + SSE
- 数据库: SQLite (WAL 模式)
- 大模型: DeepSeek V4 Flash (OpenAI 兼容协议)
- 测试: pytest + pytest-asyncio (36条)
