import { requestAdmin } from '@/api/request'

export const reviewsApi = {
  getList:  (params)       => requestAdmin.get('/reviews', { params }),
  getOne:   (caseId)       => requestAdmin.get(`/reviews/${caseId}`),
  approve:  (caseId, body) => requestAdmin.post(`/reviews/${caseId}/approve`, body),
  edit:     (caseId, body) => requestAdmin.post(`/reviews/${caseId}/edit`, body),
  reject:   (caseId, body) => requestAdmin.post(`/reviews/${caseId}/reject`, body),
}
