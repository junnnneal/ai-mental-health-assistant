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

# ---------------- 两阶段检索：精排（rerank） ----------------
# 粗排多捞候选 → cross-encoder 精排挑 top_k。模型跑在托管 API 上（如 SiliconFlow）：
# 512MB 实例自己跑不动 cross-encoder（bge-reranker-v2-m3 权重 fp16 就 1.1GB，
# 且 0.1 核 CPU 单对前向要秒级），一条 HTTP 换别人的 GPU 是唯一解。
# KEY 留空 = 精排关闭，行为与纯向量检索完全一致（上线零风险，配好 key 随时启用）。
RERANK_URL = os.getenv("RERANK_URL", "https://api.siliconflow.cn/v1/rerank")
RERANK_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
RERANK_API_KEY = os.getenv("RERANK_API_KEY", "")
RERANK_TIMEOUT = float(os.getenv("RERANK_TIMEOUT", "2"))  # 超时即放弃，回退向量原序（降级链第五层）
RERANK_CANDIDATES = int(os.getenv("RERANK_CANDIDATES", "10"))  # 粗排候选数

# 相似度阈值（弱卡过滤）：低于阈值的候选不进 prompt、不展示引用卡片——
# 宁可无引用，也不拿弱相关内容污染回答。两把尺子分开配、不混用：
RAG_MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.40"))
# ↑ 余弦尺（rerank 关闭时用）。实测分数带：精准≥0.6、相关0.4~0.5、弱匹配≤0.37，0.40 卡在空档上
RERANK_MIN_SCORE = float(os.getenv("RERANK_MIN_SCORE", "0.05"))
# ↑ rerank 尺（精排在场时用）。实测分数带：相关≥0.1、噪声≤0.005（区分度比余弦高两个数量级），0.05 卡在空档上
# 多轮拼接重试的触发线（余弦尺）：首轮最高分低于它 = 弱命中——"第二种方法是什么"这类指代型追问
# 会模模糊糊命中"第二步怎么做"这种序数语义的无关块（非空但错，实测0.31），拼上下文重检才对。
# 实测分数带：命中目标 0.58+、错得再像也只有 0.31，0.45 卡在两者之间
RAG_RETRY_BELOW = float(os.getenv("RAG_RETRY_BELOW", "0.45"))
