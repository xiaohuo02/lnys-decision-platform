import { requestAdmin } from '@/api/request'

export const auditApi = {
  getLogs: (params) => requestAdmin.get('/audit', { params }),
  getOne:  (id)     => requestAdmin.get(`/audit/${id}`),
}
