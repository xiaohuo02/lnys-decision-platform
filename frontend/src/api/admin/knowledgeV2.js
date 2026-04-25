/**
 * 知识库中台 v2 API
 * 对接后端 /admin/knowledge/v2/* 接口
 */
import { requestAdmin } from '@/api/request'

export const knowledgeV2Api = {
  // ── 知识库 ──────────────────────────────────
  getLibraries:   (params)        => requestAdmin.get('/knowledge/v2/libraries', { params }),
  createLibrary:  (data)          => requestAdmin.post('/knowledge/v2/libraries', data),
  getLibrary:     (kbId)          => requestAdmin.get(`/knowledge/v2/libraries/${kbId}`),
  deleteLibrary:  (kbId)          => requestAdmin.delete(`/knowledge/v2/libraries/${kbId}`),

  // ── 文档 ────────────────────────────────────
  getDocuments:   (kbId, params)  => requestAdmin.get(`/knowledge/v2/libraries/${kbId}/documents`, { params }),
  createDocument: (kbId, data)    => requestAdmin.post(`/knowledge/v2/libraries/${kbId}/documents`, data),
  getDocument:    (docId)         => requestAdmin.get(`/knowledge/v2/documents/${docId}`),
  getChunks:      (docId, params) => requestAdmin.get(`/knowledge/v2/documents/${docId}/chunks`, { params }),
  getVersions:    (docId)         => requestAdmin.get(`/knowledge/v2/documents/${docId}/versions`),
  rollback:       (docId, data)   => requestAdmin.post(`/knowledge/v2/documents/${docId}/rollback`, data),
  reprocess:      (docId)         => requestAdmin.post(`/knowledge/v2/documents/${docId}/reprocess`),
  deleteDocument: (docId)         => requestAdmin.delete(`/knowledge/v2/documents/${docId}`),

  // ── 检索 ────────────────────────────────────
  search:         (data)          => requestAdmin.post('/knowledge/v2/search', data),

  // ── 统计 ────────────────────────────────────
  getStats:       (params)        => requestAdmin.get('/knowledge/v2/stats', { params }),

  // ── §3.4 反馈：admin 列表 + 聚合 ───────────────
  listFeedback:   (params)        => requestAdmin.get('/knowledge/v2/feedback',       { params }),
  getFeedbackStats: (params)      => requestAdmin.get('/knowledge/v2/feedback/stats', { params }),
}
