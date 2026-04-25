import { requestAdmin } from '@/api/request'

export const memoryApi = {
  getRecords:  (params)     => requestAdmin.get('/memory/records', { params }),
  disable:     (id)         => requestAdmin.post(`/memory/records/${id}/disable`),
  expire:      (id)         => requestAdmin.post(`/memory/records/${id}/expire`),
  feedback:    (id, body)   => requestAdmin.post(`/memory/records/${id}/feedback`, body),
  getFeedback: (id)         => requestAdmin.get(`/memory/records/${id}/feedback`),
}
