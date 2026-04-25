/**
 * Traces Adapter
 * 将后端 Traces 接口返回的原始数据转换为前端视图模型
 */

export function toTraceList(raw) {
  const list = Array.isArray(raw) ? raw : (raw?.items ?? [])
  if (!list.length && !raw) return { items: [], _degraded: true }
  return {
    items: list.map((item) => ({
      runId:      item?.run_id ?? item?.runId ?? '',
      workflow:   item?.workflow ?? item?.workflow_name ?? '',
      status:     item?.status ?? 'unknown',
      startedAt:  item?.started_at ?? item?.startedAt ?? '',
      duration:   item?.duration_ms ?? item?.duration ?? null,
      agentCount: item?.agent_count ?? item?.steps?.length ?? 0,
    })),
    total:     raw?.total ?? list.length,
    _degraded: false,
  }
}

export function toTraceDetail(raw) {
  if (!raw) return { _degraded: true }
  const run = raw?.run ?? raw
  return {
    runId:     run?.run_id ?? run?.runId ?? raw?.run_id ?? '',
    workflow:  run?.workflow ?? run?.workflow_name ?? raw?.workflow_name ?? '',
    status:    run?.status ?? raw?.status ?? 'unknown',
    steps:     Array.isArray(raw?.steps) ? raw.steps.map(toTraceStep) : [],
    input:     run?.input ?? raw?.input ?? null,
    output:    run?.output ?? raw?.output ?? null,
    startedAt: run?.started_at ?? run?.startedAt ?? raw?.started_at ?? '',
    endedAt:   run?.ended_at ?? run?.endedAt ?? raw?.ended_at ?? '',
    _degraded: false,
  }
}

function toTraceStep(step) {
  return {
    stepId:   step?.step_id ?? step?.id ?? '',
    agent:    step?.agent ?? step?.agent_name ?? '',
    action:   step?.action ?? '',
    status:   step?.status ?? 'unknown',
    input:    step?.input ?? null,
    output:   step?.output ?? null,
    duration: step?.duration_ms ?? step?.duration ?? null,
  }
}
