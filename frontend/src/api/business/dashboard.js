import { requestBusiness } from '@/api/request'

export const dashboardApi = {
  getSummary: () => requestBusiness.get('/forecast/summary'),
  getKpis:    () => requestBusiness.get('/dashboard/kpis'),
  // getTrend 已移除：后端无 /dashboard/trend 端点
  // Dashboard.vue 使用 getSummary() 获取趋势数据
}
