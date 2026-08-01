<script setup lang="ts">
import { ref, onMounted } from 'vue'
import PageHead from '@/components/backend/PageHead.vue'
import TableSearch from '@/components/backend/TableSearch.vue'
import { moodLogPage, deleteMoodLog } from '@/apis/admin'
import { ElMessage, ElMessageBox } from 'element-plus'

const formItem = ref([
  {
    prop: "userId",
    label: "用户ID",
    comp: "input",
    placeholder: "请输入用户ID",
  },
  {
    prop: "moodScore",
    label: "情绪评分",
    comp: "select",
    placeholder: "请选择评分范围",
    options: [
      { label: "全部", value: "" },
      { label: "低分（1-3分）", value: "1-3" },
      { label: "中分（4-6分）", value: "4-6" },
      { label: "高分（7-10分）", value: "7-10" },
    ],
  },
])

// 表格数据
const tableData = ref<any>([])

//分页参数
const pagination = ref<any>({
  currentPage: 1,
  size: 10,
  total: 0,
})

// 会话详情弹窗
const detailDialogVisible = ref(false)
// 会话详情数据
const detailData = ref<any>({})

//ai数据转换
const aiData = ref<any>(null)

// 根据情绪类型返回对应的标签类型
const getEmotionTagType = (emotion: string) => {
  const emotionTypes: Record<string, string> = {
    '快乐': 'success',
    '平静': 'info',
    '兴奋': 'warning',
    '愤怒': 'danger',
    '悲伤': 'info',
    '焦虑': 'warning'
  }
  return emotionTypes[emotion] || 'info'
}

// 根据情绪评分返回对应的进度条颜色
const getEmotionScoreColor = (score: number) => {
  if (score >= 80) return '#f56c6c'
  if (score >= 60) return '#e6a23c'
  if (score >= 40) return '#909399'
  return '#67c23a'
}

const handleSearch = async (formData: any) => {
  const params = {
    ...pagination.value,
    ...formData
  }
  const res = await moodLogPage(params)
  tableData.value = res.records
  pagination.value.total = res.total || res.pages * pagination.value.size
};

//分页改变时触发
const handleChange = (page: number) => {
  pagination.value.currentPage = page
  handleSearch({})
};

// 查看会话详情
const viewSessionDetail = (row: any) => {
  console.log(row)
  detailData.value = row
  aiData.value = row.aiEmotionAnalysis ? JSON.parse(row.aiEmotionAnalysis) : null
  detailDialogVisible.value = true
}


// 删除情绪日志
const handleDelete = async (row: any) => {
  ElMessageBox.confirm('确认删除这条记录吗？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
      await deleteMoodLog(row.id)
      ElMessage.success('删除成功')
      handleSearch({})
  })
}

onMounted(() => {
  handleSearch({})
})
</script>


<template>
  <div>
    <PageHead title="情绪日志" />
    <TableSearch :formItem="formItem" @search="handleSearch" />

  <el-table :data="tableData" style="width: 100%; margin-top: 25px;">
    <el-table-column prop="id" label="用户ID" width="80" fixed="left" />
     <el-table-column  label="会话ID" width="80" >
        <template #default="scope">
          <el-avatar :size="40" > {{ scope.row.nickname }}</el-avatar>
        </template>
      </el-table-column>
     <el-table-column prop="diaryDate" label="记录日期" width="180" />
     <el-table-column  label="情绪评分"  >
        <template #default="scope">
          <el-rate v-model="scope.row.moodScore" disabled :max="10" :size="24"></el-rate>
        </template>
      </el-table-column>
     <el-table-column  label="生活指标" width="180" >
        <template #default="scope">
          <div>
            <p>睡眠：{{ scope.row.sleepQuality }} / 5</p>
            <p>压力：{{ scope.row.stressLevel }} / 5</p>  
          </div>
        </template>
      </el-table-column>
     <el-table-column prop="emotionTriggers" label="情绪触发因素" width="180" />
     <el-table-column prop="diaryContent" label="日记内容" width="180" />
     <el-table-column  label="操作" width="200" fixed="right" >
        <template #default="scope">
          <el-button type="primary" text @click="viewSessionDetail(scope.row)">详情</el-button>
          <el-button type="danger" text @click="handleDelete(scope.row)">删除</el-button>
        </template>
      </el-table-column>
  </el-table>

  <!-- 分页 -->
      <el-pagination layout="prev, pager, next" 
      :total="pagination.total" 
      :page-size="pagination.size" 
      @change="handleChange" 
      style="margin-top: 25px;" />

     <el-dialog 
      v-model="detailDialogVisible" 
      title="情绪日志详情" 
      :close-on-click-modal="false" 
      width="800px"
     >
      <!-- 会话详情内容 -->
      <div v-if="detailData.userId" class="detail-content">
          <div class="detail-section">
            <h4>用户信息</h4>
            <el-descriptions :column="2" border> 
              <el-descriptions-item label="用户名">{{ detailData.username }}</el-descriptions-item>
              <el-descriptions-item label="昵称">{{ detailData.nickname }}</el-descriptions-item>
              <el-descriptions-item label="用户ID">{{ detailData.userId }}</el-descriptions-item>
              <el-descriptions-item label="记录日期">{{ detailData.diaryDate }}</el-descriptions-item>
            </el-descriptions>
          </div>
          <div class="detail-section">
            <h4>情绪状态</h4>
            <el-descriptions :column="2" border> 
              <el-descriptions-item label="情绪评分">
                <el-rate v-model="detailData.moodScore" disabled :max="10" :size="24"></el-rate>
              </el-descriptions-item>
              <el-descriptions-item label="主要情绪">
                <el-tag :type="getEmotionTagType(detailData.dominantEmotion)">
                  {{ detailData.dominantEmotion || '无' }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="睡眠质量">{{ detailData.sleepQuality || '无' }} / 5</el-descriptions-item>
              <el-descriptions-item label="压力水平">{{ detailData.stressLevel || '无' }} / 5</el-descriptions-item>
            </el-descriptions>
          </div>
          <div class="detail-section">
            <h4>日记内容</h4>
            <el-descriptions :column="1" border> 
              <el-descriptions-item label="情绪触发因素">{{ detailData.emotionTriggers || '无' }}</el-descriptions-item>
              <el-descriptions-item label="日记内容">{{ detailData.diaryContent || '无' }}</el-descriptions-item>
            </el-descriptions>
          </div>
          <div v-if="aiData" class="detail-section">
            <h4>AI情绪分析结果</h4>
            <el-descriptions :column="2" border> 
              <el-descriptions-item label="主要情绪">
                <el-tag :type="getEmotionTagType(aiData.primaryEmotion)">
                  {{ aiData.primaryEmotion }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="情绪强度">
                <el-progress :percentage="aiData.emotionScore" :color="getEmotionScoreColor(aiData.emotionScore)" :stroke-width="8" />
              </el-descriptions-item>
              <el-descriptions-item label="风险等级">
                <el-tag :type="getEmotionTagType(aiData.riskLevel)">
                  {{ aiData.riskLevel }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="情绪性质">
                <el-tag :type="aiData.isNegative ? 'danger' : 'success'">
                  {{ aiData.isNegative ? '负面' : '正面' }}
                </el-tag>
              </el-descriptions-item>
            </el-descriptions>
          <!--ai部分-->
          <div class="ai-analysis-result">
            <div class="ai-suggestion-section">
              <h5>专业建议</h5>
              <div class="suggestion-content">{{ aiData.suggestion || '无' }}</div>
            </div>
            <div class="ai-risk-section">
              <h5>风险描述</h5>
              <div class="risk-content">{{ aiData.riskDescription || '无' }}</div>
            </div>
            <div class="ai-improvements-section">
              <h5>改善建议</h5>
              <ul class="improvement-list" v-for="item in aiData.improvementSuggestions" :key="item">
                <li>{{ item || '无' }}</li>
              </ul>
            </div>
          </div>
        </div>
        <div class="detail-section">
          <h4>时间信息</h4>
          <el-descriptions :column="2" border> 
            <el-descriptions-item label="创建时间">{{ detailData.createdAt }}</el-descriptions-item>
            <el-descriptions-item label="更新时间">{{ detailData.updatedAt }}</el-descriptions-item>
          </el-descriptions>
        </div>
      </div>
      <template #footer>
        <el-button  @click="detailDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
.detail-content {
  .detail-section {
    margin-bottom: 24px;
    
    h4 {
      margin: 0 0 16px 0;
      color: #303133;
      font-size: 16px;
      
      i {
        margin-right: 8px;
        color: #409eff;
      }
    }
  }
}

// AI分析相关样式
.ai-analysis-status {
  .ai-status-tag {
    margin-bottom: 4px;
    
    i {
      margin-right: 4px;
    }
  }
  
  .ai-analysis-preview {
    font-size: 11px;
    color: #909399;
    margin-top: 2px;
  }
}

.ai-analysis-result {
  .ai-keywords-section,
  .ai-suggestion-section,
  .ai-risk-section,
  .ai-improvements-section {
    margin-top: 16px;
    padding: 12px;
    background-color: #f8f9fa;
    border-radius: 4px;
    
    h5 {
      margin: 0 0 8px 0;
      color: #606266;
      font-size: 14px;
      font-weight: 600;
      
      i {
        margin-right: 6px;
        color: #909399;
      }
    }
  }
  
  .keywords-container {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    
    .keyword-tag {
      background-color: #e1f3d8;
      color: #67c23a;
      border-color: #b3d8a4;
    }
  }
  
  .suggestion-content,
  .risk-content {
    line-height: 1.6;
    color: #606266;
    background-color: white;
    padding: 8px;
    border-radius: 4px;
    border: 1px solid #ebeef5;
  }
  
  .improvement-list {
    margin: 0;
    padding-left: 20px;
    
    li {
      margin-bottom: 4px;
      color: #606266;
      line-height: 1.5;
    }
  }
  
  .ai-analysis-meta {
    margin-top: 16px;
    padding-top: 12px;
    border-top: 1px solid #ebeef5;
    
    .analysis-time {
      margin: 0;
      font-size: 12px;
      color: #909399;
      
      i {
        margin-right: 4px;
      }
    }
  }
  
  .el-progress {
    .el-progress__text {
      font-size: 12px !important;
    }
  }
}
</style>
