<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { consultationPage, sessionMessages } from '@/apis/admin'
import PageHead from '@/components/backend/PageHead.vue'

//咨询记录列表
const tableData = ref<any>([])
//分页
const pagination = ref<any>({
  pageNum: 1,
  pageSize: 10,
  total: 0
})

//会话记录详情弹窗
const currentSessionDetail = ref<any>(null)
const showDetailDialog = ref<boolean>(false)
const messagesList = ref<any>([])

//加载会话消息列表
const loadingMessage = ref<boolean>(false)

//点击详情按钮的时候，查看会话详情
const viewSessionDetail = async (row: any) => {
  //先填充基本信息，打开弹窗
  currentSessionDetail.value = row
  showDetailDialog.value = true
  //加载消息列表
  loadingMessage.value = true
  const res = await sessionMessages(row.id)
  messagesList.value = res
  loadingMessage.value = false
}

//分页改变时触发
const handleChange = (page: number) => {
  pagination.value.currentPage = page
  handleSearch({})
};
const handleSearch = async (formData: any) => {
  const params = {
    ...pagination.value,
    ...formData
  }
  const res = await consultationPage(params)
  tableData.value = res.records
  pagination.value.total = res.total || res.pages * pagination.value.size
};

onMounted(() => {
  consultationPage(pagination.value).then(res => {
    tableData.value = res.records
    pagination.value.total = res.total
    console.log(res)
  }).catch(err => {
    console.log(err)
  })

  //默认搜索
  handleSearch({})
})
</script>

<template>
  <div>
    <PageHead title="咨询记录" />
    <el-table :data="tableData" style="width: 100%">
      <el-table-column  label="会话ID" width="180" >
        <template #default="scope">
          <el-avatar :size="40" > {{ scope.row.userNickname }}</el-avatar>
        </template>
      </el-table-column>
      <el-table-column  label="情绪日志">
        <template #default="scope">
          <div class="session-title">
            {{ scope.row.sessionTitle }}
            <div class="session-preview">
              {{ scope.row.lastMessageContent }}
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="messageCount" label="消息数" width="100" />
      <el-table-column prop="lastMessageTime" label="时间" width="180" />
      <el-table-column  label="操作" width="100" >
        <template #default="scope">
          <el-button type="primary" text @click="viewSessionDetail(scope.row)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
      <el-pagination layout="prev, pager, next" 
      :total="pagination.total" 
      :page-size="pagination.size" 
      @change="handleChange" 
      style="margin-top: 25px;" />

      <!-- 会话记录详情弹窗 -->
     <el-dialog
      v-model="showDetailDialog"
      title="咨询会话详情"
      width="70%"
      :close-on-click-modal="false"
      >

      <div class="session-detail">
        <!-- 上半部分 -->
        <div class="detail-header">
          <div class="detail-row">
            <div class="detail-label">用户：</div>
            <div class="detail-value">{{ currentSessionDetail.userNickname }}</div>
          </div>
          <div class="detail-row">
            <div class="detail-label">开始时间：</div>
            <div class="detail-value">{{ currentSessionDetail.startedAt }}</div>
          </div>
          <div class="detail-row">
            <div class="detail-label">消息数：</div>
            <div class="detail-value">{{ currentSessionDetail.messageCount }}</div>
          </div>
        </div>
        <!-- 下半部分 -->
        <div class="messages-container">
          <div class="messages-header">
            <h4>对话记录</h4>
          </div>
          <div class="messages-list" v-loading="loadingMessage">
            <div v-for="item in messagesList" :key="item.id" class="message-item" :class="item.senderType === 1 ? 'user-message' : 'ai-message'">
              <div class="message-header">
                <div class="message-sender">{{ item.senderType === 1 ? '用户' : 'AI' }}</div>
                <div class="message-time">{{ item.createdAt }}</div>
              </div>
              <div class="message-content">{{ item.content }}</div>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button type="primary" @click="showDetailDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style lang="scss" scoped>
.session-title {
    font-weight: 500;
    color: #333;
    margin-bottom: 4px;
  }
  .session-preview {
    font-size: 13px;
    color: #666;
    margin-bottom: 4px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .session-detail {
    max-height: 70vh;
    overflow-y: auto;
    .detail-header {
      margin-bottom: 20px;
      padding: 16px;
      background: #f8f9fa;
      border-radius: 8px;
      border: 1px solid #e9ecef;
    }

    .detail-row {
      display: flex;
      align-items: center;
      margin-bottom: 8px;
      :last-child {
        margin-bottom: 0;
      }
      .detail-label {
        font-weight: 500;
        color: #495057;
        min-width: 80px;
        margin-right: 8px;
      }

      .detail-value {
        color: #333;
      }
    }
  }
  .messages-container {
    margin-top: 20px;
    .messages-header {
      margin-bottom: 16px;
      h4 {
        margin: 0;
        color: #333;
        font-size: 16px;
        font-weight: 500;
      }
    }
    .messages-list {
      max-height: 400px;
      overflow-y: auto;
      border: 1px solid #e9ecef;
      border-radius: 8px;
      padding: 16px;
      background: #fff;
      .message-item {
        margin-bottom: 12px;
        padding: 12px;
        border-radius: 8px;
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        :last-child {
          margin-bottom: 0;
        }
        &.user-message {
          background: #e8f4fd;
        }

        &.ai-message {
          background: #f0f9f0;
        }
      }
      .message-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
        .sender {
          font-weight: 500;
          color: #333;
          display: flex;
          align-items: center;
          gap: 4px;
        }

        .time {
          font-size: 12px;
          color: #999;
        }

        .message-content {
          color: #333;
          line-height: 1.6;
          white-space: pre-wrap;
          margin-top: 8px;
          font-size: 14px;
        }
      }
    }
  }
</style>
