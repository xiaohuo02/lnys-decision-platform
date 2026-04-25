import { requestAdmin } from '@/api/request'

export const adminDashboardApi = {
  getSummary: () => requestAdmin.get('/dashboard/summary'),
}
