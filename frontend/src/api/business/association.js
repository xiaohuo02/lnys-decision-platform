import { requestBusiness } from '@/api/request'

export const associationApi = {
  getRules:     (params)         => requestBusiness.get('/association/rules', { params }),
  getRecommend: (skuCode, params) => requestBusiness.get(`/association/recommend/${skuCode}`, { params }),
  getGraph:     (params)         => requestBusiness.get('/association/graph', { params }),
  getSkuRules:  (skuCode, params) => requestBusiness.get(`/association/sku/${skuCode}/rules`, { params }),
}
