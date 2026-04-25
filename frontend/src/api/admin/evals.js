import { requestAdmin } from '@/api/request'

export const evalsApi = {
  // ── V1: 基础 CRUD ──
  getDatasets:      (params) => requestAdmin.get('/evals/datasets', { params }),
  getDataset:       (id)     => requestAdmin.get(`/evals/datasets/${id}`),
  createDataset:    (body)   => requestAdmin.post('/evals/datasets', body),
  getEvaluators:    (params) => requestAdmin.get('/evals/evaluators', { params }),
  getEvaluator:     (id)     => requestAdmin.get(`/evals/evaluators/${id}`),
  createEvaluator:  (body)   => requestAdmin.post('/evals/evaluators', body),
  getExperiments:   (params) => requestAdmin.get('/evals/experiments', { params }),
  createExperiment: (body)   => requestAdmin.post('/evals/experiments', body),
  getExperiment:    (id)     => requestAdmin.get(`/evals/experiments/${id}`),
  runExperiment:    (id)     => requestAdmin.post(`/evals/experiments/${id}/run`),
  importSamples:    (body)   => requestAdmin.post('/evals/online-samples/import', body),

  // ── V2: Karpathy Loop（范式一） ──
  startKarpathyLoop: (body)  => requestAdmin.post('/evals/karpathy-loop', body),
  getLoopLog:        (expId) => requestAdmin.get(`/evals/loop-log/${expId}`),

  // ── V2: Prompt Evolution（范式二） ──
  startEvolution:    (body)  => requestAdmin.post('/evals/evolution', body),
  getPromptVersions: (skill) => requestAdmin.get(`/evals/prompt-versions/${skill}`),
  approveVersion:    (id)    => requestAdmin.post(`/evals/prompt-versions/${id}/approve`),
  rollbackVersion:   (id)    => requestAdmin.post(`/evals/prompt-versions/${id}/rollback`),

  // ── V2: Trajectory Memory（范式三） ──
  getTips:           (params) => requestAdmin.get('/evals/tips', { params }),
  getTipsStats:      ()       => requestAdmin.get('/evals/tips/stats'),
  retrieveTips:      (body)   => requestAdmin.post('/evals/tips/retrieve', body),
  toggleTip:         (id)     => requestAdmin.patch(`/evals/tips/${id}/toggle`),
}
