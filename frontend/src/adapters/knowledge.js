/**
 * Knowledge Adapter
 * 将后端知识库接口返回的原始数据转换为前端视图模型
 */

export function toFAQList(raw) {
  const items = raw?.items ?? (Array.isArray(raw) ? raw : [])
  return {
    items: items.map(d => ({
      docId:     d?.doc_id ?? d?.id ?? d?.faq_id ?? '',
      title:     d?.title ?? d?.question ?? '',
      content:   d?.content ?? d?.answer ?? '',
      groupName: d?.group_name ?? d?.category ?? 'general',
      source:    d?.source ?? '',
      isActive:  d?.is_active ?? true,
      createdBy: d?.created_by ?? '',
      createdAt: d?.created_at ?? '',
      updatedAt: d?.updated_at ?? '',
    })),
    total: raw?.total ?? items.length,
    _degraded: !items.length && !raw,
  }
}

export function toFAQDetail(raw) {
  if (!raw) return { _degraded: true }
  return {
    docId:     raw?.doc_id ?? raw?.id ?? '',
    title:     raw?.title ?? raw?.question ?? '',
    content:   raw?.content ?? raw?.answer ?? '',
    groupName: raw?.group_name ?? 'general',
    source:    raw?.source ?? '',
    isActive:  raw?.is_active ?? true,
    createdBy: raw?.created_by ?? '',
    createdAt: raw?.created_at ?? '',
    updatedAt: raw?.updated_at ?? '',
    _degraded: false,
  }
}
