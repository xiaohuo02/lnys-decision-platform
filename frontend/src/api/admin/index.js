export { authApi } from './auth'
export { adminDashboardApi } from './dashboard'
export { tracesApi } from './traces'
export { reviewsApi } from './reviews'
export { promptsApi } from './prompts'
export { policiesApi } from './policies'
export { releasesApi } from './releases'
export { auditApi } from './audit'
export { knowledgeApi } from './knowledge'
export { knowledgeV2Api } from './knowledgeV2'
export { memoryApi } from './memory'
export { opsCopilotApi } from './opsCopilot'
export { evalsApi } from './evals'
export { agentsApi } from './agents'
export { teamApi } from './team'

// ── 向后兼容：合并为单一 adminApi 对象 ─────────────────────────
// 现有 console 页面仍使用 adminApi.xxx() 调用方式
// 新代码请直接 import 具体模块（如 tracesApi, reviewsApi）
import { authApi as _auth } from './auth'
import { adminDashboardApi as _dash } from './dashboard'
import { tracesApi as _traces } from './traces'
import { reviewsApi as _reviews } from './reviews'
import { promptsApi as _prompts } from './prompts'
import { policiesApi as _policies } from './policies'
import { releasesApi as _releases } from './releases'
import { auditApi as _audit } from './audit'
import { knowledgeApi as _knowledge } from './knowledge'
import { knowledgeV2Api as _kbv2 } from './knowledgeV2'
import { memoryApi as _memory } from './memory'
import { opsCopilotApi as _ops } from './opsCopilot'
import { evalsApi as _evals } from './evals'
import { agentsApi as _agents } from './agents'
import { teamApi as _team } from './team'

export const adminApi = {
  // auth
  login:    _auth.login,
  register: _auth.register,
  me:       _auth.me,
  // dashboard
  getDashboardSummary: _dash.getSummary,
  // traces
  getTraces:       _traces.getList,
  getTrace:        _traces.getDetail,
  replayTrace:     _traces.replay,
  getTraceStats:   _traces.getStats,
  traceExportDl:   _traces.exportDownload,
  // reviews
  getReviews:    _reviews.getList,
  getReview:     _reviews.getOne,
  approveReview: _reviews.approve,
  editReview:    _reviews.edit,
  rejectReview:  _reviews.reject,
  // prompts
  getPrompts:    _prompts.getList,
  getPrompt:     _prompts.getOne,
  createPrompt:  _prompts.create,
  releasePrompt: _prompts.release,
  // policies
  getPolicies:    _policies.getList,
  getPolicy:      _policies.getOne,
  createPolicy:   _policies.create,
  activatePolicy: _policies.activate,
  // audit
  getAuditLogs: _audit.getLogs,
  getAuditLog:  _audit.getOne,
  // releases
  getReleases:     _releases.getList,
  getRelease:      _releases.getOne,
  createRelease:   _releases.create,
  rollbackRelease: _releases.rollback,
  // knowledge
  getFAQs:      _knowledge.getFAQs,
  getFAQ:       _knowledge.getFAQ,
  createFAQ:    _knowledge.createFAQ,
  disableFAQ:   _knowledge.disableFAQ,
  // knowledge v2
  getKBLibraries:   _kbv2.getLibraries,
  createKBLibrary:  _kbv2.createLibrary,
  getKBLibrary:     _kbv2.getLibrary,
  deleteKBLibrary:  _kbv2.deleteLibrary,
  getKBDocuments:   _kbv2.getDocuments,
  createKBDocument: _kbv2.createDocument,
  getKBDocument:    _kbv2.getDocument,
  deleteKBDocument: _kbv2.deleteDocument,
  searchKB:         _kbv2.search,
  getKBStats:       _kbv2.getStats,
  // memory
  getMemoryRecords: _memory.getRecords,
  disableMemory:    _memory.disable,
  expireMemory:     _memory.expire,
  feedbackMemory:   _memory.feedback,
  getMemoryFeedback: _memory.getFeedback,
  // ops copilot
  opsCopilotAsk: _ops.ask,
  // agents
  getAgentsOverview: _agents.getOverview,
  // team
  getTeamUsers:  _team.getUsers,
  getTeamUser:   _team.getUser,
  createTeamUser: _team.createUser,
  assignUserRole: _team.assignRole,
  disableTeamUser: _team.disableUser,
  enableTeamUser:  _team.enableUser,
  getTeamRoles:  _team.getRoles,
  // evals
  getDatasets:      _evals.getDatasets,
  getDataset:       _evals.getDataset,
  createDataset:    _evals.createDataset,
  getEvaluators:    _evals.getEvaluators,
  getEvaluator:     _evals.getEvaluator,
  createEvaluator:  _evals.createEvaluator,
  getExperiments:   _evals.getExperiments,
  createExperiment: _evals.createExperiment,
  getExperiment:    _evals.getExperiment,
  runExperiment:    _evals.runExperiment,
  importSamples:    _evals.importSamples,
}
