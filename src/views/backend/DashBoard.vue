<script setup lang="ts">
import { getDashboardData } from "@/apis/admin";
import { ref, onMounted, nextTick } from "vue";
import * as echarts from "echarts";

const aiData = ref<any>({});

//图片插入
const iconUrl1 = new URL("@/assets/images/users.png", import.meta.url).href;
const iconUrl2 = new URL("@/assets/images/like.png", import.meta.url).href;
const iconUrl3 = new URL("@/assets/images/comments.png", import.meta.url).href;
const iconUrl4 = new URL("@/assets/images/smile.png", import.meta.url).href;

//情绪趋势分析图表
//echarts实例
let emotionChart: any = null;
let sessionChart: any = null;
let activeChart: any = null;

//DOM
const emotionChartRef = ref<any>(null);
const sessionChartRef = ref<any>(null);
const activeChartRef = ref<any>(null);

//初始化图表
const initChart = () => {
  initEmotionChart();
  initConsultationChart();
  initActiveChart();
};

const initEmotionChart = () => {
  if (!emotionChartRef.value) return;
  //销毁旧图表，避免重复渲染
  if (emotionChart) {
    emotionChart.dispose();
  }
  //获取情绪趋势数据
  const emotionData = aiData.value.emotionTrend;
  console.log(emotionData);
  //初始化新图表
  emotionChart = echarts.init(emotionChartRef.value);
  //配置
  const option = {
    title: {
      text: "情绪趋势分析",
      textStyle: {
        color: "#2d3436",
        fontSize: 16,
        fontWeight: 600,
      },
      left: "center",
      top: 10,
    },
    tooltip: {
      trigger: "axis",
      borderColor: "#fab1a0",
      borderWidth: 1,
      textStyle: {
        color: "#2d3436",
      },
    },
    legend: {
      data: ["平均情绪评分", "记录数量"],
      top: 40,
    },
    grid: {
      top: 80,
      bottom: "3%",
      left: "3%",
      right: "4%",
    },
    xAxis: {
      type: "category",
      data: emotionData.map((item: any) => item.date),
      axisLine: {
        lineStyle: {
          color: "#2d3436",
        },
      },
    },
    yAxis: [
      {
        type: "value",
        name: "情绪评分",
        position: "left",
        axisLabel: {
          lineStyle: {
            color: "#2d3436",
          },
        },
      },
      {
        type: "value",
        name: "记录数量",
        position: "right",
        axisLabel: {
          lineStyle: {
            color: "#2d3436",
          },
        },
      },
    ],
    series: [
      {
        name: "平均情绪评分",
        type: "line",
        data: emotionData.map((item: any) => item.avgMoodScore),
        smooth: true,
        lineStyle: {
          width: 3,
          color: "yellow",
        },
        itemStyle: {
          color: "yellow",
        },
      },
      {
        name: "记录数量",
        type: "line",
        data: emotionData.map((item: any) => item.recordCount),
        smooth: true,
        lineStyle: {
          width: 3,
          color: "orange",
        },
        itemStyle: {
          color: "orange",
        },
      },
    ],
  };
  //设置图表
  emotionChart.setOption(option);
};

const initConsultationChart = () => {
  if (!sessionChartRef.value) return;
  if (!aiData.value.consultationStats?.dailyTrend) return;
  //销毁旧图表，避免重复渲染
  if (sessionChart) {
    sessionChart.dispose();
  }
  //获取咨询会话数据
  const sessionData = aiData.value.consultationStats.dailyTrend;
  console.log(sessionData);
  //初始化新图表
  sessionChart = echarts.init(sessionChartRef.value);
  //配置
  const option = {
    title: {
      text: "咨询活动统计",
      textStyle: {
        fontSize: 16,
        fontWeight: 600,
        color: "#2d3436",
      },
      left: "center",
      top: 10,
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(255, 255, 255, 0.95)",
      borderColor: "#fab1a0",
      borderWidth: 1,
      textStyle: {
        color: "#2d3436",
      },
    },
    legend: {
      data: ["会话数量", "参与用户数"],
      top: 40,
      textStyle: {
        color: "#636e72",
      },
    },
    grid: {
      left: "3%",
      right: "4%",
      bottom: "3%",
      top: 80,
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: sessionData.map((item: any) => item.date),
      axisLine: {
        lineStyle: {
          color: "rgba(244, 162, 97, 0.3)",
        },
      },
      axisLabel: {
        color: "#636e72",
      },
    },
    yAxis: {
      type: "value",
      axisLabel: {
        color: "#636e72",
      },
      axisLine: {
        lineStyle: {
          color: "rgba(244, 162, 97, 0.3)",
        },
      },
      splitLine: {
        lineStyle: {
          color: "rgba(244, 162, 97, 0.1)",
        },
      },
    },
    series: [
      {
        name: "会话数量",
        type: "bar",
        data: sessionData.map((item: any) => item.sessionCount),
        itemStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "#74b9ff" },
              { offset: 1, color: "#0984e3" },
            ],
          },
        },
        barWidth: "40%",
      },
      {
        name: "参与用户数",
        type: "bar",
        data: sessionData.map((item: any) => item.userCount),
        itemStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "#fdcb6e" },
              { offset: 1, color: "#f39c12" },
            ],
          },
        },
        barWidth: "40%",
      },
    ],
  };
  //设置图表
  sessionChart.setOption(option);
};

const initActiveChart = () => {
  if (!activeChartRef.value) return;
  if (!aiData.value.userActivity) return;
  //销毁旧图表，避免重复渲染
  if (activeChart) {
    activeChart.dispose();
  }
  //获取用户活跃度数据
  const activityData = aiData.value.userActivity;
  console.log(activityData);
  //初始化新图表
  activeChart = echarts.init(activeChartRef.value);
  //配置
  const option = {
    title: {
      text: "用户活跃度趋势",
      textStyle: {
        fontSize: 16,
        fontWeight: 600,
        color: "#2d3436",
      },
      left: "center",
      top: 10,
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(255, 255, 255, 0.95)",
      borderColor: "#fab1a0",
      borderWidth: 1,
      textStyle: {
        color: "#2d3436",
      },
    },
    legend: {
      data: ["活跃用户", "新增用户", "日记用户", "咨询用户"],
      top: 40,
      textStyle: {
        color: "#636e72",
      },
    },
    grid: {
      left: "3%",
      right: "4%",
      bottom: "3%",
      top: 80,
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: activityData.map((item: any) => item.date),
      axisLine: {
        lineStyle: {
          color: "rgba(244, 162, 97, 0.3)",
        },
      },
      axisLabel: {
        color: "#636e72",
      },
    },
    yAxis: {
      type: "value",
      axisLabel: {
        color: "#636e72",
      },
      axisLine: {
        lineStyle: {
          color: "rgba(244, 162, 97, 0.3)",
        },
      },
      splitLine: {
        lineStyle: {
          color: "rgba(244, 162, 97, 0.1)",
        },
      },
    },
    series: [
      {
        name: "活跃用户",
        type: "line",
        data: activityData.map((item: any) => item.activeUsers),
        smooth: true,
        lineStyle: {
          width: 3,
          color: "#a29bfe",
        },
        itemStyle: {
          color: "#a29bfe",
        },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(162, 155, 254, 0.4)" },
              { offset: 1, color: "rgba(162, 155, 254, 0.1)" },
            ],
          },
        },
      },
      {
        name: "新增用户",
        type: "line",
        data: activityData.map((item: any) => item.newUsers),
        smooth: true,
        lineStyle: {
          width: 3,
          color: "#fdcb6e",
        },
        itemStyle: {
          color: "#fdcb6e",
        },
      },
      {
        name: "日记用户",
        type: "line",
        data: activityData.map((item: any) => item.diaryUsers),
        smooth: true,
        lineStyle: {
          width: 3,
          color: "#00b894",
        },
        itemStyle: {
          color: "#00b894",
        },
      },
      {
        name: "咨询用户",
        type: "line",
        data: activityData.map((item: any) => item.consultationUsers),
        smooth: true,
        lineStyle: {
          width: 3,
          color: "#fab1a0",
        },
        itemStyle: {
          color: "#fab1a0",
        },
      },
    ],
  };
  //设置图表
  activeChart.setOption(option);
};

onMounted(async () => {
  const res = await getDashboardData();
  aiData.value = res;
  console.log(res);
  initChart();
});
</script>

<template>
  <div class="dashboard-container">
    <el-row v-if="aiData.systemOverview" :gutter="24">
      <!-- 四个卡片 -->
      <el-col :span="6">
        <el-card>
          <div class="card-content">
            <div class="avatar users">
              <el-image
                style="width: 40px; height: 40px"
                :src="iconUrl1"
                alt="用户头像"
              />
            </div>
            <div class="info">
              <p class="title">总用户数</p>
              <p class="number">{{ aiData.systemOverview.totalUsers }}</p>
              <p class="subtitle-title">
                活跃用户：{{ aiData.systemOverview.activeUsers }}
              </p>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <div class="card-content">
            <div class="avatar like">
              <el-image
                style="width: 40px; height: 40px"
                :src="iconUrl2"
                alt="情绪日志"
              />
            </div>
            <div class="info">
              <p class="title">情绪日志</p>
              <p class="number">{{ aiData.systemOverview.totalDiaries }}</p>
              <p class="subtitle-title">
                今日新增：{{ aiData.systemOverview.todayNewDiaries }}
              </p>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <div class="card-content">
            <div class="avatar comments">
              <el-image
                style="width: 40px; height: 40px"
                :src="iconUrl3"
                alt="咨询会话"
              />
            </div>
            <div class="info">
              <p class="title">咨询会话</p>
              <p class="number">{{ aiData.systemOverview.totalSessions }}</p>
              <p class="subtitle-title">
                今日新增：{{ aiData.systemOverview.todayNewSessions }}
              </p>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <div class="card-content">
            <div class="avatar smile">
              <el-image
                style="width: 40px; height: 40px"
                :src="iconUrl4"
                alt="平均情绪"
              />
            </div>
            <div class="info">
              <p class="title">平均情绪</p>
              <p class="number">
                {{ aiData.systemOverview.avgMoodScore }} / 10
              </p>
              <p class="subtitle-title">情绪健康指数</p>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表1,2 -->
    <el-row :gutter="24" style="margin-top: 20px">
      <el-col :span="12">
        <el-card style="width: 100%">
          <template #header>
            <div class="card-header">情绪趋势分析</div>
            <div class="chart-content">
              <div
                ref="emotionChartRef"
                style="width: 100%; height: 300px"
              ></div>
            </div>
          </template>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card style="width: 100%">
          <template #header>
            <div class="card-header">咨询会话统计</div>
            <div class="chart-content">
              <div v-if="aiData.consultationStats" class="consultation-stats">
                <div class="stat-item">
                  <div class="stat-label">总会话数</div>
                  <p class="stat-value">
                    {{ aiData.consultationStats.totalSessions }}
                  </p>
                </div>
                <div class="stat-item">
                  <div class="stat-label">平均时长</div>
                  <p class="stat-value">
                    {{ aiData.consultationStats.avgDurationMinutes }} 分钟
                  </p>
                </div>
                <div class="stat-item">
                  <div class="stat-label">活跃用户</div>
                  <p class="stat-value">
                    {{ aiData.systemOverview.activeUsers }}
                  </p>
                </div>
              </div>
              <div
                ref="sessionChartRef"
                style="width: 100%; height: 260px"
              ></div>
            </div>
          </template>
        </el-card>
      </el-col>
    </el-row>

    <el-row style="margin-top: 20px">
      <el-card style="width: 100%">
        <template #header>
          <div class="card-header">用户活跃度趋势</div>
          <div class="chart-content">
            <div ref="activeChartRef" style="width: 100%; height: 300px"></div>
          </div>
        </template>
      </el-card>
    </el-row>
  </div>
</template>

<style scoped lang="scss">
.dashboard-container {
  .card-header {
    font-size: 16px;
    font-weight: 600;
    color: #2c3e50;
    padding-bottom: 10px;
    border-bottom: 2px solid #e0e6ed;
    box-shadow: 0 2px 4px -2px rgba(0, 0, 0, 0.15);
  }
  .card-content {
    display: flex;
    align-items: center;
    .avatar {
      margin-right: 12px;
      width: 60px;
      height: 60px;
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      &.users {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      }
      &.like {
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
      }
      &.comments {
        background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
      }
      &.smile {
        background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
      }
    }
    .info {
      .title {
        font-size: 14px;
        color: #7f8c8d;
        margin-bottom: 4px;
      }
      .value {
        font-size: 24px;
        font-weight: 700;
        color: #2c3e50;
        margin-bottom: 4px;
      }
      .subtitle-title {
        font-size: 12px;
        color: #95a5a6;
      }
    }
  }
  .chart-content {
    padding: 20px;
    height: 300px;
    position: relative;

    canvas {
      width: 100% !important;
      height: 100% !important;
    }

    .consultation-stats {
      display: flex;
      justify-content: space-around;
      margin-bottom: 20px;

      .stat-item {
        text-align: center;

        .stat-label {
          font-size: 12px;
          color: #7f8c8d;
          margin-bottom: 4px;
        }

        .stat-value {
          font-size: 18px;
          font-weight: 600;
          color: #2c3e50;
        }
      }
    }
  }
}
</style>
