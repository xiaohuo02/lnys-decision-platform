// frontend/src/api/admin.js
// 桥接文件：重新导出 api/admin/ 目录下的所有模块
// 现有 console 页面 import { adminApi } 时仍可兼容
// 新代码请直接从 '@/api/admin/xxx' 引入具体模块

export {
  authApi,
  adminDashboardApi,
  tracesApi,
  reviewsApi,
  promptsApi,
  policiesApi,
  releasesApi,
  auditApi,
  knowledgeApi,
  memoryApi,
  opsCopilotApi,
  evalsApi,
} from './admin/index'
