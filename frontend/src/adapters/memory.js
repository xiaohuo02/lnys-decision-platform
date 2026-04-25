/**
 * Memory Adapter
 * 将后端记忆中心接口返回的原始数据转换为前端视图模型
 */

export function toMemoryRecords(raw) {
  const items = raw?.items ?? (Array.isArray(raw) ? raw : [])
  return {
    items: items.map(m => ({
      memoryId:       m?.memory_id ?? m?.id ?? m?.record_id ?? '',
      customerId:     m?.customer_id ?? '',
      contentSummary: m?.content_summary ?? m?.content ?? m?.summary ?? '',
      memoryKind:     m?.memory_kind ?? m?.memory_type ?? m?.type ?? '',
      sourceType:     m?.source_type ?? m?.source ?? '',
      riskLevel:      m?.risk_level ?? 'low',
      piiFlag:        m?.pii_flag ?? false,
      isActive:       m?.is_active ?? true,
      expiresAt:      m?.expires_at ?? null,
      feedback:       m?.feedback ?? m?.feedback_history ?? [],
      createdAt:      m?.created_at ?? '',
      updatedAt:      m?.updated_at ?? '',
    })),
    total: raw?.total ?? items.length,
    _degraded: !items.length && !raw,
  }
}

export function toMemoryDetail(raw) {
  if (!raw) return { _degraded: true }
  return {
    memoryId:       raw?.memory_id ?? raw?.id ?? '',
    customerId:     raw?.customer_id ?? '',
    contentSummary: raw?.content_summary ?? raw?.content ?? '',
    memoryKind:     raw?.memory_kind ?? '',
    sourceType:     raw?.source_type ?? '',
    riskLevel:      raw?.risk_level ?? 'low',
    piiFlag:        raw?.pii_flag ?? false,
    isActive:       raw?.is_active ?? true,
    expiresAt:      raw?.expires_at ?? null,
    feedback:       raw?.feedback ?? raw?.feedback_history ?? [],
    createdAt:      raw?.created_at ?? '',
    updatedAt:      raw?.updated_at ?? '',
    _degraded:      false,
  }
}
