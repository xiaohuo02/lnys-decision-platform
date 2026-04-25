import { requestAdmin } from '@/api/request'

export const teamApi = {
  getUsers:    (params) => requestAdmin.get('/team/users', { params }),
  getUser:     (id)     => requestAdmin.get(`/team/users/${id}`),
  createUser:  (data)   => requestAdmin.post('/team/users', data),
  assignRole:  (id, data) => requestAdmin.put(`/team/users/${id}/role`, data),
  disableUser: (id)     => requestAdmin.post(`/team/users/${id}/disable`),
  enableUser:  (id)     => requestAdmin.post(`/team/users/${id}/enable`),
  getRoles:    ()       => requestAdmin.get('/team/roles'),
}
