/**
 * Sentiment Adapter
 * 将后端舆情分析接口返回的原始数据转换为前端视图模型
 * 隔离后端字段变化对页面组件的影响
 *
 * 后端 schema:
 *   overview → { positive_pct, negative_pct, neutral_pct, avg_score_7d, trend_30d[], alert }
 *   topics   → { topics: [{ id, label, keywords[] }] } 或直接 [{ id, label, keywords }]
 */

export function toSentimentOverview(raw) {
  if (!raw) return null
  return {
    positive_pct: raw.positive_pct ?? raw.positive ?? 0,
    negative_pct: raw.negative_pct ?? raw.negative ?? 0,
    neutral_pct:  raw.neutral_pct  ?? raw.neutral  ?? 0,
    avg_score_7d: raw.avg_score_7d ?? raw.avg_score ?? null,
    trend_30d:    raw.trend_30d    ?? raw.trend     ?? [],
    alert:        raw.alert        ?? false,
    _degraded:    !!raw._meta?.degraded,
  }
}

export function toSentimentTopics(raw) {
  const list = Array.isArray(raw) ? raw : (raw?.topics ?? raw?.items ?? [])
  const _inferCat = (label) => {
    if (/正面|好评/.test(label)) return '正面'
    if (/负面|差评/.test(label)) return '负面'
    return '中性'
  }
  return list.map((item, idx) => ({
    id:       item?.id       ?? idx,
    label:    item?.label    ?? item?.topic ?? item?.name ?? `Topic ${idx}`,
    category: item?.category ?? _inferCat(item?.label ?? ''),
    keywords: item?.keywords ?? [],
  }))
}
