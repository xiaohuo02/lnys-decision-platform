import { requestBusiness } from '@/api/request'

export const customersApi = {
  getRfm:        (params) => requestBusiness.get('/customers/rfm', { params }),
  getSegments:   ()       => requestBusiness.get('/customers/segments'),
  getClv:        (params) => requestBusiness.get('/customers/clv', { params }),
  getChurnRisk:  (params) => requestBusiness.get('/customers/churn-risk', { params }),
  predictChurn:  (data)   => requestBusiness.post('/customers/predict-churn', data),
}
