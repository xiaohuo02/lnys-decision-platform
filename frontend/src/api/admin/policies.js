import { requestAdmin } from '@/api/request'

export const policiesApi = {
  getList:   (params)    => requestAdmin.get('/policies', { params }),
  getOne:    (id)        => requestAdmin.get(`/policies/${id}`),
  create:    (body)      => requestAdmin.post('/policies', body),
  activate:  (id, body)  => requestAdmin.post(`/policies/${id}/activate`, body),
}
