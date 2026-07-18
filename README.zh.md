# Agentic RAG Enterprise

企业级 Agentic RAG 运行时，受 Google Gemini Enterprise Agent Platform 的 Agentic RAG 架构启发。

> 当前状态：**Milestone 5 完成** — Planner (E-017) + Executor (E-018) 已交付。全量测试通过（682 passed / 1 skipped）。

---

## 快速开始

### 环境要求

- Python 3.13+
- （可选）Docker — 用于 Qdrant 向量数据库（mock 模式不需要）

### 启动服务

```bash
# 1. 安装依赖
uv sync --dev
# 或 pip install -e ".[dev]"

# 2. 配置文件已就绪（.env），直接启动
uvicorn agentic_rag_enterprise.api.main:app --reload --host 0.0.0.0 --port 8000
```

服务默认使用 **zen** provider（keyless 的 OpenAI 兼容接口），不需要 API Key 或外部数据库。

### 发一条请求

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "what is project x?"}'
```

返回结构化的 `AnswerEnvelope`：

```json
{
  "draft_answer": "回答正文",
  "claims": [{"claim_text": "...", "evidence_ids": ["..."]}],
  "evidence": [...]
}
```

### 健康检查

```bash
curl http://localhost:8000/health
# → {"status": "ok"}
```

---

## 模型 Provider 配置

项目支持三种 provider，在 `.env` 中通过 `LLM_PROVIDER` 切换：

### zen（默认，推荐）

Base URL: `https://opencode.ai/zen/v1`

无需 API Key。兼容 OpenAI 接口。

```ini
LLM_PROVIDER=zen
# 可选：指定模型
LLM_MODEL=deepseek-v4-flash-free
```

可用模型：`deepseek-v4-flash-free`（默认）、`mimo-v2.5-free`

### kilo

Base URL: `https://api.kilo.ai/api/gateway/v1`

无需 API Key。

```ini
LLM_PROVIDER=kilo
```

可用模型：
- `nvidia/nemotron-3-super-120b-a12b:free`（默认）
- `poolside/laguna-xs.2:free`
- `step-3.7-flash-free`

### mock（开发/测试）

内置确定性 fake 模型，不依赖外部服务。适合离线开发和测试。

```ini
LLM_PROVIDER=mock
```

---

## API 端点

| 端点 | 方法 | 说明 |
|---|---|---|
| `/health` | GET | 健康检查 |
| `/v1/chat` | POST | 企业级 RAG 问答（主入口） |
| `/chat` | POST | 遗留基线端点（仅用于回归测试） |

### 请求格式

```json
{
  "query": "你的问题",
  "corpus_id": "engineering_wiki"
}
```

`corpus_id` 可选，不传时使用默认路由。

---

## 项目架构

```
用户查询
   ↓
FastAPI (/v1/chat)
   ↓
ChatService (迭代检索 + 足够上下文判断)
   ├── Corpus Router (多 corpus 路由)
   ├── Multi-Corpus Retrieval (混合检索)
   ├── Evidence Store (证据存储)
   ├── Coverage Judge (证据充分性判断)
   ├── Planner + Executor (DAG 计划与执行)
   └── Grounded Synthesis (基于证据的回答)
   ↓
AnswerEnvelope (可审计的答案 + 引用列表)
```

### 核心能力

- **多库路由** — 将问题路由到正确的知识库
- **混合检索** — 稠密 + 稀疏检索，支持元数据过滤
- **主动规划** — 将复杂问题拆解为多步 DAG，逐步检索 (Planner + Executor)
- **证据充分性判断** — 判断已有证据是否足够回答，不够则继续检索
- **基证合成** — 仅基于检索到的证据生成回答，不编造
- **可审计跟踪** — 完整的计划、调用、证据、决策链路

---

## 开发命令

```bash
# 全量测试（682 项）
uv run pytest

# 代码风格检查
uv run ruff check .
uv run ruff format --check .

# 类型检查
uv run mypy src/agentic_rag_enterprise

# 自动修复格式
uv run ruff format .
```

---

## 项目状态

| Issue | 状态 | 说明 |
|---|---|---|
| E-017 | CLOSED | Typed Planner + DAG Validator |
| E-018 | CLOSED | Controlled DAG Executor |
| E-019/E-020 | 进行中 | Coverage Judge 迭代优化 |

---

## 许可

MIT
