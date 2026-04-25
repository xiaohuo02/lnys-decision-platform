/**
 * 角色体系定义
 * 每个角色有 key、label、level（数字越小权限越高）、可见菜单组
 *
 * 角色来源:
 *   - DB `roles` 表 7 个真实角色（platform_admin / ops_analyst / ml_engineer
 *     / customer_service_manager / risk_reviewer / auditor / employee）
 *   - Legacy 虚构角色（super_admin / business_admin / service_agent）保留作
 *     兼容 fallback，不作为新分配入口，详见 docs/plan/R-RBAC-FIX.md
 */

export const ROLES = {
  // ── DB 真实角色 ──
  platform_admin:           { key: 'platform_admin',           label: '平台管理员',   level: 0, groups: ['business', 'console'] },
  ops_analyst:              { key: 'ops_analyst',              label: '运营分析师',   level: 2, groups: ['business', 'console'] },
  ml_engineer:              { key: 'ml_engineer',              label: '算法工程师',   level: 2, groups: ['business', 'console'] },
  customer_service_manager: { key: 'customer_service_manager', label: '客服主管',     level: 3, groups: ['business', 'console'] },
  risk_reviewer:            { key: 'risk_reviewer',            label: '风控审核员',   level: 3, groups: ['business', 'console'] },
  auditor:                  { key: 'auditor',                  label: '审计员',       level: 5, groups: ['console'] },
  employee:                 { key: 'employee',                 label: '员工',         level: 99, groups: ['business'] },

  // ── Legacy 虚构角色（保留兼容旧硬编码，不新分配）──
  super_admin:    { key: 'super_admin',    label: '超级管理员',  level: 0, groups: ['business', 'console'] },
  business_admin: { key: 'business_admin', label: '业务管理员',  level: 1, groups: ['business', 'console'] },
  service_agent:  { key: 'service_agent',  label: '客服专员',    level: 4, groups: ['business'] },
}

export const ROLE_KEYS = Object.keys(ROLES)

/**
 * 判断用户角色是否有权访问指定 roles 列表
 * @param {string} userRole - 用户当前角色 key
 * @param {string[]} allowedRoles - 路由或菜单允许的角色列表，空数组表示全部放行
 */
export function hasAccess(userRole, allowedRoles) {
  if (!allowedRoles || allowedRoles.length === 0) return true
  return allowedRoles.includes(userRole)
}

/**
 * 判断用户角色是否可以看到某个菜单组
 * @param {string} userRole
 * @param {string} group - 'business' | 'console'
 */
export function canSeeGroup(userRole, group) {
  const roleDef = ROLES[userRole]
  if (!roleDef) return false
  return roleDef.groups.includes(group)
}
