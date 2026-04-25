import { requestAdmin } from '@/api/request'

export const agentsApi = {
  getOverview: () => requestAdmin.get('/agents/overview'),
}
