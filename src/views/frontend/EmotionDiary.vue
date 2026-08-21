<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import { createOrUpdateEmotionDiary } from "@/apis/frontEnd";
import type { DiaryForm } from "@/types";
import {
  Calendar,
  Check,
  EditPen,
  Moon,
  RefreshLeft,
  Sunny,
  Warning,
} from "@element-plus/icons-vue";

const formRef = ref<FormInstance>();
const isSaving = ref(false);

//取本地日期：toISOString是UTC，北京时间早8点前会得到昨天，
//日记会被记到前一天、进而覆盖前一天那条（接口按diaryDate一天一条）
const getToday = () => {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
};

const defaultForm = (): DiaryForm => ({
  diaryDate: getToday(),
  moodScore: 6,
  dominantEmotion: "平静",
  emotionTriggers: "",
  diaryContent: "",
  sleepQuality: 3,
  stressLevel: 3,
});

const diaryForm = reactive<DiaryForm>(defaultForm());

const emotionOptions = [
  { name: "平静", tone: "calm" },
  { name: "开心", tone: "bright" },
  { name: "期待", tone: "fresh" },
  { name: "疲惫", tone: "muted" },
  { name: "焦虑", tone: "warm" },
  { name: "低落", tone: "soft" },
  { name: "烦躁", tone: "alert" },
  { name: "感激", tone: "green" },
];

const rules: FormRules<DiaryForm> = {
  diaryDate: [{ required: true, message: "请选择记录日期", trigger: "change" }],
  moodScore: [{ required: true, message: "请选择情绪评分", trigger: "change" }],
  dominantEmotion: [
    { required: true, message: "请选择主要情绪", trigger: "change" },
  ],
  emotionTriggers: [
    { required: true, message: "请输入情绪触发因素", trigger: "blur" },
  ],
  diaryContent: [
    { required: true, message: "请输入今日感想", trigger: "blur" },
  ],
  sleepQuality: [
    { required: true, message: "请选择睡眠质量", trigger: "change" },
  ],
  stressLevel: [
    { required: true, message: "请选择压力水平", trigger: "change" },
  ],
};

const moodLabel = computed(() => {
  if (diaryForm.moodScore >= 8) {
    return "状态很好";
  }
  if (diaryForm.moodScore >= 5) {
    return "整体平稳";
  }
  return "需要照顾";
});

const stressLabel = computed(() => {
  if (diaryForm.stressLevel >= 4) {
    return "压力偏高";
  }
  if (diaryForm.stressLevel >= 2) {
    return "压力适中";
  }
  return "压力较低";
});

const sleepLabel = computed(() => {
  if (diaryForm.sleepQuality >= 4) {
    return "睡眠不错";
  }
  if (diaryForm.sleepQuality >= 2) {
    return "睡眠一般";
  }
  return "需要补眠";
});

const selectEmotion = (emotion: string) => {
  diaryForm.dominantEmotion = emotion;
};

const resetForm = () => {
  Object.assign(diaryForm, defaultForm());
  formRef.value?.clearValidate();
};

const submitDiary = async () => {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) {
    return;
  }

  isSaving.value = true;
  try {
    await createOrUpdateEmotionDiary({ ...diaryForm });
    //保存成功后清空表单回到默认值；失败不动，避免用户已填内容丢失
    resetForm();
    ElMessage.success("情绪日记保存成功");
  } catch (error) {
    ElMessage.error("情绪日记保存失败");
    console.error("情绪日记保存失败", error);
  } finally {
    isSaving.value = false;
  }
};
</script>

<template>
  <div class="emotionDiary-container">
    <section class="header-section">
      <div class="header-content">
        <div class="header-icon">
          <el-icon><EditPen /></el-icon>
        </div>
        <div>
          <h2>情绪日记</h2>
          <p>记录今天的情绪、触发因素和身体状态</p>
        </div>
      </div>
      <div class="header-date">
        <el-icon><Calendar /></el-icon>
        {{ diaryForm.diaryDate }}
      </div>
    </section>

    <main class="content">
      <section class="diary-card">
        <div class="title-row">
          <div>
            <h3 class="title">今日记录</h3>
            <p class="subtitle">把复杂感受拆成几个清楚的线索</p>
          </div>
          <el-button text :icon="RefreshLeft" @click="resetForm">
            重置
          </el-button>
        </div>

        <el-form
          ref="formRef"
          :model="diaryForm"
          :rules="rules"
          label-position="top"
          class="detail-form"
        >
          <div class="form-grid">
            <el-form-item label="记录日期" prop="diaryDate">
              <el-date-picker
                v-model="diaryForm.diaryDate"
                type="date"
                value-format="YYYY-MM-DD"
                placeholder="选择日期"
                class="full-control"
              />
            </el-form-item>

            <el-form-item label="情绪评分" prop="moodScore">
              <div class="score-control">
                <el-slider v-model="diaryForm.moodScore" :min="1" :max="10" />
                <span>{{ diaryForm.moodScore }} / 10</span>
              </div>
            </el-form-item>
          </div>

          <el-form-item label="主要情绪" prop="dominantEmotion">
            <div class="emotion-grid">
              <button
                v-for="emotion in emotionOptions"
                :key="emotion.name"
                type="button"
                class="emotion-card"
                :class="[
                  emotion.tone,
                  { selected: diaryForm.dominantEmotion === emotion.name },
                ]"
                @click="selectEmotion(emotion.name)"
              >
                <span class="emotion-dot"></span>
                <span class="emotion-name">{{ emotion.name }}</span>
              </button>
            </div>
          </el-form-item>

          <el-form-item label="情绪触发因素" prop="emotionTriggers">
            <el-input
              v-model="diaryForm.emotionTriggers"
              placeholder="例如：沟通、学习、工作、睡眠、关系变化"
              maxlength="120"
              show-word-limit
            />
          </el-form-item>

          <el-form-item label="今日感想" prop="diaryContent">
            <el-input
              v-model="diaryForm.diaryContent"
              type="textarea"
              :rows="6"
              maxlength="800"
              show-word-limit
              resize="none"
              placeholder="写下今天发生了什么，以及它让你产生了什么感受"
            />
          </el-form-item>

          <div class="life-indicators">
            <div class="indicator-group">
              <div class="indicator-heading">
                <el-icon><Moon /></el-icon>
                睡眠质量
              </div>
              <el-rate v-model="diaryForm.sleepQuality" :max="5" />
            </div>
            <div class="indicator-group">
              <div class="indicator-heading">
                <el-icon><Sunny /></el-icon>
                压力水平
              </div>
              <el-rate v-model="diaryForm.stressLevel" :max="5" />
            </div>
          </div>

          <div class="action-buttons">
            <el-button @click="resetForm">清空重写</el-button>
            <el-button
              type="primary"
              :icon="Check"
              :loading="isSaving"
              @click="submitDiary"
            >
              保存日记
            </el-button>
          </div>
        </el-form>
      </section>

      <aside class="summary-panel">
        <div class="summary-score">
          <div class="score-ring">
            <span>{{ diaryForm.moodScore }}</span>
            <small>情绪分</small>
          </div>
          <div>
            <h3>{{ moodLabel }}</h3>
            <p>主要情绪：{{ diaryForm.dominantEmotion }}</p>
          </div>
        </div>

        <div class="summary-list">
          <div class="summary-item">
            <div class="item-top">
              <span class="item-icon"><el-icon><Moon /></el-icon></span>
              <div class="item-title">
                <span>{{ sleepLabel }}</span>
                <p>睡眠质量</p>
              </div>
              <b>{{ diaryForm.sleepQuality }}<i>/ 5</i></b>
            </div>
            <div class="item-bar">
              <i :style="{ width: (diaryForm.sleepQuality / 5) * 100 + '%' }"></i>
            </div>
          </div>
          <div class="summary-item">
            <div class="item-top">
              <span class="item-icon"><el-icon><Warning /></el-icon></span>
              <div class="item-title">
                <span>{{ stressLabel }}</span>
                <p>压力水平</p>
              </div>
              <b>{{ diaryForm.stressLevel }}<i>/ 5</i></b>
            </div>
            <div class="item-bar">
              <i :style="{ width: (diaryForm.stressLevel / 5) * 100 + '%' }"></i>
            </div>
          </div>
        </div>

        <div class="gentle-note">
          <div class="note-title">今日提醒</div>
          <p>
            如果情绪评分偏低或压力偏高，可以先减少任务密度，再处理最重要的一件事。
          </p>
        </div>
      </aside>
    </main>
  </div>
</template>

<style scoped lang="scss">
.emotionDiary-container {
  min-height: calc(100vh - 120px);
  background: linear-gradient(135deg, #fafbfc 0%, #fffaf3 52%, #f2f7f5 100%);
  // 页面级左右留白：banner和内容列都在这个栅格里居中
  padding: 0 28px;
  .header-section {
    background: linear-gradient(135deg, #22c55e 0%, #f59e0b 100%);
    color: white;
    padding: 34px 48px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 10px 30px rgba(34, 197, 94, 0.12);
    // 四角全圆的浮动卡片：与下方内容列同宽居中，边缘落在同一栅格上
    // box-sizing必须显式补：项目没引base.css，全局无border-box，
    // 默认content-box会把48px侧padding加在max-width外，外宽变1376与内容列错位
    box-sizing: border-box;
    margin: 20px auto 0;
    max-width: 1280px;
    border-radius: 24px;
    .header-content {
      display: flex;
      align-items: center;
      gap: 14px;
      .header-icon {
        width: 52px;
        height: 52px;
        border-radius: 14px;
        background: rgba(255, 255, 255, 0.22);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 24px;
      }
      h2 {
        margin: 0;
        font-size: 28px;
        font-weight: 800;
      }
      p {
        margin-top: 4px;
        font-size: 14px;
        opacity: 0.92;
      }
    }
    .header-date {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 14px;
      font-weight: 600;
      background: rgba(255, 255, 255, 0.18);
      border: 1px solid rgba(255, 255, 255, 0.28);
      border-radius: 999px;
      padding: 8px 14px;
    }
  }
  .content {
    width: 100%;
    // 限宽居中：今日记录收窄，仪表盘离开屏幕右缘
    max-width: 1280px;
    margin: 0 auto;
    padding: 24px 0 36px;
    display: grid;
    grid-template-columns: minmax(0, 1fr) 320px;
    gap: 20px;
    // start是sticky生效的前提：grid默认stretch会把子项拉满整行高度，
    // 拉满后没有富余空间，position:sticky就不会动
    align-items: start;
    .diary-card,
    .summary-panel {
      background: rgba(255, 255, 255, 0.96);
      border-radius: 16px;
      border: 1px solid rgba(245, 158, 11, 0.1);
      box-shadow:
        0 12px 36px rgba(251, 146, 60, 0.08),
        0 4px 14px rgba(15, 23, 42, 0.04);
    }
    .diary-card {
      padding: 24px;
      .title-row {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        margin-bottom: 22px;
        .title {
          margin: 0;
          font-size: 22px;
          font-weight: 800;
          color: #1f2937;
        }
        .subtitle {
          margin-top: 4px;
          font-size: 13px;
          color: #78716c;
        }
      }
      .detail-form {
        :deep(.el-form-item__label) {
          color: #374151;
          font-weight: 700;
          line-height: 1.2;
          margin-bottom: 8px;
        }
        :deep(.el-input__wrapper),
        :deep(.el-textarea__inner) {
          border-radius: 8px;
          box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.24) inset;
        }
        :deep(.el-input__wrapper.is-focus),
        :deep(.el-textarea__inner:focus) {
          box-shadow: 0 0 0 1px #f59e0b inset;
        }
        .form-grid {
          display: grid;
          grid-template-columns: 260px minmax(0, 1fr);
          gap: 18px;
        }
        .full-control {
          width: 100%;
        }
        .score-control {
          width: 100%;
          display: grid;
          grid-template-columns: minmax(0, 1fr) 70px;
          gap: 14px;
          align-items: center;
          span {
            font-size: 13px;
            font-weight: 700;
            color: #f59e0b;
            text-align: right;
          }
        }
        .emotion-grid {
          width: 100%;
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 10px;
          .emotion-card {
            min-height: 58px;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 10px 12px;
            display: flex;
            align-items: center;
            gap: 10px;
            cursor: pointer;
            background: #f9fafb;
            transition: all 0.2s ease;
            .emotion-dot {
              width: 12px;
              height: 12px;
              border-radius: 50%;
              background: #94a3b8;
              flex-shrink: 0;
            }
            .emotion-name {
              color: #374151;
              font-weight: 700;
            }
            &.calm .emotion-dot {
              background: #38bdf8;
            }
            &.bright .emotion-dot {
              background: #facc15;
            }
            &.fresh .emotion-dot {
              background: #22c55e;
            }
            &.muted .emotion-dot {
              background: #94a3b8;
            }
            &.warm .emotion-dot {
              background: #fb923c;
            }
            &.soft .emotion-dot {
              background: #a78bfa;
            }
            &.alert .emotion-dot {
              background: #f43f5e;
            }
            &.green .emotion-dot {
              background: #10b981;
            }
            &.selected {
              border-color: #f59e0b;
              background: #fff7ed;
              box-shadow: 0 6px 16px rgba(245, 158, 11, 0.12);
              transform: translateY(-1px);
            }
          }
        }
        .life-indicators {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 16px;
          margin-top: 8px;
          .indicator-group {
            border: 1px solid rgba(148, 163, 184, 0.18);
            border-radius: 10px;
            padding: 14px;
            background: #fbfcfb;
            .indicator-heading {
              display: flex;
              align-items: center;
              gap: 8px;
              margin-bottom: 10px;
              color: #374151;
              font-weight: 700;
            }
          }
        }
        .action-buttons {
          margin-top: 24px;
          display: flex;
          justify-content: flex-end;
          gap: 12px;
        }
      }
    }
    .summary-panel {
      padding: 24px;
      // 自然高度 + 吸顶：卡片多高就多高，下滑时钉在视口顶部跟随，
      // 右侧始终有内容（不再等高拉伸、也不再滑走缺块）
      position: sticky;
      top: 18px;
      .summary-score {
        display: flex;
        align-items: center;
        gap: 16px;
        padding-bottom: 20px;
        border-bottom: 1px solid rgba(148, 163, 184, 0.16);
        .score-ring {
          width: 100px;
          height: 100px;
          border-radius: 50%;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          background:
            radial-gradient(circle at center, #fff 58%, transparent 60%),
            conic-gradient(#22c55e 0%, #facc15 48%, #fb7185 100%);
          color: #7c2d12;
          flex-shrink: 0;
          span {
            font-size: 30px;
            line-height: 1;
            font-weight: 800;
          }
          small {
            margin-top: 4px;
            color: #8b7355;
          }
        }
        h3 {
          font-size: 20px;
          font-weight: 800;
          color: #1f2937;
          margin-bottom: 4px;
        }
        p {
          color: #78716c;
          font-size: 13px;
        }
      }
      .summary-list {
        display: flex;
        flex-direction: column;
        gap: 14px;
        padding: 20px 0;
        .summary-item {
          border: 1px solid rgba(148, 163, 184, 0.18);
          border-radius: 12px;
          padding: 14px;
          background: #fbfcfb;
          .item-top {
            display: flex;
            align-items: center;
            gap: 10px;
            .item-icon {
              width: 36px;
              height: 36px;
              border-radius: 10px;
              flex-shrink: 0;
              display: flex;
              align-items: center;
              justify-content: center;
              font-size: 17px;
              color: #f59e0b;
              background: #fff7ed;
            }
            .item-title {
              flex: 1;
              min-width: 0;
              span {
                display: block;
                color: #374151;
                font-weight: 700;
                font-size: 15px;
              }
              p {
                margin-top: 2px;
                color: #78716c;
                font-size: 12px;
              }
            }
            b {
              font-size: 20px;
              font-weight: 800;
              color: #1f2937;
              i {
                font-style: normal;
                font-size: 12px;
                color: #a8a29e;
                margin-left: 2px;
              }
            }
          }
          .item-bar {
            margin-top: 12px;
            height: 6px;
            border-radius: 999px;
            background: rgba(148, 163, 184, 0.2);
            overflow: hidden;
            i {
              display: block;
              height: 100%;
              border-radius: inherit;
              background: linear-gradient(90deg, #22c55e 0%, #f59e0b 100%);
              transition: width 0.3s ease;
            }
          }
        }
      }
      .gentle-note {
        // 紧跟指标卡片自然排列；等高拉伸的留白留在卡片底部，
        // 比把提醒顶到底、中间空一大块更自然
        border-radius: 12px;
        background: linear-gradient(135deg, #fff7ed 0%, #f0fdf4 100%);
        border: 1px solid rgba(245, 158, 11, 0.14);
        padding: 16px;
        .note-title {
          color: #92400e;
          font-weight: 800;
          margin-bottom: 6px;
        }
        p {
          color: #6b5b47;
          font-size: 13px;
          line-height: 1.6;
        }
      }
    }
  }
}

@media (max-width: 1180px) {
  .emotionDiary-container {
    .content {
      grid-template-columns: 1fr;
    }
  }
}

@media (max-width: 720px) {
  .emotionDiary-container {
    .header-section {
      padding: 24px 20px;
      align-items: flex-start;
      flex-direction: column;
      gap: 14px;
    }
    .content {
      padding: 16px 0;
      .diary-card {
        padding: 18px;
        .title-row {
          gap: 12px;
          flex-direction: column;
        }
        .detail-form {
          .form-grid,
          .life-indicators {
            grid-template-columns: 1fr;
          }
          .emotion-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
        }
      }
    }
  }
}
</style>
