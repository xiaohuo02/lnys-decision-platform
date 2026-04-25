import { requestBusiness } from '@/api/request'

export const fraudApi = {
  getStats:        ()               => requestBusiness.get('/fraud/stats'),
  score:           (data)           => requestBusiness.post('/fraud/score', data),
  getPendingReviews: ()             => requestBusiness.get('/fraud/pending-reviews'),
  review:          (threadId, data) => requestBusiness.post(`/fraud/review/${threadId}`, data),
}
