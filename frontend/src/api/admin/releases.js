import { requestAdmin } from '@/api/request'

export const releasesApi = {
  getList:   (params)    => requestAdmin.get('/releases', { params }),
  getOne:    (id)        => requestAdmin.get(`/releases/${id}`),
  create:    (body)      => requestAdmin.post('/releases', body),
  rollback:  (id, body)  => requestAdmin.post(`/releases/${id}/rollback`, body),
}
