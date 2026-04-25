/**
 * Business navigation — 按"业务决策循环"分为 4 组：
 *   overview : 经营总览（起点）
 *   insight  : 业务诊断（主动决策）
 *   risk     : 风险与应答（被动响应）
 *   tools    : 输出与工具
 *
 * 浮层（不占导航位）：智能助手 → 右下角 UnifiedCopilotPanel
 */
export default [

  // 首屏入口：对齐 2026 agent-first 趋势，AI 经营分析作为主入口
  { path: '',           redirect: '/analyze' },

  // ── 经营总览 (overview) ───────────────────────────────────────
  { path: 'dashboard',  name: 'Dashboard',    component: () => import('@/views/business/Dashboard.vue'),           meta: { title: '平台总览',     menuGroup: 'business', navGroup: 'overview', icon: 'DataAnalysis',  desc: '今日焦点 · KPI · 需要关注 · 推荐动作', roles: [] } },

  // ── 业务诊断 (insight) ───────────────────────────────────────
  { path: 'analyze',    name: 'Analyze',       component: () => import('@/views/business/AnalyzeProgress.vue'),     meta: { title: '经营分析',     menuGroup: 'business', navGroup: 'insight',  icon: 'MagicStick',    desc: 'AI 经营分析 · SSE 实时进度', roles: [] } },
  { path: 'customer',   name: 'Customer',      component: () => import('@/views/business/CustomerAnalysis.vue'),    meta: { title: '客户分析',     menuGroup: 'business', navGroup: 'insight',  icon: 'User',          desc: 'RFM热力图 · 客群聚类 · CLV排行 · 流失风险', roles: [] } },
  { path: 'forecast',   name: 'Forecast',      component: () => import('@/views/business/SalesForecast.vue'),       meta: { title: '销售预测',     menuGroup: 'business', navGroup: 'insight',  icon: 'TrendCharts',   desc: '多模型集成销售预测', roles: [] } },
  { path: 'inventory',  name: 'Inventory',     component: () => import('@/views/business/InventoryManagement.vue'), meta: { title: '库存优化',     menuGroup: 'business', navGroup: 'insight',  icon: 'Box',           desc: 'ABC-XYZ分类 · 补货策略', roles: [] } },
  { path: 'association',name: 'Association',   component: () => import('@/views/business/AssociationAnalysis.vue'), meta: { title: '关联分析',     menuGroup: 'business', navGroup: 'insight',  icon: 'Share',         desc: '关联规则 · 交叉推荐', roles: [] } },

  // ── 风险与应答 (risk) ────────────────────────────────────────
  { path: 'fraud',             name: 'Fraud',             component: () => import('@/views/business/FraudDetection.vue'),     meta: { title: '欺诈风控',   menuGroup: 'business', navGroup: 'risk', icon: 'Warning',      desc: '实时欺诈检测 · 风险评分', roles: ['platform_admin', 'ops_analyst', 'ml_engineer', 'risk_reviewer', 'super_admin', 'business_admin'] } },
  { path: 'sentiment',         name: 'SentimentOverview', component: () => import('@/views/business/SentimentOverview.vue'), meta: { title: '舆情总览',   menuGroup: 'business', navGroup: 'risk', icon: 'ChatDotRound', desc: 'KPI · 趋势 · 话题分布',         roles: [] } },
  { path: 'sentiment/analyze', name: 'SentimentAnalyze',  component: () => import('@/views/business/SentimentAnalyze.vue'),  meta: { title: '舆情分析',   menuGroup: 'business', navGroup: 'risk', icon: 'ChatDotRound', desc: 'Cascade 推理 · HITL 审核',     roles: [] } },
  { path: 'chat',              name: 'Chat',              component: () => import('@/views/business/OpenClaw.vue'),          meta: { title: '智能客服',   menuGroup: 'business', navGroup: 'risk', icon: 'Service',      desc: 'AI 客服对话 · 意图识别',        roles: [] } },

  // ── 输出与工具 (tools) ───────────────────────────────────────
  { path: 'report',     name: 'Report',        component: () => import('@/views/business/ReportExport.vue'),        meta: { title: '报告导出',     menuGroup: 'business', navGroup: 'tools',    icon: 'Document',      desc: '多维报告生成 · 导出', roles: [] } },

  // ── 隐藏路由（保留可达性，但不在菜单显示） ─────────────────
  { path: 'copilot',        name: 'BizCopilot',    component: () => import('@/views/business/BizCopilot.vue'),      meta: { title: '智能助手', menuGroup: 'business', icon: 'ChatLineRound', desc: 'AI 运营助手 · 业务洞察（已降为右下角浮层）', roles: [], hidden: true } },
  { path: 'report/:run_id', name: 'ReportDetail',  component: () => import('@/views/business/ReportExport.vue'),    meta: { title: '报告详情', menuGroup: 'business', icon: 'Document',      desc: '查看特定 Run 的报告',                       roles: [], hidden: true } },
]

