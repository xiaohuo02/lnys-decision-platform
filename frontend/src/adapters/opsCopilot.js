/**
 * Ops Copilot Adapter
 * 将后端 Ops Copilot 接口返回的原始数据转换为前端视图模型
 */

export function toCopilotReply(raw) {
  if (!raw) return { answer: '', structuredData: null, suggestedActions: [], relatedRuns: [], intent: null, confidence: null, sources: [], _degraded: true, _fallback: true }
  return {
    answer:           raw?.answer ?? raw?.reply ?? raw?.content ?? '',
    structuredData:   raw?.data ?? raw?.structured_data ?? null,
    suggestedActions: raw?.suggested_actions ?? raw?.actions ?? [],
    relatedRuns:      raw?.related_runs ?? raw?.runs ?? [],
    intent:           raw?.intent ?? null,
    confidence:       raw?.confidence ?? null,
    sources:          raw?.sources ?? raw?.references ?? [],
    traceId:          raw?.trace_id ?? raw?.traceId ?? null,
    _degraded:        raw?._meta?.degraded ?? raw?.degraded ?? false,
    _fallback:        raw?.fallback ?? false,
  }
}
