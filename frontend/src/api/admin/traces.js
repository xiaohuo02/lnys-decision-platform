import { requestAdmin } from '@/api/request'

export const tracesApi = {
  getList:   (params) => requestAdmin.get('/traces', { params }),
  getDetail: (runId)  => requestAdmin.get(`/traces/${runId}`),
  replay:    (runId)  => requestAdmin.post(`/traces/${runId}/replay`),
  getStats:  (params) => requestAdmin.get('/traces/stats', { params }),
  exportDownload: (params) => requestAdmin.get('/traces/export', {
    params,
    responseType: 'blob',
    transformResponse: [(data) => data],
  }),
}
