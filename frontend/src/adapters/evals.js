/**
 * Evals Adapter
 * 将后端评测中心接口返回的原始数据转换为前端视图模型
 */

export function toDatasetList(raw) {
  const items = raw?.items ?? (Array.isArray(raw) ? raw : [])
  return {
    items: items.map(d => ({
      id:        d?.dataset_id ?? d?.id ?? '',
      name:      d?.name ?? '',
      taskType:  d?.task_type ?? '',
      itemCount: d?.item_count ?? d?.sample_count ?? 0,
      createdBy: d?.created_by ?? '',
      createdAt: d?.created_at ?? '',
    })),
    total: raw?.total ?? items.length,
    _degraded: !items.length && !raw,
  }
}

export function toEvaluatorList(raw) {
  const items = raw?.items ?? (Array.isArray(raw) ? raw : [])
  return {
    items: items.map(e => ({
      id:        e?.evaluator_id ?? e?.id ?? '',
      name:      e?.name ?? '',
      taskType:  e?.task_type ?? '',
      version:   e?.version ?? 1,
      rules:     e?.scoring_rules ?? {},
      createdBy: e?.created_by ?? '',
      createdAt: e?.created_at ?? '',
    })),
    total: raw?.total ?? items.length,
    _degraded: !items.length && !raw,
  }
}

export function toExperimentList(raw) {
  const items = raw?.items ?? (Array.isArray(raw) ? raw : [])
  return {
    items: items.map(e => ({
      id:            e?.experiment_id ?? e?.id ?? '',
      name:          e?.name ?? '',
      status:        e?.status ?? 'unknown',
      datasetId:     e?.dataset_id ?? '',
      evaluatorId:   e?.evaluator_id ?? '',
      targetType:    e?.target_type ?? '',
      targetId:      e?.target_id ?? e?.agent_name ?? '',
      targetVersion: e?.target_version ?? '',
      totalCases:    e?.total_cases ?? 0,
      passRate:      e?.pass_rate ?? null,
      createdBy:     e?.created_by ?? '',
      createdAt:     e?.created_at ?? '',
    })),
    total: raw?.total ?? items.length,
    _degraded: !items.length && !raw,
  }
}

export function toExperimentDetail(raw) {
  if (!raw) return { _degraded: true }
  return {
    id:            raw?.experiment_id ?? raw?.id ?? '',
    name:          raw?.name ?? '',
    status:        raw?.status ?? 'unknown',
    datasetId:     raw?.dataset_id ?? '',
    evaluatorId:   raw?.evaluator_id ?? '',
    targetType:    raw?.target_type ?? '',
    targetId:      raw?.target_id ?? raw?.agent_name ?? '',
    targetVersion: raw?.target_version ?? '',
    totalCases:    raw?.total_cases ?? 0,
    passRate:      raw?.pass_rate ?? null,
    metrics:       raw?.metrics ?? raw?.results ?? {},
    resultCount:   raw?.result_count ?? 0,
    createdBy:     raw?.created_by ?? '',
    createdAt:     raw?.created_at ?? '',
    _degraded:     false,
  }
}
