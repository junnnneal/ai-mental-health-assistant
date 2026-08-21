<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  getKnowledgeArticleDetail,
  getKnowledgeArticlePage,
} from "@/apis/frontEnd";
import type { ArticleItem } from "@/types";
import {
  ArrowLeft,
  Collection,
  Reading,
  Search,
  Star,
  Timer,
  View,
} from "@element-plus/icons-vue";

const articles = ref<ArticleItem[]>([]);
const recommendArticles = ref<ArticleItem[]>([]);
const currentArticle = ref<ArticleItem | null>(null);
const loading = ref(false);
const detailLoading = ref(false);
const keyword = ref("");

const pagination = ref({
  currentPage: 1,
  size: 5,
  total: 0,
});

const fallbackArticles: ArticleItem[] = [
  {
    id: "static_1",
    title: "焦虑来临时，如何把注意力带回当下",
    summary:
      "用呼吸、身体感受和环境观察，把失控感拆成可以处理的小步骤。",
    categoryName: "情绪调节",
    authorName: "心理AI助手",
    readCount: 1280,
    updatedAt: "2026-07-30",
    tags: ["焦虑", "呼吸练习", "自我照顾"],
    content:
      "<p>当焦虑出现时，先不急着和它对抗。你可以试着把注意力放在脚掌、呼吸和周围的声音上。</p><h2>一个简单练习</h2><p>慢慢吸气 4 秒，呼气 6 秒，重复 3 到 5 轮。然后说出你看到的 3 个物品、听到的 2 种声音、感受到的 1 个身体触点。</p>",
  },
  {
    id: "static_2",
    title: "睡前反刍太多，可以怎样停下来",
    summary:
      "给大脑一个收尾仪式，把明天再处理的事写下来，让休息重新变得可能。",
    categoryName: "睡眠支持",
    authorName: "心理AI助手",
    readCount: 936,
    updatedAt: "2026-07-28",
    tags: ["睡眠", "压力", "记录"],
    content:
      "<p>睡前反复思考并不代表你脆弱，更多时候是大脑在尝试保护你。</p><h2>睡前收尾</h2><p>准备一张纸，写下最担心的三件事，并为每件事写一个明天最小的行动。</p>",
  },
  {
    id: "static_3",
    title: "如何识别情绪背后的真实需求",
    summary:
      "情绪不是问题本身，它常常是在提醒我们某个需求没有被看见。",
    categoryName: "自我理解",
    authorName: "心理AI助手",
    readCount: 784,
    updatedAt: "2026-07-25",
    tags: ["需求", "觉察", "关系"],
    content:
      "<p>愤怒、委屈、低落和焦虑都可能指向一个未被满足的需求。</p><h2>提问方式</h2><p>你可以问自己：如果这个情绪能说话，它最希望我知道什么？</p>",
  },
];

const visibleArticles = computed(() => {
  const word = keyword.value.trim();
  if (!word) {
    return articles.value;
  }
  return articles.value.filter((article) =>
    `${article.title}${article.summary || ""}${getCategoryName(article)}`
      .toLowerCase()
      .includes(word.toLowerCase()),
  );
});

const articleTags = (tags?: string | string[]) => {
  if (Array.isArray(tags)) {
    return tags;
  }
  if (!tags) {
    return [];
  }
  return tags
    .split(/[,，\s]+/)
    .map((tag) => tag.trim())
    .filter(Boolean);
};

const formatReadCount = (count?: number) => {
  if (!count) {
    return "0";
  }
  if (count >= 10000) {
    return `${(count / 10000).toFixed(1)}万`;
  }
  return String(count);
};

const getCategoryName = (article: ArticleItem) => {
  return article.categoryName || article.category || "心理科普";
};

const getArticleContent = (article: ArticleItem) => {
  return article.content || article.articleContent || "<p>暂无正文内容。</p>";
};

const normalizeArticleList = (data: any) => {
  if (Array.isArray(data)) {
    return {
      records: data,
      total: data.length,
    };
  }

  return {
    records: data?.records || data?.list || data?.data?.records || [],
    total: data?.total || data?.data?.total || data?.records?.length || 0,
  };
};

const loadArticles = async () => {
  loading.value = true;
  try {
    const res = await getKnowledgeArticlePage({
      sortField: "readCount",
      sortDirection: "desc",
      currentPage: pagination.value.currentPage,
      size: pagination.value.size,
    });
    const { records, total } = normalizeArticleList(res);
    articles.value = records.length ? records : fallbackArticles;
    // 推荐栏不在这里赋值：翻页会重跑本函数，会把全局Top6冲成当前页top3
    // （推荐由loadRecommendations单独负责，仅在catch里用静态数据兜底）
    pagination.value.total = total || articles.value.length;
  } catch (error) {
    articles.value = fallbackArticles;
    recommendArticles.value = fallbackArticles.slice(0, 3);
    pagination.value.total = fallbackArticles.length;
    ElMessage.error("获取文章列表失败");
    console.error("获取文章列表失败", error);
  } finally {
    loading.value = false;
  }
};

const openArticle = async (article: ArticleItem) => {
  currentArticle.value = article;
  if (String(article.id).startsWith("static_")) {
    return;
  }

  detailLoading.value = true;
  try {
    const detail = await getKnowledgeArticleDetail(article.id);
    currentArticle.value = {
      ...article,
      ...(detail || {}),
    };
  } catch (error) {
    ElMessage.error("获取文章详情失败");
    console.error("获取文章详情失败", error);
  } finally {
    detailLoading.value = false;
  }
};

const backToList = () => {
  currentArticle.value = null;
};

const handlePageChange = (page: number) => {
  pagination.value.currentPage = page;
  loadArticles();
};

//推荐栏单独拉全局阅读量top4：只从当前页5篇里挑覆盖面太窄，
//失败静默保留loadArticles里的当前页top3兜底
const loadRecommendations = async () => {
  try {
    const res = await getKnowledgeArticlePage({
      sortField: "readCount",
      sortDirection: "desc",
      currentPage: 1,
      size: 4,
    });
    const { records } = normalizeArticleList(res);
    if (records.length) {
      recommendArticles.value = records.slice(0, 4);
    }
  } catch (error) {
    console.error("获取推荐文章失败", error);
  }
};

onMounted(() => {
  loadArticles();
  loadRecommendations();
});
</script>

<template>
  <div v-if="!currentArticle" class="knowledge-container">
    <section class="header-section">
      <div class="header-content">
        <el-icon><Collection /></el-icon>
        <div>
          <h2>心理知识库</h2>
          <p>把情绪、睡眠、压力和关系里的困惑整理成可以阅读的答案</p>
        </div>
      </div>
      <div class="search-box">
        <el-input
          v-model="keyword"
          :prefix-icon="Search"
          placeholder="搜索文章标题、摘要或分类"
          clearable
        />
      </div>
    </section>

    <main class="content">
      <aside class="recommend-section">
        <div class="section-title">
          <el-icon><Star /></el-icon>
          推荐阅读
        </div>
        <div class="recommend-list">
          <div
            v-for="article in recommendArticles"
            :key="article.id"
            class="recommend-item"
            @click="openArticle(article)"
          >
            <h4>{{ article.title }}</h4>
            <p>{{ article.summary }}</p>
            <div class="read-count">
              <el-icon><View /></el-icon>
              <span>{{ formatReadCount(article.readCount) }} 阅读</span>
            </div>
          </div>
        </div>
      </aside>

      <section class="article-list" v-loading="loading">
        <el-empty
          v-if="visibleArticles.length === 0"
          description="暂无匹配文章"
        />
        <article
          v-for="article in visibleArticles"
          :key="article.id"
          class="article-item"
          @click="openArticle(article)"
        >
          <div class="article-cover">
            <el-icon><Reading /></el-icon>
          </div>
          <div class="info">
            <div class="title">
              <h3>{{ article.title }}</h3>
              <el-tag size="small" type="warning">
                {{ getCategoryName(article) }}
              </el-tag>
            </div>
            <p class="summary">{{ article.summary || "暂无摘要" }}</p>
            <div class="flex-box article-meta">
              <div class="meta-item">
                <el-icon><Timer /></el-icon>
                <span>{{ article.updatedAt || article.createdAt || "刚刚" }}</span>
              </div>
              <div class="meta-item">
                <el-icon><View /></el-icon>
                <span>{{ formatReadCount(article.readCount) }} 阅读</span>
              </div>
              <span class="author">{{ article.authorName || "心理AI助手" }}</span>
            </div>
          </div>
        </article>
      </section>
    </main>

    <div class="pagination-wrapper">
      <el-pagination
        layout="prev, pager, next"
        :current-page="pagination.currentPage"
        :page-size="pagination.size"
        :total="pagination.total"
        @current-change="handlePageChange"
      />
    </div>
  </div>

  <div v-else class="articleDetail-container" v-loading="detailLoading">
    <section class="header-section">
      <div class="header-content">
        <el-button circle plain :icon="ArrowLeft" @click="backToList" />
        <div>
          <h2>文章详情</h2>
          <p>慢慢读，选择一个此刻最有帮助的句子带走</p>
        </div>
      </div>
    </section>

    <main class="content">
      <article class="diary-card">
        <div class="title">知识文章</div>
        <div class="sub-title">
          <el-tag class="category-tag" type="warning">
            {{ getCategoryName(currentArticle) }}
          </el-tag>
          <div class="flex-box">
            <div class="item">
              <el-icon><Timer /></el-icon>
              <span>
                {{ currentArticle.updatedAt || currentArticle.createdAt || "刚刚" }}
              </span>
            </div>
            <div class="item">
              <el-icon><View /></el-icon>
              <span>{{ formatReadCount(currentArticle.readCount) }} 阅读</span>
            </div>
          </div>
        </div>

        <h1 class="article-title">{{ currentArticle.title }}</h1>

        <div class="summary-content">
          {{ currentArticle.summary || "这篇文章暂时没有摘要。" }}
        </div>

        <div
          class="content-wrapper"
          v-html="getArticleContent(currentArticle)"
        ></div>

        <div class="tags-content" v-if="articleTags(currentArticle.tags).length">
          <div class="tags-title">文章标签</div>
          <div class="tags-list">
            <el-tag
              v-for="tag in articleTags(currentArticle.tags)"
              :key="tag"
              effect="plain"
            >
              {{ tag }}
            </el-tag>
          </div>
        </div>
      </article>
    </main>
  </div>
</template>

<style scoped lang="scss">
.knowledge-container {
  min-height: calc(100vh - 120px);
  background: linear-gradient(135deg, #fafbfc 0%, #f7f9fc 50%, #f2f6fa 100%);
  // 页面级左右留白：banner和内容列都在这个栅格里居中（与情绪日记页同款）
  padding: 0 28px;
  .flex-box {
    display: flex;
    align-items: center;
    gap: 14px;
    span {
      margin-left: 4px;
    }
  }
  .header-section {
    background: linear-gradient(135deg, #f59e0b 0%, #8b5cf6 100%);
    color: white;
    padding: 42px 48px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 24px;
    // 四角圆角浮动卡片；border-box必须显式补（项目无全局重置，
    // 否则48px侧padding加在max-width外，会与内容列错位96px）
    box-sizing: border-box;
    margin: 20px auto 0;
    max-width: 1280px;
    border-radius: 24px;
    box-shadow: 0 10px 30px rgba(139, 92, 246, 0.14);
    .header-content {
      display: flex;
      align-items: center;
      gap: 14px;
      .el-icon {
        width: 52px;
        height: 52px;
        border-radius: 14px;
        background: rgba(255, 255, 255, 0.2);
        font-size: 26px;
      }
      h2 {
        font-size: 28px;
        font-weight: 800;
        margin: 0;
      }
      p {
        margin-top: 4px;
        font-size: 14px;
        opacity: 0.92;
      }
    }
    .search-box {
      width: 360px;
      :deep(.el-input__wrapper) {
        border-radius: 999px;
        box-shadow: none;
      }
    }
  }
  .content {
    display: block;
    position: relative;
    margin: 0 auto;
    width: 100%;
    max-width: 1280px;
    padding: 20px 0 30px;
    .recommend-section {
      // 定高侧栏：高度锁60vh与文章列表彻底解耦（列表换页/长短变化都不再传导），
      // 只顶对齐首篇文章，底端不追平——彻底消除翻页弹动
      position: absolute;
      top: 20px;
      left: 0;
      width: 280px;
      height: 60vh;
      // border-box必须补：无全局重置时padding加在width外，外宽312会压住文章列表12px
      box-sizing: border-box;
      background: white;
      border-radius: 12px;
      box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
      padding: 16px;
      display: flex;
      flex-direction: column;
      .section-title {
        font-size: 15px;
        font-weight: 700;
        color: #374151;
        margin-bottom: 14px;
        display: flex;
        align-items: center;
        gap: 6px;
        .el-icon {
          color: #f59e0b;
        }
      }
      .recommend-list {
        flex: 1;
        // 固定4篇+space-evenly撑满60vh定高，不滚动；矮屏极端溢出直接裁掉不出滚动条
        overflow: hidden;
        display: flex;
        flex-direction: column;
        justify-content: space-evenly;
        gap: 14px;
        .recommend-item {
          border-left: 4px solid #f59e0b;
          padding-left: 12px;
          cursor: pointer;
          transition: all 0.2s ease;
          h4 {
            font-size: 14px;
            font-weight: 700;
            color: #111827;
            line-height: 1.45;
          }
          p {
            margin-top: 6px;
            color: #6b7280;
            font-size: 12px;
            line-height: 1.5;
          }
          .read-count {
            margin-top: 10px;
            font-size: 12px;
            color: #6b7280;
            display: flex;
            align-items: center;
            gap: 6px;
          }
          &:hover {
            transform: translateX(3px);
          }
        }
      }
    }
    .article-list {
      // 让出绝对定位推荐栏的宽度（280卡 + 20间距）
      margin-left: 300px;
      .article-item {
        background: white;
        border-radius: 12px;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
        padding: 16px;
        margin-bottom: 20px;
        // 末篇不留尾随margin：推荐栏bottom锚点才能和最后一张卡底边严格齐平
        &:last-child {
          margin-bottom: 0;
        }
        display: flex;
        gap: 18px;
        cursor: pointer;
        transition: all 0.2s ease;
        // 高度恒定：标题nowrap+摘要clamp2行+meta单行，内容上界固定(~112)，
        // 用min-height把1行摘要的矮卡垫到同一高度，消除每页组合差异导致的列表总高抖动
        box-sizing: border-box;
        min-height: 148px;
        align-items: center;
        .article-cover {
          width: 96px;
          height: 96px;
          border-radius: 10px;
          flex-shrink: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          color: white;
          font-size: 32px;
          background: linear-gradient(135deg, #f59e0b 0%, #8b5cf6 100%);
        }
        .info {
          flex: 1;
          min-width: 0;
          .title {
            display: flex;
            align-items: center;
            gap: 10px;
            h3 {
              color: #111827;
              font-size: 18px;
              font-weight: 800;
              overflow: hidden;
              white-space: nowrap;
              text-overflow: ellipsis;
            }
          }
          .summary {
            margin: 10px 0 14px;
            color: #6b7280;
            font-size: 14px;
            line-height: 1.6;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
          }
          .article-meta {
            color: #78716c;
            font-size: 12px;
            .meta-item {
              display: flex;
              align-items: center;
              gap: 4px;
            }
            .author {
              color: #f59e0b;
              font-weight: 700;
            }
          }
        }
        &:hover {
          transform: translateY(-2px);
          box-shadow: 0 10px 24px rgba(139, 92, 246, 0.12);
        }
      }
    }
  }
  .pagination-wrapper {
    display: flex;
    justify-content: center;
    padding-bottom: 30px;
  }
}

.articleDetail-container {
  min-height: calc(100vh - 120px);
  background: linear-gradient(135deg, #fafbfc 0%, #f7f9fc 50%, #f2f6fa 100%);
  padding: 0 28px;
  .flex-box {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    .item {
      margin-right: 20px;
      display: flex;
      align-items: center;
      color: #6b7280;
      span {
        margin-left: 5px;
      }
    }
  }
  .header-section {
    background: linear-gradient(135deg, #f59e0b 0%, #8b5cf6 100%);
    color: white;
    padding: 36px 48px;
    // 阅读页整体窄一档（980），banner与内容列同宽对齐
    box-sizing: border-box;
    margin: 20px auto 0;
    max-width: 980px;
    border-radius: 24px;
    box-shadow: 0 10px 30px rgba(139, 92, 246, 0.14);
    .header-content {
      display: flex;
      align-items: center;
      gap: 12px;
      h2 {
        font-size: 26px;
        font-weight: 800;
        margin: 0;
      }
      p {
        margin-top: 4px;
        opacity: 0.92;
      }
    }
  }
  .content {
    margin: 0 auto;
    width: 100%;
    max-width: 980px;
    padding: 20px 0 30px;
    .diary-card {
      margin-bottom: 20px;
      background: white;
      border-radius: 10px;
      padding: 24px;
      box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
      .title {
        margin-bottom: 15px;
        font-size: 20px;
        font-weight: 700;
        color: #374151;
      }
      .sub-title {
        margin-top: 20px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        .category-tag {
          margin-right: 20px;
        }
      }
      .article-title {
        font-size: 28px;
        font-weight: 800;
        color: #111827;
        margin-top: 30px;
        margin-bottom: 10px;
        line-height: 1.35;
      }
      .summary-content {
        background: rgba(126, 211, 33, 0.1);
        border-left: 4px solid #7ed321;
        padding: 12px 15px;
        border-radius: 0 8px 8px 0;
        position: relative;
        color: #4b5563;
        line-height: 1.7;
      }
      .content-wrapper {
        margin-top: 24px;
        font-size: 15px;
        color: #374151;
        line-height: 1.8;
        :deep(p) {
          margin-bottom: 10px;
        }
        :deep(h1),
        :deep(h2),
        :deep(h3),
        :deep(h4),
        :deep(h5),
        :deep(h6) {
          margin: 15px 0 10px;
          color: #111827;
          font-weight: 700;
        }
        :deep(h2) {
          font-size: 18px;
          border-bottom: 2px solid #e5e7eb;
          padding-bottom: 5px;
        }
        :deep(h3) {
          font-size: 16px;
        }
        :deep(ul),
        :deep(ol) {
          padding-left: 18px;
          margin-bottom: 10px;
        }
        :deep(li) {
          margin-bottom: 5px;
        }
      }
      .tags-content {
        margin-top: 20px;
        padding-top: 15px;
        border-top: 1px solid #e5e7eb;
        .tags-title {
          margin-bottom: 10px;
          font-size: 14px;
          font-weight: 700;
          color: #374151;
        }
        .tags-list {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
        }
      }
    }
  }
}

@media (max-width: 900px) {
  .knowledge-container {
    .header-section {
      align-items: flex-start;
      flex-direction: column;
      padding: 30px 22px;
      .search-box {
        width: 100%;
      }
    }
    .content {
      .recommend-section {
        position: static;
        width: 100%;
        height: auto;
      }
      .article-list {
        margin-left: 0;
      }
    }
  }
}
</style>
