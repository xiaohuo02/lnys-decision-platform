import { requestBusiness } from '@/api/request'

export const chatApi = {
  sendMessage:    (data)      => requestBusiness.post('/chat/message', data),
  getHistory:     (sessionId) => requestBusiness.get(`/chat/history/${sessionId}`),
  deleteSession:  (sessionId) => requestBusiness.delete(`/chat/session/${sessionId}`),
}
