# Agent 服务（FastAPI + LangGraph）

AI健康管家的服务端：LangGraph ReAct Agent，挂 4 个工具（知识库RAG检索 / 情绪分析查询 / 会话历史查询 / 情绪日记写入），`astream_events` 把执行过程翻译成 SSE（token / tool_start / tool_end / done / error）供前端做过程可视化。

## 启动

```bash
cd agent-server
.venv/Scripts/python.exe -m uvicorn main:app --port 8000
```

首次调用 `search_knowledge` 会先建知识库（拉全部文章详情 + 向量化，约 10~30 秒），之后走进程内缓存。

## 文件

- `tools.py` —— 工具层：ContextVar 透传用户 token 调后端接口；服务端 RAG（分块 + embedding-2 + 余弦 top-k）
- `graph.py` —— `create_react_agent` 组装 ReAct 循环 + 系统提示词
- `main.py` —— FastAPI 入口：`POST /chat` SSE 流式，CORS 限 localhost:5173/5174
- `.env` —— `GLM_API_KEY`、`BACKEND_BASE`（已 gitignore）
