/**
 * 治理控制台路由表 V2
 *
 * 4 组 12 项 + 向后兼容 redirect
 * navGroup: command | observability | ai-engineering | security
 */
export default [
  { path: '', redirect: '/console/dashboard' },

  // ── 指挥中心 (command) ───────────────────────────────────────
  { path: 'dashboard',   name: 'ConsoleDashboard',    component: () => import('@/views/console/ConsoleDashboard.vue'),    meta: { title: '治理总览',   menuGroup: 'console', navGroup: 'command',       icon: 'Monitor',       desc: '系统运行状态 · KPI · 待办', roles: [] } },
  { path: 'activity',    name: 'ConsoleActivityFeed',  component: () => import('@/views/console/ConsoleActivityFeed.vue'), meta: { title: '活动流',     menuGroup: 'console', navGroup: 'command',       icon: 'List',          desc: '实时事件流 · 待办 · 告警', roles: [] } },
  { path: 'ops-copilot', name: 'ConsoleOpsCopilot',    component: () => import('@/views/console/ConsoleOpsCopilot.vue'),  meta: { title: '运维助手',   menuGroup: 'console', navGroup: 'command',       icon: 'ChatLineRound', desc: 'AI 运维助手', roles: ['platform_admin', 'ops_analyst', 'ml_engineer', 'super_admin', 'business_admin'] } },

  // ── 可观测性 (observability) ──────────────────────────────────
  { path: 'traces',      name: 'ConsoleTraceExplorer', component: () => import('@/views/console/ConsoleTraces.vue'),      meta: { title: '智能体日志', menuGroup: 'console', navGroup: 'observability', icon: 'List',          desc: '查看所有AI使用记录', roles: [] } },
  { path: 'agent-hub',   name: 'ConsoleAgentHub',      component: () => import('@/views/console/ConsoleAgentHub.vue'),    meta: { title: '智能体中枢', menuGroup: 'console', navGroup: 'observability', icon: 'Cpu',           desc: '智能体 · 工作流 · 状态', roles: ['platform_admin', 'ops_analyst', 'ml_engineer', 'super_admin', 'business_admin'] } },
  { path: 'health',      name: 'ConsoleHealth',        component: () => import('@/views/console/ConsoleHealth.vue'),      meta: { title: '系统健康',   menuGroup: 'console', navGroup: 'observability', icon: 'Odometer',      desc: '系统健康检查', roles: ['platform_admin', 'ops_analyst', 'ml_engineer', 'super_admin'] } },

  // ── AI 工程 (ai-engineering) ──────────────────────────────────
  { path: 'prompts',     name: 'ConsolePromptStudio',  component: () => import('@/views/console/ConsolePrompts.vue'),     meta: { title: '提示词工坊', menuGroup: 'console', navGroup: 'ai-engineering', icon: 'EditPen',       desc: '提示词管理 · 试验场', roles: ['platform_admin', 'ops_analyst', 'ml_engineer', 'auditor', 'super_admin', 'business_admin'] } },
  { path: 'knowledge',   name: 'ConsoleKnowledgeMemory', component: () => import('@/views/console/ConsoleKnowledgeMemory.vue'), meta: { title: '知识与记忆', menuGroup: 'console', navGroup: 'ai-engineering', icon: 'Collection', desc: '知识库 · 记忆治理', roles: ['platform_admin', 'ops_analyst', 'ml_engineer', 'customer_service_manager', 'auditor', 'super_admin', 'business_admin', 'service_agent'] } },
  { path: 'knowledge-v2', name: 'ConsoleKnowledgeV2', component: () => import('@/views/console/ConsoleKnowledgeV2.vue'), meta: { title: '知识库中台', menuGroup: 'console', navGroup: 'ai-engineering', icon: 'FolderOpened', desc: '多知识库管理 · 文档处理 · 统一检索', roles: ['platform_admin', 'ops_analyst', 'ml_engineer', 'super_admin', 'business_admin'] } },
  { path: 'evals',       name: 'ConsoleEvalCenter',    component: () => import('@/views/console/ConsoleEvals.vue'),       meta: { title: '评测中心',   menuGroup: 'console', navGroup: 'ai-engineering', icon: 'DataAnalysis',  desc: '评测数据集 · 实验', roles: ['platform_admin', 'ops_analyst', 'ml_engineer', 'auditor', 'super_admin', 'business_admin'] } },

  // ── 安全与管理 (security) ─────────────────────────────────────
  { path: 'security',    name: 'ConsoleSecurity',      component: () => import('@/views/console/ConsoleSecurity.vue'),    meta: { title: '安全合规',   menuGroup: 'console', navGroup: 'security',      icon: 'Lock',          desc: '安全策略 · 审计日志', roles: ['platform_admin', 'auditor', 'super_admin', 'business_admin'] } },
  { path: 'releases',    name: 'ConsoleReleases',      component: () => import('@/views/console/ConsoleReleases.vue'),    meta: { title: '发布中心',   menuGroup: 'console', navGroup: 'security',      icon: 'Upload',        desc: '发布管理 · 回滚', roles: ['platform_admin', 'ml_engineer', 'auditor', 'super_admin', 'business_admin'] } },
  { path: 'settings',    name: 'ConsoleTeamSettings',  component: () => import('@/views/console/ConsoleTeamSettings.vue'), meta: { title: '团队与设置', menuGroup: 'console', navGroup: 'security',      icon: 'Setting',       desc: '团队权限 · 系统设置', roles: ['platform_admin', 'super_admin'] } },

  // ── TraceDetail (内嵌式，非侧栏导航) ──────────────────────────
  { path: 'traces/:runId', name: 'ConsoleTraceDetail', component: () => import('@/views/console/ConsoleTraceDetail.vue'), meta: { title: '追踪详情', menuGroup: 'console', hidden: true, roles: [] } },

  // ── 向后兼容 redirect ────────────────────────────────────────
  { path: 'agents',         redirect: '/console/agent-hub' },
  { path: 'workflows',      redirect: '/console/agent-hub' },
  { path: 'reviews',        redirect: to => ({ path: '/fraud', query: { tab: 'reviews' } }) },
  { path: 'audit',          redirect: to => ({ path: '/console/security', query: { tab: 'audit' } }) },
  { path: 'memory',         redirect: to => ({ path: '/console/knowledge', query: { tab: 'memory' } }) },
  { path: 'team',           redirect: to => ({ path: '/console/settings', query: { tab: 'team' } }) },
  { path: 'copilot-config', redirect: to => ({ path: '/console/settings', query: { tab: 'copilot' } }) },
  { path: 'policies',       redirect: '/console/security' },
]
