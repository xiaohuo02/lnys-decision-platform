import { requestWorkflow } from '@/api/request'

export const workflowApi = {
  // workflow 运行
  run:       (body)   => requestWorkflow.post('/workflows/run', body),
  getStatus: (runId)  => requestWorkflow.get(`/workflows/${runId}/status`),
  cancel:    (runId)  => requestWorkflow.post(`/workflows/${runId}/cancel`),

  // agents
  getAgents: (params) => requestWorkflow.get('/agents', { params }),
  getAgent:  (id)     => requestWorkflow.get(`/agents/${id}`),
}
