"""
集中配置：所有可变项收进环境变量，本地 .env / Render 环境变量一份清单管全部。
对应架构图里的 config_data.py —— 此前 GLM 地址、模型名、CORS 散落在 graph.py/tools.py/main.py 三处硬编码。
"""
import os

from dotenv import load_dotenv

# 必须在其他模块读 os.getenv 之前执行：本地开发读 .env，生产读平台环境变量
load_dotenv()

# ---------------- GLM（智谱开放平台，OpenAI 兼容协议） ----------------

GLM_API_KEY = os.getenv("GLM_API_KEY", "")
GLM_BASE_URL = os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
CHAT_MODEL = os.getenv("CHAT_MODEL", "glm-4-flash-250414")  # 固定版本号：别名排队抖动大
EMBED_MODEL = os.getenv("EMBED_MODEL", "embedding-2")
EMBED_URL = f"{GLM_BASE_URL}/embeddings"

# ---------------- 课程后端（登录、文章、会话、情绪日记） ----------------

BACKEND_BASE = os.getenv("BACKEND_BASE", "http://159.75.169.224:1235/api")

# ---------------- 服务自身 ----------------

# 允许的跨站来源：本地开发两个端口 + 线上站点（逗号分隔）。
# 生产流量其实走 Netlify agent.mjs 同源转发，这里主要服务本地直连调试
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://localhost:5174"
    ).split(",")
    if o.strip()
]

# /kb/rebuild 的管理令牌：空 = 端点禁用（公网可达的管理接口必须有钥匙）
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

# ---------------- RAG / 知识库 ----------------

CHROMA_DIR = os.getenv("CHROMA_DIR", "./chroma_data")  # Chroma 落盘目录（gitignore）
KB_SEED_DIR = os.getenv("KB_SEED_DIR", "./data")  # 种子文章 JSON（进仓库，随代码部署）
# 向量后端选择：chroma（默认）| json（纯Python余弦回退，Render 内存紧张/装不上 chromadb 时用）
KB_BACKEND = os.getenv("KB_BACKEND", "chroma")
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
# embedding 接口单批上限（智谱限制），也是现在 tools.py 一直用的批次大小
EMBED_BATCH_SIZE = 10
