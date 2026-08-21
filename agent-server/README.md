# Agent 服务（FastAPI + LangGraph + Chroma RAG）

服务端 RAG + AI健康管家 Agent。按模块化架构组织（对应标准 RAG 流程图的
config_data / knowledge_base / vector_stores / rag 分层）：

```
data/*.json ──▶ knowledge_base.py ──▶ rag.py(embedding) ──▶ vector_store.py(Chroma)
 种子文章      入库编排(分块/指纹)      智谱 embedding-2        持久化+cosine检索
                                             │
main.py ◀────────────────────────────────────┘
 ├─ POST /rag/chat   咨询页：检索→citations事件→LLM流式（SSE）
 ├─ POST /chat       健康管家：LangGraph ReAct，token/tool_start/tool_end/done/error
 ├─ POST /analyze    情绪分析（非流式，异常返 result=null）
 ├─ POST /kb/rebuild 强制重建知识库（x-admin-token 头校验 ADMIN_TOKEN）
 └─ GET  /health     健康检查 + 知识库状态（chunks/building/backend）
```

## 文件

- `config.py` —— 集中配置，全部环境变量化（见 .env.example）
- `llm.py` —— ChatOpenAI 工厂（rag/analyze/agent 三个实例共用一个构造点）
- `knowledge_base.py` —— 入库编排：种子加载 → h3 分块 → 批量向量化 → 写库；
  sha256 指纹增量重建（改 data/*.json 后自动重建）；单飞 Task 防并发重复构建
- `vector_store.py` —— Chroma PersistentClient（cosine）+ json 纯Python余弦双后端，
  chromadb 装不上/内存紧张时 `KB_BACKEND=json` 或自动降级，业务代码零改动
- `rag.py` —— 向量化 + 检索 + 咨询页 prompt（从前端逐字迁移，保证行为一致）
- `tools.py` —— Agent 工具层：ContextVar 透传用户 token 调课程后端
- `graph.py` —— `create_react_agent` 组装 ReAct 循环 + 系统提示词
- `data/` —— 30 篇种子文章（知识源内置，不依赖课程后端存活）
- `chroma_data/` —— 向量库落盘（运行时生成，gitignore，可随时由种子重建）

## 启动（本地）

```bash
cd agent-server
.venv/Scripts/python.exe -m uvicorn main:app --port 8000
```

启动时 lifespan 后台自动灌库（首次约 5 秒：30 篇 → 122 块），指纹命中时跳过。
前端 vite 已配 /agent 代理到 localhost:8000。

## 部署（Render）

- Root Directory: `agent-server`；Build: `pip install -r requirements.txt`；
  Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- 环境变量：`PYTHON_VERSION=3.13.4`、`GLM_API_KEY`、`BACKEND_BASE`、
  `CORS_ORIGINS`（线上站点地址）、`ADMIN_TOKEN`
- 免费版磁盘 ephemeral：重启后 lifespan 自动重建 Chroma（分钟内）
- 免费版 15 分钟无流量休眠：用 UptimeRobot 等每 10 分钟 ping `/health` 保活
- 生产访问链路：浏览器 → Netlify（agent.mjs 转发，环境变量 AGENT_URL）→ 本服务

## 知识库更新

改 `data/*.json` 后 push（Render 自动部署，指纹变化触发重建），
或在线上直接 `curl -X POST <render地址>/kb/rebuild -H "x-admin-token: <ADMIN_TOKEN>"`。

## 依赖版本

requirements.txt 钉死；chromadb 必须 >=1.1（Rust 内核才有 Python 3.13 wheel）。
