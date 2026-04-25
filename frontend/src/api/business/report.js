import axios from 'axios'
import { requestBusiness } from '@/api/request'

function getToken() {
  return localStorage.getItem('token') || ''
}

export const reportApi = {
  getList:   (params) => requestBusiness.get('/reports', { params }),
  generate:  (data) => requestBusiness.post('/reports/generate', data),
  /**
   * 下载报告文件。
   * 使用独立 axios 实例避免 requestBusiness 拦截器对 blob 响应做 JSON 解包。
   * 处理后端返回 JSON 错误响应（如 404）和正常文件流两种情况。
   */
  download: async (id, format = 'markdown') => {
    const token = getToken()
    const res = await axios.get(`/api/reports/${id}/download`, {
      params: { format },
      responseType: 'blob',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    const blob = res.data
    // 如果返回的是 JSON（错误响应），解析并抛出
    if (blob.type && blob.type.includes('application/json')) {
      const text = await blob.text()
      const json = JSON.parse(text)
      throw new Error(json.message || '下载失败')
    }
    return blob
  },
}
