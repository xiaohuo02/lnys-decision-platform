import { requestAdmin } from '@/api/request'

export const promptsApi = {
  getList:  (params)    => requestAdmin.get('/prompts', { params }),
  getOne:   (id)        => requestAdmin.get(`/prompts/${id}`),
  create:   (body)      => requestAdmin.post('/prompts', body),
  release:  (id, body)  => requestAdmin.post(`/prompts/${id}/release`, body),
}
