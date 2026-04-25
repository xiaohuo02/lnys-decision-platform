import { requestAdmin } from '@/api/request'

export const authApi = {
  login:    (body) => requestAdmin.post('/auth/login', body),
  register: (body) => requestAdmin.post('/auth/register', body),
  me:       ()     => requestAdmin.get('/auth/me'),
}
