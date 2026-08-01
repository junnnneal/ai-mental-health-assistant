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
  isError?: boolean
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
