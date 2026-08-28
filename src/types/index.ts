import type { RouteRecordRaw } from 'vue-router'

export interface RouterConfig {
  path: string
  name: string
  component: RouteRecordRaw['component']
  children?: RouterConfig[]
}

export interface MenuItem {
  id: string
  label: string
  path: string
  icon?: string
  children?: MenuItem[]
}

export interface RouteMenu {
  path: string
  meta: {
    title: string
    icon: string
  }
}

/** 用户信息 */
export interface UserInfo {
  id: number
  username: string
  email: string
  nickname: string
  avatar: string
  birthday: string
  gender: number
  genderDisplayName: string
  phone: string
  status: number
  userType: number
  userTypeDisplayName: string
  createdAt: string
  updatedAt: string
}

/** 登录接口返回的 data */
export interface LoginResult {
  token: string
  roleType: string
  userInfo: UserInfo
}

export interface FormOption {
  label: string
  value: string
}

export interface FormColConfig {
  xs: number
  sm: number
  md: number
  lg: number
  xl: number
}

/** 通用搜索表单项配置 */
export interface FormItemConfig {
  prop: string
  label: string
  comp: string
  placeholder?: string
  options?: FormOption[]
  col?: FormColConfig
}

/** AI 咨询会话列表项 */
export interface SessionHistoryItem {
  id?: number | string
  sessionId?: number | string
  status: string
  sessionTitle: string
  startedAt?: string
  lastMessageContent?: string
  messageCount?: number
  durationMinutes?: number
}

/** RAG引用来源卡片数据 */
export interface MessageCitation {
  //来源序号，对应AI回答中的[1][2]标注
  index: number
  articleId: number | string
  articleTitle: string
  heading: string
}

/** 自检声明的三档标注（supported有依据 / beyond资料外建议 / unsupported与资料不符） */
export interface MessageVerifyClaim {
  text: string
  status: 'supported' | 'beyond' | 'unsupported'
}

/** RAG回答生成后幻觉自检结果（服务端verify事件下发） */
export interface MessageVerify {
  //pass全有依据 / warn有资料外建议 / fail有与资料不符的声明（服务端从claims重算）
  verdict: 'pass' | 'warn' | 'fail'
  supported: number
  beyond: number
  //与资料不符的声明文本列表（重点列出问题项）
  unsupported: string[]
  //逐条声明明细（展开徽章时只展示非supported项）
  claims: MessageVerifyClaim[]
  //回答与引用块的最大余弦相似度（辅助信号，自检或对齐失败时缺失）
  alignment?: number | null
}

/** AI 咨询消息 */
export interface ChatMessage {
  id: number | string
  sessionId?: number | string
  senderType: number | string
  senderTypeDesc?: string
  messageType?: number
  messageTypeDesc?: string
  content: string
  contentLength?: number
  contentPreview?: string
  createdAt: string
  //前端标记：该消息是错误提示（不参与本地持久化）
  isError?: boolean
  //RAG检索命中的参考来源（随消息一起本地持久化）
  citations?: MessageCitation[]
  //生成后幻觉自检结果（随消息一起本地持久化）
  verify?: MessageVerify
}

/** 情绪花园展示数据 */
export interface EmotionGarden {
  primaryEmotion: string
  emotionScore: number
  isNegative: boolean
  summary: string
  suggestion: string
  riskLevel: 'low' | 'medium' | 'high'
  actionItems: string[]
}

/** 情绪日记表单/提交数据 */
export interface EmotionDiaryPayload {
  diaryDate: string
  moodScore: number
  dominantEmotion: string
  emotionTriggers: string
  diaryContent: string
  sleepQuality: number
  stressLevel: number
}

export type DiaryForm = EmotionDiaryPayload

export interface KnowledgeArticlePageParams {
  sortField: string
  sortDirection: string
  currentPage: string | number
  size: string | number
}

export interface ArticleItem {
  id: number | string
  title: string
  summary?: string
  content?: string
  articleContent?: string
  categoryName?: string
  category?: string
  categoryId?: number | string
  authorName?: string
  readCount?: number
  tags?: string | string[]
  coverUrl?: string
  updatedAt?: string
  createdAt?: string
}
