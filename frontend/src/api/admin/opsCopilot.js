import { requestAdmin } from '@/api/request'

export const opsCopilotApi = {
  ask: (body) => requestAdmin.post('/ops-copilot/ask', body),
}
