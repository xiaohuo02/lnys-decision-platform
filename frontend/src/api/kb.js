/**
 * 知识库 API — 统一入口
 * 后端 KB CRUD / RAG 搜索 API 就绪后，此处切换到真实接口。
 */
import { requestBusiness } from './request'

export const kbApi = {
  /**
   * 向量检索
   * @param {{ query: string, collection?: string, top_k?: number }} params
   */
  search(params) {
    return requestBusiness.post('/kb/search', params).catch(() => {
      // graceful fallback — 后端尚未就绪时返回占位
      return { results: [] }
    })
  },

  /** 获取知识库集合列表 */
  listCollections() {
    return requestBusiness.get('/kb/collections').catch(() => [])
  },

  /** 获取单个文档详情 */
  getDocument(docId) {
    return requestBusiness.get(`/kb/documents/${docId}`)
  },

  /** 上传文档到知识库 */
  uploadDocument(collection, formData) {
    return requestBusiness.post(`/kb/collections/${collection}/documents`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
  },

  /** 删除文档 */
  deleteDocument(docId) {
    return requestBusiness.delete(`/kb/documents/${docId}`)
  },
}
