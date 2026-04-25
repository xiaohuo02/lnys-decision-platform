import { requestAdmin } from '@/api/request'

export const knowledgeApi = {
  getFAQs:    (params)             => requestAdmin.get('/knowledge/faqs', { params }),
  getFAQ:     (id)                 => requestAdmin.get(`/knowledge/faqs/${id}`),
  createFAQ:  (body)               => requestAdmin.post('/knowledge/faqs', body),
  disableFAQ: (id)                 => requestAdmin.post(`/knowledge/faqs/${id}/disable`),
}
