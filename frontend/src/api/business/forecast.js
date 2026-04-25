import { requestBusiness } from '@/api/request'

export const forecastApi = {
  getSummary: ()     => requestBusiness.get('/forecast/summary'),
  predict:    (data) => requestBusiness.post('/forecast/predict', data),
}
