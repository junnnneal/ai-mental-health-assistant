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
RERANK_CANDIDATES = int(os.getenv("RERANK_CANDIDATES", "10"))  # RRF 合并保留数 = 送精排候选数

# RRF 融合常数：两段式各用一次（合并处融合 cos/BM25 召回排名，定序处融合池内
# 余弦序/rerank 序），等权 1/(k+排名)——纯排名融合，不配权重不归一化。
# 加权扫描（eval_weighted_report.md）：权重曲面台阶状，BM25 票权 ≥2 退化纯词法
# （NDCG 0.714）、≤0.5 退化纯余弦（0.812），1:1 等权是唯一吃到两路互补的点。
# k≥20 结果饱和，取文献标准值 60。闸门恒用 rerank 绝对分。
RRF_K = int(os.getenv("RRF_K", "60"))

# ---------------- 混合检索：两段式 RRF（合并处融合召回，定序处融合排序） ----------------
# 稀疏词法补稠密向量的短板：专有名词/术语/精确字面可能整体进不了余弦 top-N——
# 精排只能重排已召回的候选，捞不回没进池子的块。两路各捞 top-N、RRF(cos,BM25)
# 等权合并取前 RERANK_CANDIDATES 送精排，精排后再与池内余弦序 RRF 融合定序。
# 100 题三轮对照定案（eval_report / eval_weighted_report / eval_width_report）：
#   召回宽精排池小：15+15 召回 R@0.976（10+10 是 0.940），合并 keep10 送精排；
#     keep15 对 top-3 无增益反而 top1 0.894→0.882；
#   定序不独裁：rerank 序即最终序（教科书做法）任何宽度都是最差行
#     （NDCG 0.791~0.807 / top1 0.824），RRF(cos,rr) 定序 0.859/0.894；
#   BM25 不进定序投票：任何 γ>0 第三票都不如不给（最优 γ=0.25 才 0.848 < 0.863），
#     闸门恒用 rerank 分（BM25 绝对分对无关题也有 6~13 分，无区分度）。
# RAG_RECALL_N：两路召回深度（余弦路与 BM25 路同宽，宽度实验 10→15 的来源）。
RAG_RECALL_N = int(os.getenv("RAG_RECALL_N", "15"))
# BM25_TOP_N：词法路深度。设 0 = 关闭词法路，合并退化为余弦原序
# （线上只动环境变量、不改代码的回滚开关）。
BM25_TOP_N = int(os.getenv("BM25_TOP_N", "15"))

# ---------------- 生成后幻觉自检（verify 事件） ----------------
# 回答流结束后、done 前，用一次低温 LLM 调用把回答拆成事实性声明逐条对照引用资料
# （§9 策略②输出自校验），并发算检索-生成对齐分（策略⑤：answer 与各引用块的最大
# 余弦，辅助信号只进 payload 与日志、不参与判定）。宽松三档：编造具体事实才 fail，
# 资料外的一般性心理建议只计 warn——陪伴场景回答几乎必带共情建议，从严会徽章常年
# 黄着没人信。仅在"有 citations 且回答≥30字"时触发；任何失败（超时/解析/异常）
# 静默跳过——不发 verify 事件、照常 done，绝不拖垮对话主链路（降级链第七层）。
# 设 0 = 关闭（线上只动环境变量的回滚开关，行为回到没有自检的版本）。
RAG_VERIFY = os.getenv("RAG_VERIFY", "1") == "1"
# 实测 glm-4-flash 非流式 ainvoke 生成核验 JSON 约 3~6s，长回答偶发 >8s（超时曾
# 让 verify 帧整体丢失），封顶 15s——只在有引用的回答末尾多等这一段，首字不受影响
RAG_VERIFY_TIMEOUT = float(os.getenv("RAG_VERIFY_TIMEOUT", "15"))

# 相似度阈值（弱卡过滤）：低于阈值的候选不进 prompt、不展示引用卡片——
# 宁可无引用，也不拿弱相关内容污染回答。两把尺子分开配、不混用：
RAG_MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.40"))
# ↑ 余弦尺（rerank 关闭时用）。实测分数带：精准≥0.6、相关0.4~0.5、弱匹配≤0.37，0.40 卡在空档上
RERANK_MIN_SCORE = float(os.getenv("RERANK_MIN_SCORE", "0.01"))
# ↑ rerank 尺（精排在场时用）。100 题标注集阈值扫描（eval_report.md Part B）：0.05→0.01
# 引用覆盖率 0.882→0.953、top1 正确率 0.824→0.847，代价仅无关引用率 0.046→0.101、
# OOV 误引用 4/14→6/14（新增两条均为低危生活类题）。分数带重叠（相关块 229/389 低于噪声
# 最高分 0.26），绝对阈值只能权衡、无法两全，取覆盖优先。
# 多轮拼接重试的触发线（余弦尺）：首轮最高分低于它 = 弱命中——"第二种方法是什么"这类指代型追问
# 会模模糊糊命中"第二步怎么做"这种序数语义的无关块（非空但错，实测0.31），拼上下文重检才对。
# 实测分数带：命中目标 0.58+、错得再像也只有 0.31，0.45 卡在两者之间
RAG_RETRY_BELOW = float(os.getenv("RAG_RETRY_BELOW", "0.45"))
