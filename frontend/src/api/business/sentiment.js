import { requestBusiness } from '@/api/request'

export const sentimentApi = {
  getOverview:    ()     => requestBusiness.get('/sentiment/overview'),
  getTopics:      ()     => requestBusiness.get('/sentiment/topics'),
  analyze:        (data) => requestBusiness.post('/sentiment/analyze', data),
  getReviewQueue: ()     => requestBusiness.get('/sentiment/reviews'),
  resolveReview:  (data) => requestBusiness.post('/sentiment/reviews/resolve', data),
  // 知识库
  getKBStats:     ()     => requestBusiness.get('/sentiment/kb/stats'),
  searchSimilar:  (data) => requestBusiness.post('/sentiment/kb/search', data),
  searchEntity:   (entity, days = 7) => requestBusiness.get(`/sentiment/kb/entity/${entity}`, { params: { days } }),
}
