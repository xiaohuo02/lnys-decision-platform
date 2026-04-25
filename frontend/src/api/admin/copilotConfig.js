/**
 * Copilot Config API — 权限配置 + 反馈看板 + 对话搜索
 */
import { requestAdmin } from '../request'

// ── 技能列表 + 权限矩阵 ──
export function getSkillList() {
  return requestAdmin.get('/copilot/config/skills')
}

// ── 权限覆盖 CRUD ──
export function listOverrides(userId = '') {
  return requestAdmin.get('/copilot/config/overrides', { params: userId ? { user_id: userId } : {} })
}

export function setOverride(userId, skillName, enabled, reason = '') {
  return requestAdmin.put('/copilot/config/overrides', {
    user_id: userId,
    skill_name: skillName,
    enabled,
    reason,
  })
}

export function deleteOverride(userId, skillName) {
  return requestAdmin.delete('/copilot/config/overrides', {
    data: { user_id: userId, skill_name: skillName },
  })
}

// ── 反馈统计 ──
export function getFeedbackStats(days = 30) {
  return requestAdmin.get('/copilot/config/feedback-stats', { params: { days } })
}

// ── 对话搜索 ──
export function searchConversations(q, mode = '', limit = 20) {
  return requestAdmin.get('/copilot/config/search', {
    params: { q, ...(mode ? { mode } : {}), limit },
  })
}
