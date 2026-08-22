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

const scoreTone = (score: number, max: number) => {
  const ratio = score / max;
  if (ratio <= 0.2) {
    return "score-muted";
  }
  if (ratio <= 0.4) {
    return "score-cool";
  }
  if (ratio <= 0.6) {
    return "score-warm";
  }
  if (ratio <= 0.8) {
    return "score-bright";
  }
  return "score-vivid";
};

const moodScoreTone = computed(() => scoreTone(diaryForm.moodScore, 10));
const sleepScoreTone = computed(() => scoreTone(diaryForm.sleepQuality, 5));
const stressScoreTone = computed(() => scoreTone(diaryForm.stressLevel, 5));

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
    <header class="page-intro">
      <div class="intro-content">
        <div class="intro-icon" aria-hidden="true">
          <el-icon><EditPen /></el-icon>
        </div>
        <div>
          <span class="intro-kicker">每日自检</span>
          <h2>情绪日记</h2>
          <p>记录今天的情绪、触发因素和身体状态</p>
        </div>
      </div>
      <div class="current-date" aria-label="当前记录日期">
        <el-icon aria-hidden="true"><Calendar /></el-icon>
        <div>
          <span>记录日期</span>
          <strong>{{ diaryForm.diaryDate }}</strong>
        </div>
      </div>
    </header>

    <main class="content">
      <div class="diary-shell">
        <section class="diary-surface" aria-labelledby="diary-form-title">
          <div class="title-row">
            <div>
              <h3 id="diary-form-title" class="title">今日记录</h3>
              <p class="subtitle">把复杂感受拆成几个清楚的线索</p>
            </div>
          </div>

          <el-form
            ref="formRef"
            :model="diaryForm"
            :rules="rules"
            label-position="top"
            class="detail-form"
          >
          <div class="form-section form-section-first">
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
                  <el-slider
                    v-model="diaryForm.moodScore"
                    :min="1"
                    :max="10"
                  />
                  <span>{{ diaryForm.moodScore }} / 10</span>
                </div>
              </el-form-item>
            </div>
          </div>

          <div class="form-section">
            <el-form-item label="主要情绪" prop="dominantEmotion">
              <div class="emotion-grid">
                <button
                  v-for="emotion in emotionOptions"
                  :key="emotion.name"
                  type="button"
                  class="emotion-choice"
                  :class="[
                    emotion.tone,
                    { selected: diaryForm.dominantEmotion === emotion.name },
                  ]"
                  :aria-pressed="diaryForm.dominantEmotion === emotion.name"
                  @click="selectEmotion(emotion.name)"
                >
                  <el-icon
                    v-if="diaryForm.dominantEmotion === emotion.name"
                    aria-hidden="true"
                  >
                    <Check />
                  </el-icon>
                  <span>{{ emotion.name }}</span>
                  <span class="emotion-dot" aria-hidden="true"></span>
                </button>
              </div>
            </el-form-item>
          </div>

          <div class="form-section writing-section">
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
          </div>

          <section class="form-section wellbeing-section" aria-labelledby="wellbeing-title">
            <div class="section-heading">
              <h4 id="wellbeing-title">身体状态</h4>
              <p>用直觉评分即可，不必追求精确</p>
            </div>
            <div class="life-indicators">
              <div class="indicator-group">
                <div class="indicator-heading">
                  <el-icon aria-hidden="true"><Moon /></el-icon>
                  睡眠质量
                </div>
                <el-rate v-model="diaryForm.sleepQuality" :max="5" />
              </div>
              <div class="indicator-group">
                <div class="indicator-heading">
                  <el-icon aria-hidden="true"><Sunny /></el-icon>
                  压力水平
                </div>
                <el-rate v-model="diaryForm.stressLevel" :max="5" />
              </div>
            </div>
          </section>

          <div class="action-buttons">
            <el-button plain @click="resetForm">清空重写</el-button>
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
      </div>

      <div class="summary-shell">
        <aside class="summary-panel" aria-live="polite">
          <div class="summary-heading">
            <h3>今日状态</h3>
            <p>根据你的填写实时更新</p>
          </div>

        <div class="mood-summary">
          <div class="mood-score" :class="moodScoreTone">
            <strong>{{ diaryForm.moodScore }}</strong>
            <span>/ 10</span>
          </div>
          <div class="mood-copy">
            <h4>{{ moodLabel }}</h4>
            <p>主要情绪：{{ diaryForm.dominantEmotion }}</p>
          </div>
        </div>

        <div class="metric-list">
          <section
            class="metric-item sleep-metric"
            :class="sleepScoreTone"
            aria-label="睡眠质量"
          >
            <div class="metric-topline">
              <div class="metric-title">
                <el-icon aria-hidden="true"><Moon /></el-icon>
                <div>
                  <span>睡眠质量</span>
                  <p>{{ sleepLabel }}</p>
                </div>
              </div>
              <strong>{{ diaryForm.sleepQuality }}<small>/ 5</small></strong>
            </div>
            <div class="metric-scale" aria-hidden="true">
              <span
                v-for="step in 5"
                :key="step"
                :class="{ active: step <= diaryForm.sleepQuality }"
              ></span>
            </div>
          </section>

          <section
            class="metric-item stress-metric"
            :class="stressScoreTone"
            aria-label="压力水平"
          >
            <div class="metric-topline">
              <div class="metric-title">
                <el-icon aria-hidden="true"><Warning /></el-icon>
                <div>
                  <span>压力水平</span>
                  <p>{{ stressLabel }}</p>
                </div>
              </div>
              <strong>{{ diaryForm.stressLevel }}<small>/ 5</small></strong>
            </div>
            <div class="metric-scale" aria-hidden="true">
              <span
                v-for="step in 5"
                :key="step"
                :class="{ active: step <= diaryForm.stressLevel }"
              ></span>
            </div>
          </section>
        </div>

          <div class="gentle-note">
            <div class="note-title">
              <el-icon aria-hidden="true"><Warning /></el-icon>
              今日提醒
            </div>
            <p>
              如果情绪评分偏低或压力偏高，可以先减少任务密度，再处理最重要的一件事。
            </p>
          </div>
        </aside>
      </div>
    </main>
  </div>
</template>

<style scoped lang="scss">
.emotionDiary-container {
  --diary-bg: #f1f5f2;
  --diary-surface: #fbfcfb;
  --diary-surface-soft: #e3ebe6;
  --diary-text: #1f2924;
  --diary-text-soft: #637168;
  --diary-border: #d5e0d9;
  --diary-accent: #3f6855;
  --diary-accent-dark: #294b3c;
  --diary-accent-soft: #dce9e1;

  min-height: calc(100dvh - 120px);
  padding: 0 clamp(16px, 3vw, 40px);
  color: var(--diary-text);
  background:
    radial-gradient(circle at 8% 0%, rgba(63, 104, 85, 0.1), transparent 28rem),
    var(--diary-bg);
  font-family:
    "PingFang SC",
    "Microsoft YaHei",
    -apple-system,
    BlinkMacSystemFont,
    "Segoe UI",
    sans-serif;

  position: relative;
  isolation: isolate;

  &::before {
    position: absolute;
    inset: 0;
    z-index: -1;
    content: "";
    pointer-events: none;
    opacity: 0.5;
    background:
      radial-gradient(circle at 88% 32%, rgba(91, 128, 108, 0.08), transparent 18rem),
      repeating-linear-gradient(
        135deg,
        rgba(255, 255, 255, 0.14) 0,
        rgba(255, 255, 255, 0.14) 1px,
        transparent 1px,
        transparent 7px
      );
  }

  .page-intro {
    box-sizing: border-box;
    width: 100%;
    max-width: 1260px;
    margin: 0 auto;
    padding: 38px 8px 30px;
    display: flex;
    align-items: center;
    justify-content: space-between;

    .intro-content {
      display: flex;
      align-items: center;
      gap: 16px;

      .intro-icon {
        width: 50px;
        height: 50px;
        border-radius: 15px;
        color: #f7faf8;
        background: var(--diary-accent);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 23px;
        box-shadow: 0 12px 26px rgba(41, 75, 60, 0.18);
      }

      h2 {
        margin: 0;
        color: var(--diary-text);
        font-size: clamp(27px, 3vw, 34px);
        font-weight: 750;
        line-height: 1.15;
        letter-spacing: -0.035em;
        text-wrap: balance;
      }

      .intro-kicker {
        display: inline-flex;
        align-items: center;
        min-height: 22px;
        margin-bottom: 8px;
        padding: 3px 9px;
        color: var(--diary-accent-dark);
        border: 1px solid rgba(63, 104, 85, 0.16);
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.54);
        font-size: 10px;
        font-weight: 700;
        line-height: 1;
        letter-spacing: 0.16em;
      }

      p {
        max-width: 36rem;
        margin-top: 7px;
        color: var(--diary-text-soft);
        font-size: 14px;
        line-height: 1.6;
        text-wrap: pretty;
      }
    }

    .current-date {
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 170px;
      padding-left: 24px;
      border-left: 1px solid var(--diary-border);
      color: var(--diary-accent-dark);

      > .el-icon {
        font-size: 20px;
      }

      span {
        display: block;
        color: var(--diary-text-soft);
        font-size: 12px;
        line-height: 1.2;
      }

      strong {
        display: block;
        margin-top: 4px;
        font-size: 14px;
        font-weight: 700;
        line-height: 1.2;
        letter-spacing: 0.02em;
        font-variant-numeric: tabular-nums;
      }
    }
  }

  .content {
    width: 100%;
    max-width: 1260px;
    margin: 0 auto;
    padding: 0 0 48px;
    display: grid;
    grid-template-columns: minmax(0, 1fr) 300px;
    gap: clamp(22px, 3vw, 34px);
    align-items: start;

    .diary-shell,
    .summary-shell {
      padding: 6px;
      border: 1px solid rgba(63, 104, 85, 0.14);
      border-radius: 28px;
      background: rgba(232, 240, 235, 0.58);
      box-shadow:
        0 26px 70px rgba(34, 61, 49, 0.07),
        inset 0 1px 0 rgba(255, 255, 255, 0.74);
    }

    .diary-shell {
      animation: diary-rise 720ms cubic-bezier(0.32, 0.72, 0, 1) both;
    }

    .summary-shell {
      position: sticky;
      top: 20px;
      animation: diary-rise 820ms 80ms cubic-bezier(0.32, 0.72, 0, 1) both;
    }

    .diary-surface {
      padding: clamp(22px, 3vw, 34px);
      border: 1px solid var(--diary-border);
      border-radius: 22px;
      background: rgba(251, 252, 251, 0.96);
      box-shadow:
        0 18px 44px rgba(34, 61, 49, 0.06),
        inset 0 1px 0 rgba(255, 255, 255, 0.9);

      .title-row {
        margin-bottom: 26px;

        .title {
          margin: 0;
          color: var(--diary-text);
          font-size: 23px;
          font-weight: 720;
          line-height: 1.25;
          letter-spacing: -0.025em;
        }

        .subtitle {
          max-width: 38rem;
          margin-top: 7px;
          color: var(--diary-text-soft);
          font-size: 13px;
          line-height: 1.6;
        }
      }

      .detail-form {
        :deep(.el-form-item__label) {
          height: auto;
          margin-bottom: 9px;
          color: #304039;
          font-size: 14px;
          font-weight: 650;
          line-height: 1.25;
        }

        :deep(.el-form-item) {
          margin-bottom: 0;
        }

        :deep(.el-input__wrapper),
        :deep(.el-textarea__inner) {
          color: var(--diary-text);
          border-radius: 10px;
          background: #f7faf8;
          box-shadow: 0 0 0 1px #d2ddd6 inset;
          transition:
            background-color 180ms cubic-bezier(0.32, 0.72, 0, 1),
            box-shadow 180ms cubic-bezier(0.32, 0.72, 0, 1);
        }

        :deep(.el-input__wrapper) {
          min-height: 44px;
        }

        :deep(.el-textarea__inner) {
          padding: 13px 15px;
          line-height: 1.75;
        }

        :deep(.el-input__inner::placeholder),
        :deep(.el-textarea__inner::placeholder) {
          color: #718078;
        }

        :deep(.el-input__wrapper:hover),
        :deep(.el-textarea__inner:hover) {
          background: #ffffff;
          box-shadow: 0 0 0 1px #b3c7ba inset;
        }

        :deep(.el-input__wrapper.is-focus),
        :deep(.el-textarea__inner:focus) {
          background: #ffffff;
          box-shadow: 0 0 0 2px var(--diary-accent) inset;
        }

        :deep(.el-form-item.is-error .el-input__wrapper),
        :deep(.el-form-item.is-error .el-textarea__inner) {
          box-shadow: 0 0 0 1px var(--el-color-danger) inset;
        }

        :deep(.el-input__count) {
          color: #748078;
          background: transparent;
        }

        :deep(.el-slider) {
          --el-slider-main-bg-color: var(--diary-accent);
          --el-slider-runway-bg-color: #d5e0d9;
          --el-slider-stop-bg-color: #d5e0d9;
          --el-slider-button-size: 17px;
        }

        :deep(.el-slider__button) {
          border-color: var(--diary-accent);
        }

        :deep(.el-rate) {
          --el-rate-fill-color: var(--diary-accent);
          --el-rate-void-color: #becdc3;
          --el-rate-icon-size: 24px;
          height: 30px;
        }

        :deep(.el-button) {
          min-width: 108px;
          height: 44px;
          margin-left: 0;
          border-radius: 10px;
          font-weight: 650;
          transition:
            color 180ms cubic-bezier(0.32, 0.72, 0, 1),
            border-color 180ms cubic-bezier(0.32, 0.72, 0, 1),
            background-color 180ms cubic-bezier(0.32, 0.72, 0, 1),
            transform 180ms cubic-bezier(0.32, 0.72, 0, 1);
        }

        :deep(.el-button:not(.el-button--primary)) {
          color: #3b5045;
          border-color: #c3d2c8;
          background: transparent;
        }

        :deep(.el-button:not(.el-button--primary):hover) {
          color: var(--diary-accent-dark);
          border-color: #97b19f;
          background: var(--diary-accent-soft);
        }

        :deep(.el-button--primary) {
          border-color: var(--diary-accent);
          background: var(--diary-accent);
        }

        :deep(.el-button--primary:hover),
        :deep(.el-button--primary:focus-visible) {
          border-color: var(--diary-accent-dark);
          background: var(--diary-accent-dark);
        }

        :deep(.el-button:active) {
          transform: translateY(1px) scale(0.99);
        }

        .form-section {
          padding: 24px 0;
          border-top: 1px solid var(--diary-border);

          &.form-section-first {
            padding-top: 0;
            border-top: 0;
          }
        }

        .form-grid {
          display: grid;
          grid-template-columns: minmax(220px, 0.7fr) minmax(320px, 1.3fr);
          gap: 22px;
        }

        .full-control {
          width: 100%;
        }

        .score-control {
          width: 100%;
          display: grid;
          grid-template-columns: minmax(0, 1fr) 64px;
          gap: 16px;
          align-items: center;

          span {
            font-size: 13px;
            font-weight: 750;
            color: var(--diary-accent-dark);
            text-align: right;
            font-variant-numeric: tabular-nums;
          }
        }

        .emotion-grid {
          width: 100%;
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 9px;

          .emotion-choice {
            min-height: 52px;
            padding: 10px 13px;
            display: flex;
            align-items: center;
            justify-content: flex-start;
            gap: 10px;
            color: #445149;
            font: inherit;
            font-size: 14px;
            font-weight: 650;
            text-align: left;
            cursor: pointer;
            border: 1px solid #d5ddd8;
            border-radius: 10px;
            background: #f8faf8;
            transition:
              color 180ms cubic-bezier(0.32, 0.72, 0, 1),
              border-color 180ms cubic-bezier(0.32, 0.72, 0, 1),
              background-color 180ms cubic-bezier(0.32, 0.72, 0, 1),
              transform 180ms cubic-bezier(0.32, 0.72, 0, 1);

            .emotion-dot {
              width: 10px;
              height: 10px;
              flex: 0 0 auto;
              border-radius: 50%;
              background: var(--emotion-color);
              box-shadow: 0 0 0 4px var(--emotion-tint);
              transition:
                transform 420ms cubic-bezier(0.32, 0.72, 0, 1),
                box-shadow 420ms cubic-bezier(0.32, 0.72, 0, 1);
            }

            &.calm {
              --emotion-color: #23889a;
              --emotion-tint: #d4eef2;
              --emotion-selected: #e7f7f9;
              --emotion-ink: #176572;
            }

            &.bright {
              --emotion-color: #c28d3f;
              --emotion-tint: #f7ecd8;
              --emotion-selected: #fcf5e8;
              --emotion-ink: #8e672e;
            }

            &.fresh {
              --emotion-color: #3ba766;
              --emotion-tint: #d6f0df;
              --emotion-selected: #e8f8ed;
              --emotion-ink: #287343;
            }

            &.muted {
              --emotion-color: #96958d;
              --emotion-tint: #ecece8;
              --emotion-selected: #f5f5f2;
              --emotion-ink: #6d6d67;
            }

            &.warm {
              --emotion-color: #b87660;
              --emotion-tint: #f5e6e0;
              --emotion-selected: #fbefeb;
              --emotion-ink: #8f5747;
            }

            &.soft {
              --emotion-color: #8b7ba1;
              --emotion-tint: #eeeaf4;
              --emotion-selected: #f6f3fa;
              --emotion-ink: #69587f;
            }

            &.alert {
              --emotion-color: #aa6976;
              --emotion-tint: #f3e6ea;
              --emotion-selected: #faeff2;
              --emotion-ink: #884f5d;
            }

            &.green {
              --emotion-color: #cf7c23;
              --emotion-tint: #f6e5ce;
              --emotion-selected: #fff2df;
              --emotion-ink: #925c18;
            }

            &:hover {
              color: var(--emotion-ink);
              border-color: var(--emotion-color);
              background: var(--emotion-selected);

              .emotion-dot {
                transform: scale(1.18);
                box-shadow: 0 0 0 5px var(--emotion-tint);
              }
            }

            &:focus-visible {
      outline: 3px solid rgba(63, 104, 85, 0.22);
              outline-offset: 2px;
            }

            &:active {
              transform: translateY(1px) scale(0.99);
            }

            &.selected {
              color: var(--emotion-ink);
              border-color: var(--emotion-color);
              background: var(--emotion-selected);
              box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.78),
                0 8px 18px var(--emotion-tint);

              .emotion-dot {
                transform: scale(1.16);
                box-shadow: 0 0 0 5px var(--emotion-tint);
              }
            }

            .el-icon {
              flex: 0 0 auto;
              color: var(--emotion-color);
              font-size: 15px;
            }

            .emotion-dot {
              margin-left: auto;
            }
          }
        }

        .writing-section {
          display: grid;
          gap: 22px;
        }

        .section-heading {
          margin-bottom: 16px;

          h4 {
            color: var(--diary-text);
            font-size: 15px;
            font-weight: 700;
            line-height: 1.3;
          }

          p {
            margin-top: 5px;
            color: var(--diary-text-soft);
            font-size: 12px;
            line-height: 1.5;
          }
        }

        .life-indicators {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 0;
          padding: 4px 0;

          .indicator-group {
            min-width: 0;

            &:last-child {
              padding-left: 28px;
              border-left: 1px solid var(--diary-border);
            }

            .indicator-heading {
              display: flex;
              align-items: center;
              gap: 8px;
              margin-bottom: 12px;
              color: #3d4942;
              font-size: 14px;
              font-weight: 650;

              .el-icon {
                color: var(--diary-accent);
                font-size: 17px;
              }
            }
          }
        }

        .action-buttons {
          padding-top: 26px;
          display: flex;
          justify-content: flex-end;
          gap: 12px;
          border-top: 1px solid var(--diary-border);
        }
      }
    }

    .summary-panel {
      position: static;
      padding: 26px;
      border: 1px solid #d1ddd5;
      border-radius: 22px;
      background: var(--diary-surface);

      .score-muted {
        --score-color: #8999a6;
        --score-track: #dce5ea;
        --score-glow: rgba(137, 153, 166, 0.2);
      }

      .score-cool {
        --score-color: #4c88b4;
        --score-track: #d2e4ef;
        --score-glow: rgba(76, 136, 180, 0.2);
      }

      .score-warm {
        --score-color: #bd8a3d;
        --score-track: #f0e3c9;
        --score-glow: rgba(189, 138, 61, 0.2);
      }

      .score-bright {
        --score-color: #3e9d69;
        --score-track: #d3ecdc;
        --score-glow: rgba(62, 157, 105, 0.22);
      }

      .score-vivid {
        --score-color: #15966b;
        --score-track: #c9eadb;
        --score-glow: rgba(21, 150, 107, 0.26);
      }

      .stress-metric.score-muted {
        --score-color: #5b9a72;
        --score-track: #d7eddf;
        --score-glow: rgba(91, 154, 114, 0.2);
      }

      .stress-metric.score-cool {
        --score-color: #82a75a;
        --score-track: #e1ecd4;
        --score-glow: rgba(130, 167, 90, 0.2);
      }

      .stress-metric.score-warm {
        --score-color: #c2933e;
        --score-track: #f1e5cb;
        --score-glow: rgba(194, 147, 62, 0.2);
      }

      .stress-metric.score-bright {
        --score-color: #db7b3f;
        --score-track: #f6dfd1;
        --score-glow: rgba(219, 123, 63, 0.22);
      }

      .stress-metric.score-vivid {
        --score-color: #d34d58;
        --score-track: #f3d5d9;
        --score-glow: rgba(211, 77, 88, 0.26);
      }

      .summary-heading {
        h3 {
          color: var(--diary-text);
          font-size: 18px;
          font-weight: 720;
          line-height: 1.3;
          letter-spacing: -0.02em;
        }

        p {
          margin-top: 5px;
          color: var(--diary-text-soft);
          font-size: 12px;
          line-height: 1.5;
        }
      }

      .mood-summary {
        display: flex;
        align-items: center;
        gap: 18px;
        padding: 26px 0 24px;

        .mood-score {
          width: 92px;
          height: 96px;
          flex: 0 0 auto;
          display: flex;
          align-items: center;
          justify-content: center;
          border-radius: 18px;
          color: #f5f8f6;
          background: var(--score-color);
          box-shadow: 0 14px 28px var(--score-glow);
          font-variant-numeric: tabular-nums;
          transition:
            background-color 420ms cubic-bezier(0.32, 0.72, 0, 1),
            box-shadow 420ms cubic-bezier(0.32, 0.72, 0, 1);

          strong {
            font-size: 36px;
            font-weight: 750;
            line-height: 1;
            letter-spacing: -0.05em;
          }

          span {
            margin-left: 4px;
            font-size: 11px;
            font-weight: 600;
            opacity: 0.78;
          }
        }

        .mood-copy {
          min-width: 0;

          h4 {
            color: var(--diary-text);
            font-size: 18px;
            font-weight: 720;
            line-height: 1.3;
          }

          p {
            margin-top: 6px;
            color: var(--diary-text-soft);
            font-size: 12px;
            line-height: 1.5;
            word-break: break-word;
          }
        }
      }

      .metric-list {
        border-top: 1px solid #cbd8d0;

        .metric-item {
          padding: 20px 0;
          border-bottom: 1px solid #cbd8d0;

          .metric-topline {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;

            .metric-title {
              display: flex;
              align-items: center;
              gap: 10px;

              > .el-icon {
                flex: 0 0 auto;
                color: var(--score-color);
                font-size: 18px;
                transition: color 420ms cubic-bezier(0.32, 0.72, 0, 1);
              }

              span {
                display: block;
                color: #344139;
                font-size: 13px;
                font-weight: 680;
                line-height: 1.3;
              }

              p {
                margin-top: 4px;
                color: var(--diary-text-soft);
                font-size: 12px;
                line-height: 1.3;
              }
            }

            > strong {
              color: var(--diary-text);
              font-size: 20px;
              font-weight: 750;
              font-variant-numeric: tabular-nums;

              small {
                margin-left: 3px;
                color: var(--diary-text-soft);
                font-size: 11px;
                font-weight: 600;
              }
            }
          }

          .metric-scale {
            margin-top: 14px;
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 6px;

            span {
              height: 5px;
              border-radius: 2px;
              background: var(--score-track);
              transition:
                background-color 220ms cubic-bezier(0.32, 0.72, 0, 1),
                transform 220ms cubic-bezier(0.32, 0.72, 0, 1);

              &.active {
                background: var(--score-color);
                transform: scaleY(1.35);
              }
            }
          }
        }
      }

      .gentle-note {
        padding-top: 22px;

        .note-title {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 8px;
          color: var(--diary-accent-dark);
          font-size: 13px;
          font-weight: 700;

          .el-icon {
            font-size: 16px;
          }
        }

        p {
          max-width: 30ch;
          color: #58665e;
          font-size: 13px;
          line-height: 1.7;
          text-wrap: pretty;
        }
      }
    }
  }
}

@keyframes diary-rise {
  from {
    opacity: 0;
    transform: translateY(18px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 1180px) {
  .emotionDiary-container {
    .content {
      grid-template-columns: 1fr;

      .summary-shell {
        position: static;
      }

      .summary-panel {
        display: grid;
        grid-template-columns: minmax(0, 0.8fr) minmax(300px, 1.2fr);
        column-gap: 34px;

        .summary-heading,
        .gentle-note {
          grid-column: 1 / -1;
        }

        .metric-list {
          border-top: 0;
        }

        .gentle-note p {
          max-width: 58ch;
        }
      }
    }
  }
}

@media (max-width: 760px) {
  .emotionDiary-container {
    padding: 0 14px;

    .page-intro {
      padding: 26px 4px 22px;
      align-items: flex-start;
      flex-direction: column;
      gap: 20px;

      .intro-content {
        align-items: flex-start;

        .intro-icon {
          width: 44px;
          height: 44px;
          border-radius: 13px;
          font-size: 20px;
        }
      }

      .current-date {
        width: 100%;
        min-width: 0;
        padding: 16px 0 0;
        border-top: 1px solid var(--diary-border);
        border-left: 0;
      }
    }

    .content {
      padding-bottom: 28px;
      gap: 16px;

      .diary-surface {
        padding: 20px 16px;
        border-radius: 18px;

        .title-row {
          margin-bottom: 22px;
        }

        .detail-form {
          .form-grid,
          .life-indicators {
            grid-template-columns: 1fr;
          }

          .form-grid {
            gap: 22px;
          }

          .emotion-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }

          .life-indicators {
            .indicator-group:last-child {
              margin-top: 18px;
              padding: 18px 0 0;
              border-top: 1px solid var(--diary-border);
              border-left: 0;
            }
          }

          .action-buttons {
            gap: 9px;

            :deep(.el-button) {
              flex: 1;
              min-width: 0;
            }

            :deep(.el-button--primary) {
              flex: 1.35;
            }
          }
        }
      }

      .summary-panel {
        padding: 22px 20px;
        border-radius: 18px;
        display: block;

        .metric-list {
          border-top: 1px solid #cbd8d0;
        }

        .gentle-note p {
          max-width: none;
        }
      }
    }
  }
}

@media (prefers-reduced-motion: reduce) {
  .emotionDiary-container {
    *,
    *::before,
    *::after {
      scroll-behavior: auto !important;
      transition-duration: 0.01ms !important;
      animation-duration: 0.01ms !important;
      animation-iteration-count: 1 !important;
    }
  }
}
</style>
