import { requestBusiness } from '@/api/request'

export const inventoryApi = {
  getStatus: () => requestBusiness.get('/inventory/status'),
  getAlerts: (params) => requestBusiness.get('/inventory/alerts', { params }),
  getAbcXyz: () => requestBusiness.get('/inventory/abc-xyz'),
  getTrend: (params) => requestBusiness.get('/inventory/trend', { params }),
}
