# AI 心理健康情绪陪伴助手

![Vue](https://img.shields.io/badge/Vue-3.5-42b883?logo=vuedotjs) ![TypeScript](https://img.shields.io/badge/TypeScript-6.0-3178c6?logo=typescript) ![FastAPI](https://img.shields.io/badge/FastAPI-0.119a?logo=fastapi) ![LangGraph](https://img.shields.io/badge/LangGraph-ReAct_Agent-1c3c3c) ![Chroma](https://img.shields.io/badge/ChromaDB-向量检索-ff6f61)

基于大模型的 PC 端心理健康陪伴应用：**Vue3 前端 + FastAPI Agent 服务端**双端架构，GLM 大模型 + 服务端 RAG 检索增强 + LangGraph ReAct Agent，SSE 全链路流式对话，已部署上线（Netlify + Render 双平台）。

## 🏗️ 架构总览

```
浏览器
  │
  ▼
Netlify（前端静态站 + 边缘函数代理）
  ├── /api/*   ──────────► 课程业务后端（登录 / 文章 / 会话）
  └── /agent   ──────────► Render · FastAPI agent-server
                              ├── POST /rag/chat    咨询页：检索 → citations 事件 → GLM 流式（SSE）
                              ├── POST /chat        健康管家：LangGraph ReAct Agent（SSE）
                              ├── POST /analyze     情绪分析（非流式）
                              ├── POST /kb/rebuild  知识库重建（admin token 校验）
                              └── GET  /health      健康检查 + 知识库状态
                              │
                              ├── 智谱 GLM（生成）/ embedding-2（向量化）
                              ├── SiliconFlow bge-reranker-v2-m3（精排）
                              └── ChromaDB（嵌入式向量库，cosine）
```

**密钥全链路不出服务端**：GLM / embedding / rerank 的 key 只存在于 Render 环境变量，前端 bundle 零泄漏。

## ✨ 功能

**前台**
- **AI 心理咨询**：RAG 检索增强的流式对话，回答前置「引用卡片」标注知识来源；回答完成后**「AI 自检」徽章**逐条核对事实声明与引用资料（生成后幻觉校验，可展开明细）；识别自伤风险时优先给出心理援助热线（危机兜底）
- **AI 健康管家**：LangGraph ReAct Agent，自主调用知识检索 / 情绪分析 / 会话查询 / 日记保存四类工具
- **情绪日记**：富文本记录 + AI 情绪分析 + ECharts 情绪趋势可视化
- **心理知识库**：150 篇 / 10 类主题结构化文章，支持浏览检索
- **登录注册**：会话与日记按用户隔离

**后台（管理端）**
- 数据看板、咨询记录、情绪统计、知识文章管理

## 🛠️ 技术栈

| 端 | 技术 |
|---|---|
| 前端 | Vue 3.5（`<script setup>` + TS）、Vite 8、Pinia、Element Plus、ECharts、wangEditor、SSE（原生 fetch 流解析） |
| Agent 服务端 | Python / FastAPI、LangGraph（ReAct）、LangChain（ChatOpenAI）、ChromaDB、httpx、jieba（BM25 词法检索） |
| 模型服务 | 智谱 GLM（流式生成）、embedding-2（1024 维向量化）、SiliconFlow 托管 bge-reranker-v2-m3（精排） |
| 部署 | Netlify（前端 + 边缘函数代理）、Render（Agent 服务，指纹自动重建 + 定时保活） |

## 🚀 核心技术亮点

### 1. SSE 流式对话全链路（首字延迟 1.8s → 190~240ms）
- **手写 SSE 解析器**：原生 fetch 读流 + buffer 半行拼接，正确处理 chunk 在 `data:` 行中间断开的边界；事件契约 `citations → token → done/error`，错误以事件下发绝不裸断流
- **rAF 打字机**：requestAnimationFrame 逐字渲染，按 token 积压量自适应速度，surrogate pair 处理保证 emoji 不乱码
- **首字优化靠埋点不靠猜**：分段埋点定位出会话建立阻塞与模型版本 TTFT 抖动两处瓶颈，建会话改后台单飞、固定模型版本后首字稳定 190~240ms（约 4 倍提升）
- **瞬态网关错误自动重试**：仅对 502/503/504 且「流尚未开始」时延迟重试一次，防止回复内容重复

### 2. 服务端 RAG 混合检索管线（150 篇 / 655 块语料）
```
150 篇结构化文章 → <h3> 小节语义分块（碎块丢弃 + 「分类-标题-小节」前缀增强命中）
  → embedding-2 批量向量化（按 index 还原顺序）→ 嵌入式 ChromaDB（cosine）
查询时刻：问题向量化 → 混合召回（余弦 top-15 ∪ BM25 词法 top-15，纯 Python Okapi + jieba 分词）
  → RRF(k=60) 等权融合两路召回排名、取前 10 送 bge-reranker 精排
  → 池内余弦序 + 精排序再做一次 RRF 融合定序（精排当投票者、不当独裁者）
  → top-3 → 双尺阈值过滤（rerank 尺 / 余弦尺分开配）→ 指代型追问弱命中自动拼上下文重检
  → 资料截 300 字注入 system prompt → GLM 流式生成 + 引用卡片前置下发
  → 回答完成后低温 LLM 幻觉自检（事实声明三档核对 + 检索-生成对齐分）→ verify 事件下发徽章
```
- 语料按**实测召回失败定向扩容**（30 → 150 篇）：「提加薪」弱卡 0.41 → 三连中 0.68；指代追问「第二种方法是什么」错卡 0.31 → 对卡 0.61
- 噪声 query（"1+1等于几"）top-3 全滤，零引用零知识库污染
- **可靠性六层兜底**：知识库 3s 软超时降级直答、检索异常返回空列表、chromadb 不可用自动切 JsonStore 纯 Python 余弦、rerank 超时回退合并 RRF 序、BM25 失败静默退化为纯余弦召回（jieba 缺失再降级 CJK 二元组分词）、幻觉自检失败静默跳过照常收尾——RAG 任何故障都不拦着 AI 回话，首字延迟不因加检索而劣化

### 3. 检索质量可量化（100 题分级评测集，四个自由度全部实验定案）
人工标注 100 条 query（同义改写 / 关键词 / 易混淆 / 危机 / OOV 分级），构建 `eval_dataset.json`，用 **MRR@3 / NDCG@3 / Hit@3 / P@3** 同池对照各检索配置，四个设计自由度各有专属实验：
- **RRF 的位置**：教科书「RRF(cos,BM25) 合并 → rerank 序即终序」在任何召回宽度下都是最差行（NDCG 0.791~0.807，rerank 独裁易翻车）——定案**两段式**：合并处 RRF(cos,BM25) 选池、定序处 RRF(cos,rerank)，精排当投票者不当独裁者；
- **权重**：加权扫描 w_bm∈{0, 0.25, 0.5, 1, 2, ∞} 权重曲面台阶状——≥2 退化纯词法选池（NDCG 0.714）、≤0.5 退化纯余弦（0.812），**1:1 等权是唯一吃到两路互补的点**，RRF「排名融合、免权重调参」的设计哲学在实测中成立；
- **宽度**：召回 15+15（R@0.976，10+10 为 0.940）+ 合并只留 10 送精排（「召回宽、精排池小」；keep15 对 top-3 无增益反降 top1）；
- **闸门**：两段式架构下重扫确认 rerank≥0.01 仍是覆盖-噪声膝点（0.005 噪声 +42%，0.02 覆盖 -3.5pt）。
最终 **MRR 0.941 / NDCG@3 0.859 / P@3 0.877 / Hit@3 0.973 / 闸后 top1 正确率 0.894**；rerank 有效性按「先各路召回、再同池只变排序」分阶段验证（同池对照：无 rerank 0.777 NDCG / rerank 独裁 0.803 / 融合 0.859，MRR 与 top1 只有融合不降）；五份报告：`eval_report.md`（v3 基线）→ `eval_weighted_report.md`（权重与 RRF 位置）→ `eval_width_report.md`（宽度与保留数）→ `eval_gate_report.md`（闸门重校）→ `eval_stages_report.md`（召回/精排分阶段拆解）。

### 3.5 生成后幻觉自检（verify 事件）
回答流结束后、断流前，服务端用一次低温 LLM 调用把回答拆成事实性声明，逐条对照引用资料标注三档（supported 有依据 / beyond 资料外建议 / unsupported 与资料不符），并发计算检索-生成对齐分（回答与各引用块的最大余弦）；verdict 服务端从声明重算，经 SSE `verify` 事件下发，前端渲染「AI 自检」徽章（可展开明细）。宽松三档尺度（编造具体事实才 fail）适配陪伴场景；纯共情回答/无引用/自检任何失败一律不发事件、照常收尾——自检绝不拖垮对话主链路。

### 4. LangGraph ReAct Agent
`create_react_agent` 组装推理-行动循环，工具层经 ContextVar 透传用户 token 调课程后端，SSE 下发 `tool_start/tool_end` 事件让前端实时展示工具调用过程。

### 5. IndexedDB 会话持久化（本地即唯一真相源）
桶模型（`userId_sessionKey` 索引 + seq 自增保序）、localStorage 存量幂等迁移、单桶 200 条容量裁剪、无痕模式降级内存模式；定位并修复 **reactive Proxy 不可结构化克隆**导致的静默落库失败（DataCloneError）。

### 6. 部署工程化
- Render 免费层：ephemeral 磁盘重启丢库 → 语料 sha256 指纹校验自动重建（655 块约 10s，embedding 掉条批级重试 + 全有或全无入库，缺块绝不静默上架）；15 分钟休眠 → GitHub Actions（每 5 分钟）+ Netlify 定时函数（每 15 分钟错峰）双平台保活——单平台 cron 延迟不再造成休眠，UptimeRobot 免费档不可靠已弃用
- Netlify 边缘函数代理跨域与密钥注入，前端开发/生产同一 `/agent` 路径

## 📦 本地运行

```bash
# 前端（Node ^20.19.0 || >=22.12.0）
npm install
npm run dev          # Vite 已配置 /api /agent /llm 本地代理

# Agent 服务端（Python 3.13）
cd agent-server
pip install -r requirements.txt
python -m uvicorn main:app --port 8000   # 启动时自动灌库（首次约 10s）
```

环境变量（GLM_API_KEY 等）见 [agent-server/README.md](agent-server/README.md)。

## 📁 目录结构

```
├── src/
│   ├── apis/            # agent(SSE 解析) / llm / 业务接口
│   ├── views/frontend/  # 咨询 / 健康管家 / 情绪日记 / 知识库 / 首页
│   ├── views/backend/   # 管理端看板 / 咨询记录 / 情绪统计 / 知识管理
│   ├── composables/     # useRag / useEmotionAnalysis
│   └── stores/ router/ components/
├── agent-server/        # FastAPI：rag.py / graph.py / knowledge_base.py / vector_store.py / eval
├── netlify/functions/   # 边缘函数代理
└── scripts/             # 语料校验 / 导入脚本
```

## 📝 说明

业务后端与基础页面结构源自课程项目；**服务端 RAG 管线、LangGraph Agent、SSE 流式全链路、检索质量评测、IndexedDB 持久化方案与双平台部署**为个人独立完成的设计与实现。AI 生成内容仅供参考，不构成专业心理诊断；存在自伤风险请拨打专业心理援助热线。项目仅用于学习交流。
