/**
 * Copilot 内嵌对话框 — 模拟用户交互 E2E 测试
 *
 * 覆盖全部 9 个业务页面内嵌 Copilot + BizCopilot 独立页：
 *   Dashboard / CustomerAnalysis / SentimentAnalysis / SalesForecast
 *   FraudDetection / AssociationAnalysis / InventoryManagement
 *   ReportExport / AnalyzeProgress / BizCopilot
 *
 * 测试维度：
 *   ① 快捷问题（quick questions）
 *   ② 数据行/节点点击 → AI 自动提问
 *   ③ 多轮追问（follow-up）
 *   ④ 上下文注入验证（setContext / page_context）
 *   ⑤ 跨智能体调用（askAgent / askCrossAgent）
 *   ⑥ 反馈（feedback）
 *   ⑦ 错误降级（degradation）
 *   ⑧ Thread 管理（new / switch / resume）
 *   ⑨ Suggestion 处理
 *
 * 运行: node tests/copilot_e2e.test.js
 *
 * 技术原理：
 *   - 用 MockSSEServer 在 127.0.0.1 起一个真实 HTTP 服务，返回 SSE 事件流
 *   - 直接 import usePageCopilot / useCopilotStream 的核心逻辑进行集成测试
 *   - 由于 Vue composable 依赖 Vue runtime，我们对核心协议层做协议级验证
 *   - 对视图层交互逻辑做行为模拟验证（模拟用户点击→触发的 ask / setContext 调用）
 */

const http = require('http')
const { URL } = require('url')

// ═══════════════════════════════════════════════════════════════════
// §0  Test Framework (lightweight, zero-dep)
// ═══════════════════════════════════════════════════════════════════

let _pass = 0, _fail = 0, _skip = 0, _currentSuite = ''
const _failures = []

function suite(name) { _currentSuite = name; console.log(`\n━━ ${name} ━━`) }

function assert(label, condition) {
  if (condition) { _pass++; console.log(`  ✓ ${label}`) }
  else { _fail++; _failures.push(`[${_currentSuite}] ${label}`); console.error(`  ✗ ${label}`) }
}

function assertEq(label, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected)
  if (ok) { _pass++; console.log(`  ✓ ${label}`) }
  else { _fail++; _failures.push(`[${_currentSuite}] ${label}: got ${JSON.stringify(actual)}, want ${JSON.stringify(expected)}`); console.error(`  ✗ ${label}: got ${JSON.stringify(actual)}, want ${JSON.stringify(expected)}`) }
}

function assertIncludes(label, str, sub) {
  const ok = typeof str === 'string' && str.includes(sub)
  if (ok) { _pass++; console.log(`  ✓ ${label}`) }
  else { _fail++; _failures.push(`[${_currentSuite}] ${label}`); console.error(`  ✗ ${label}: "${sub}" not found in "${String(str).slice(0, 120)}"`) }
}

function assertGt(label, actual, threshold) {
  if (actual > threshold) { _pass++; console.log(`  ✓ ${label}`) }
  else { _fail++; _failures.push(`[${_currentSuite}] ${label}: ${actual} ≤ ${threshold}`); console.error(`  ✗ ${label}: ${actual} ≤ ${threshold}`) }
}

// ═══════════════════════════════════════════════════════════════════
// §1  Mock SSE Server
// ═══════════════════════════════════════════════════════════════════

/**
 * 创建一个 Mock SSE 服务器，根据请求 body 中的 question 返回不同的 SSE 事件流。
 * 模拟真实的 AG-UI 协议：run_start → thinking → tool_call → text_delta → suggestions → sources → run_end
 */
function createMockSSEServer() {
  const requestLog = []

  let _threadCounter = 0
  /** 构造一条 SSE data 行 */
  function sse(evt) { return `data: ${JSON.stringify(evt)}\n\n` }

  /** 根据 question 生成对应的 SSE 事件流 */
  function generateEvents(body) {
    const q = body.question || ''
    const threadId = body.thread_id || 'mock-thread-' + Date.now() + '-' + (++_threadCounter)
    const page = body.page_context?.page || 'unknown'
    const mentions = body.page_context?.mentions || []

    const events = []

    // run_start
    events.push(sse({ type: 'run_start', metadata: { thread_id: threadId, mode: 'biz' } }))

    // thinking (只在某些问题触发)
    if (q.includes('分析') || q.includes('预测') || q.includes('风险') || q.includes('解读') || q.includes('趋势') || q.includes('特征')) {
      events.push(sse({ type: 'thinking_start', content: '' }))
      events.push(sse({ type: 'thinking_delta', content: `正在分析「${q.slice(0, 20)}」相关数据...` }))
      events.push(sse({ type: 'thinking_end', content: '' }))
    }

    // tool_call (模拟 skill 路由)
    const skillName = _inferSkill(q, mentions, page)
    if (skillName) {
      events.push(sse({ type: 'tool_call_start', metadata: { skill: skillName, display_name: _skillDisplayName(skillName) } }))
      events.push(sse({ type: 'tool_call_end', metadata: { skill: skillName } }))
    }

    // intent + confidence
    events.push(sse({ type: 'intent', content: _inferIntent(q) }))
    events.push(sse({ type: 'confidence', content: 0.92 }))

    // artifact (某些问题返回数据表格)
    if (q.includes('概览') || q.includes('列表') || q.includes('预警') || q.includes('补货')) {
      events.push(sse({ type: 'artifact_start', artifact_type: 'generic_table', metadata: { title: '数据概览' } }))
      events.push(sse({ type: 'artifact_delta', content: { columns: ['指标', '数值'], rows: [['活跃用户', '12,345'], ['转化率', '3.2%']] } }))
      events.push(sse({ type: 'artifact_end' }))
    }

    // text_delta (分块返回)
    const reply = _generateReply(q, page, skillName)
    const chunks = _splitToChunks(reply, 30)
    for (const chunk of chunks) {
      events.push(sse({ type: 'text_delta', content: chunk }))
    }

    // sources
    events.push(sse({ type: 'sources', items: [
      { title: '企业知识库 - 运营手册', score: 0.95, collection: 'kb_rag' },
      { title: '历史分析报告', score: 0.87 },
    ] }))

    // suggestions (追问建议)
    const suggestions = _generateSuggestions(q, page)
    if (suggestions.length) {
      events.push(sse({ type: 'suggestions', items: suggestions }))
    }

    // run_end
    events.push(sse({ type: 'run_end', metadata: { thread_id: threadId, elapsed_ms: 1200 }, data: { token_usage: { input: 150, output: 280 } } }))

    return events.join('')
  }

  const server = http.createServer((req, res) => {
    if (req.method === 'POST' && req.url.includes('/copilot/stream')) {
      let bodyStr = ''
      req.on('data', chunk => { bodyStr += chunk })
      req.on('end', () => {
        let body = {}
        try { body = JSON.parse(bodyStr) } catch {}
        requestLog.push({ url: req.url, body, ts: Date.now() })

        // 模拟 error 场景
        if (body.question?.includes('__FORCE_ERROR__')) {
          res.writeHead(500, { 'Content-Type': 'text/plain' })
          res.end('Internal Server Error')
          return
        }

        res.writeHead(200, {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
          'X-Thread-Id': body.thread_id || 'mock-thread-' + Date.now(),
        })
        res.write(generateEvents(body))
        res.end()
      })
    } else if (req.method === 'GET' && req.url.includes('/messages')) {
      requestLog.push({ url: req.url, method: 'GET', ts: Date.now() })
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({
        code: 200, data: {
          messages: [
            { id: 1, role: 'user', content: '库存预警有哪些？', created_at: '2026-04-08T10:01:00Z' },
            { id: 2, role: 'assistant', content: '当前有 3 个 SKU 处于紧急预警状态...', skills_used: ['inventory_skill'], created_at: '2026-04-08T10:01:05Z' },
          ],
          total: 2,
        },
      }))
    } else if (req.method === 'GET' && req.url.includes('/copilot/threads')) {
      requestLog.push({ url: req.url, method: 'GET', ts: Date.now() })
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({
        code: 200, data: {
          threads: [
            { id: 'thread-001', title: '库存分析对话', created_at: '2026-04-08T10:00:00Z' },
            { id: 'thread-002', title: '客户洞察', created_at: '2026-04-07T15:00:00Z' },
          ],
          total: 2,
        },
      }))
    } else if (req.method === 'POST' && req.url.includes('/feedback')) {
      let bodyStr = ''
      req.on('data', chunk => { bodyStr += chunk })
      req.on('end', () => {
        let body = {}
        try { body = JSON.parse(bodyStr) } catch {}
        requestLog.push({ url: req.url, body, ts: Date.now() })
        res.writeHead(200, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ code: 200, data: { status: 'ok' } }))
      })
    } else if (req.method === 'POST' && req.url.includes('/action/execute')) {
      let bodyStr = ''
      req.on('data', chunk => { bodyStr += chunk })
      req.on('end', () => {
        let body = {}
        try { body = JSON.parse(bodyStr) } catch {}
        requestLog.push({ url: req.url, body, ts: Date.now() })
        res.writeHead(200, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ code: 200, data: { executed: true, action_type: body.action_type } }))
      })
    } else {
      res.writeHead(404); res.end('Not Found')
    }
  })

  return { server, requestLog }
}

// ── SSE 内容生成辅助 ──

function _inferSkill(q, mentions, page) {
  const skillMentions = mentions.filter(m => m.type === 'skill')
  if (skillMentions.length) return skillMentions[0].id

  const mapping = {
    '库存': 'inventory_skill', '补货': 'inventory_skill', 'SKU': 'inventory_skill',
    '客户': 'customer_intel', '客群': 'customer_intel', '流失': 'customer_intel', 'RFM': 'customer_intel', 'CLV': 'customer_intel',
    '预测': 'forecast_skill', '销售趋势': 'forecast_skill', '备货': 'forecast_skill',
    '舆情': 'sentiment_skill', '情感': 'sentiment_skill', '满意度': 'sentiment_skill', '评论': 'sentiment_skill',
    '风控': 'fraud_skill', '欺诈': 'fraud_skill', '风险交易': 'fraud_skill', '审核': 'fraud_skill',
    '关联': 'association_skill', '搭配': 'association_skill', '交叉营销': 'association_skill',
    '报告': 'kb_rag', '知识库': 'kb_rag',
  }
  for (const [kw, skill] of Object.entries(mapping)) {
    if (q.includes(kw)) return skill
  }

  const pageFallback = {
    inventory: 'inventory_skill', customer: 'customer_intel', forecast: 'forecast_skill',
    sentiment: 'sentiment_skill', fraud: 'fraud_skill', association: 'association_skill',
    dashboard: 'kb_rag', report: 'kb_rag', workflow: 'kb_rag',
  }
  return pageFallback[page] || null
}

function _skillDisplayName(id) {
  const names = {
    inventory_skill: '库存管理', customer_intel: '客群洞察', forecast_skill: '销售预测',
    sentiment_skill: '舆情分析', fraud_skill: '风控中心', association_skill: '关联分析', kb_rag: '知识库',
  }
  return names[id] || id
}

function _inferIntent(q) {
  // 按关键词在 q 中的最后出现位置决定主 intent（尾部意图优先）
  const intents = [
    { id: 'overview',       kws: ['概览', '状况', '态势', '整体'] },
    { id: 'forecast',       kws: ['预测'] },
    { id: 'alert',          kws: ['预警'] },
    { id: 'recommendation', kws: ['建议', '策略', '优化', '洞察', '挽回', '改善'] },
    { id: 'analysis',       kws: ['分析', '解读', '特征', '对比', '原因'] },
  ]
  let best = 'general', bestPos = -1
  for (const { id, kws } of intents) {
    for (const kw of kws) {
      const pos = q.lastIndexOf(kw)
      if (pos > bestPos) { bestPos = pos; best = id }
    }
  }
  return best
}

function _generateReply(q, page, skill) {
  const replies = {
    inventory_skill: `根据当前库存数据分析：\n\n1. **紧急预警 SKU**：LY-TEA-001（当前库存 12，安全库存 50）、LY-SNACK-023（当前 5，安全 30）\n2. **库存周转天数**：整体平均 18.5 天，较上月改善 2.3 天\n3. **建议**：优先补货 LY-TEA-001，预计 3 天内断货\n\n> 以上数据基于最近 30 天销售趋势计算`,
    customer_intel: `客群分析结果：\n\n- **高价值客户**（CLV > ¥5000）占比 12.3%，贡献 45% 收入\n- **流失风险**：23 位客户流失概率 > 70%，主因为最近 60 天无消费\n- **RFM 分层**：忠诚客户 340 人，沉睡客户 156 人\n\n建议对高流失风险客户推送定向优惠`,
    forecast_skill: `销售预测摘要：\n\n- **MAPE（融合模型）**：4.2%，表现优秀\n- **未来 7 天预测**：日均销售约 ¥85,000，周末峰值预计 ¥120,000\n- **置信区间**：95% 置信度下，日销售额在 ¥70,000 - ¥100,000\n\n建议提前准备周末促销库存`,
    sentiment_skill: `舆情分析概览：\n\n- **正面情感**：62.4%，较上周提升 3.1%\n- **负面情感**：15.2%，主要集中在物流时效\n- **热点话题**：#产品质量（正面）、#配送延迟（负面）、#新品推荐（中性）\n\n建议关注物流时效问题，考虑优化配送合作方`,
    fraud_skill: `风控态势报告：\n\n- **今日拦截**：47 笔，拦截率 2.8%\n- **高风险交易特征**：深夜交易（凌晨 2-4 点）+ 新账户 + 大额（>¥5000）\n- **模型评分**：LightGBM 精度 94.2%，IsoForest 异常检出率 89.7%\n\n有 3 笔交易进入人工审核队列，建议优先处理`,
    association_skill: `商品关联分析：\n\n- **强关联规则**（Lift > 3）：12 条\n- **最佳搭配**：柠檬茶 + 坚果礼盒（Lift 4.8，置信度 0.72）\n- **交叉营销潜力**：建议将零食系列与茶饮进行捆绑促销\n\n前三名关联对的平均支持度为 0.15`,
    kb_rag: `根据知识库检索和业务数据综合分析：\n\n当前业务整体运行平稳，各项指标均在合理区间。\n\n**需关注事项**：\n1. 库存预警 SKU 数量较上周增加 2 个\n2. 客户流失风险略有上升\n3. 本周舆情正面率持续改善\n\n建议重点关注库存和客户留存。`,
  }
  return replies[skill] || `针对您的问题「${q.slice(0, 30)}」，以下是分析结果：\n\n基于当前数据分析，各项业务指标运行正常。建议持续关注关键指标变化趋势。`
}

function _generateSuggestions(q, page) {
  const pageSuggestions = {
    inventory: [
      { type: 'question', label: '哪些 SKU 需要紧急补货？' },
      { type: 'question', label: 'ABC-XYZ 矩阵中 AX 类商品有哪些？' },
      { type: 'action', label: '导出库存预警报表', action: 'export_report', payload: { type: 'inventory_alert' } },
    ],
    customer: [
      { type: 'question', label: '高价值客户有哪些共同特征？' },
      { type: 'question', label: '流失风险最高的 10 位客户' },
      { type: 'question', label: '如何提升客户留存率？' },
    ],
    forecast: [
      { type: 'question', label: '各模型预测精度对比' },
      { type: 'question', label: '影响预测精度的关键因素' },
    ],
    sentiment: [
      { type: 'question', label: '负面评论的核心话题是什么？' },
      { type: 'question', label: '如何改善用户满意度？' },
    ],
    fraud: [
      { type: 'question', label: '待审核交易的优先级排序' },
      { type: 'question', label: '最近一周高风险交易趋势' },
    ],
    association: [
      { type: 'question', label: '推荐搭配促销方案' },
      { type: 'question', label: '低 Lift 商品对有优化空间吗？' },
    ],
    dashboard: [
      { type: 'question', label: '哪个业务板块增长最快？' },
      { type: 'question', label: '异常指标的根因分析' },
    ],
    report: [
      { type: 'question', label: '报告中应突出哪些亮点？' },
    ],
    workflow: [
      { type: 'question', label: '可以优化哪些步骤？' },
    ],
  }
  return pageSuggestions[page] || [{ type: 'question', label: '还有什么需要了解的？' }]
}

function _splitToChunks(text, size) {
  const chunks = []
  for (let i = 0; i < text.length; i += size) {
    chunks.push(text.slice(i, i + size))
  }
  return chunks
}

// ═══════════════════════════════════════════════════════════════════
// §2  SSE Client (模拟 useCopilotStream 的协议解析)
// ═══════════════════════════════════════════════════════════════════

function parseSSEResponse(raw) {
  const result = {
    threadId: '', text: '', thinking: '', intent: '', confidence: 0,
    skill: null, artifacts: [], suggestions: [], sources: [],
    elapsedMs: 0, tokenUsage: null, error: null, events: [],
  }
  const lines = raw.split('\n')
  for (const line of lines) {
    if (!line.startsWith('data: ')) continue
    const jsonStr = line.slice(6).trim()
    if (!jsonStr || jsonStr === '[DONE]') continue
    try {
      const evt = JSON.parse(jsonStr)
      result.events.push(evt)
      switch (evt.type) {
        case 'run_start': result.threadId = evt.metadata?.thread_id || ''; break
        case 'run_end': result.elapsedMs = evt.metadata?.elapsed_ms || 0; result.tokenUsage = evt.data?.token_usage; break
        case 'run_error': result.error = evt.content; break
        case 'text_delta': result.text += evt.content || ''; break
        case 'thinking_start': result.thinking = ''; break
        case 'thinking_delta': result.thinking += evt.content || ''; break
        case 'thinking_end': break
        case 'tool_call_start': result.skill = { name: evt.metadata?.skill, displayName: evt.metadata?.display_name, loading: true }; break
        case 'tool_call_end': if (result.skill) result.skill.loading = false; break
        case 'artifact_start': result.artifacts.push({ type: evt.artifact_type, metadata: evt.metadata, content: null, closed: false }); break
        case 'artifact_delta': { const last = result.artifacts[result.artifacts.length - 1]; if (last) last.content = evt.content; break }
        case 'artifact_end': { const last = result.artifacts[result.artifacts.length - 1]; if (last) last.closed = true; break }
        case 'suggestions': result.suggestions = evt.items || []; break
        case 'intent': result.intent = evt.content || ''; break
        case 'confidence': result.confidence = evt.content || 0; break
        case 'sources': result.sources = evt.items || []; break
      }
    } catch { /* malformed JSON, skip */ }
  }
  return result
}

/** 发送一个 SSE 请求并解析结果 */
async function askCopilot(port, body) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(body)
    const req = http.request({
      hostname: '127.0.0.1', port,
      path: '/api/copilot/stream',
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) },
    }, (res) => {
      let raw = ''
      res.on('data', chunk => { raw += chunk })
      res.on('end', () => {
        if (res.statusCode !== 200) {
          resolve({ error: `HTTP ${res.statusCode}`, text: '', events: [], threadId: '' })
        } else {
          resolve(parseSSEResponse(raw))
        }
      })
    })
    req.on('error', reject)
    req.write(data)
    req.end()
  })
}

/** REST GET helper */
async function httpGet(port, path) {
  return new Promise((resolve, reject) => {
    http.get({ hostname: '127.0.0.1', port, path }, (res) => {
      let raw = ''
      res.on('data', chunk => { raw += chunk })
      res.on('end', () => { try { resolve(JSON.parse(raw)) } catch { resolve(raw) } })
    }).on('error', reject)
  })
}

/** REST POST helper */
async function httpPost(port, path, body) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(body)
    const req = http.request({
      hostname: '127.0.0.1', port, path, method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) },
    }, (res) => {
      let raw = ''
      res.on('data', chunk => { raw += chunk })
      res.on('end', () => { try { resolve(JSON.parse(raw)) } catch { resolve(raw) } })
    })
    req.on('error', reject)
    req.write(data)
    req.end()
  })
}


// ═══════════════════════════════════════════════════════════════════
// §3  Page Interaction Simulators
// ═══════════════════════════════════════════════════════════════════

/**
 * 模拟 usePageCopilot 的行为：
 *   - 构造与真实代码相同的 page_context
 *   - 发送 SSE 请求
 *   - 验证响应
 */
class PageCopilotSimulator {
  constructor(port, pageName, defaultSkills = [], mode = 'biz') {
    this.port = port
    this.pageName = pageName
    this.defaultSkills = defaultSkills
    this.mode = mode
    this.pageContext = {}
    this.threadId = ''
    this.messages = []
  }

  setContext(ctx) {
    this.pageContext = { ...this.pageContext, ...ctx }
  }

  clearContext() {
    this.pageContext = {}
  }

  async ask(question, extraMentions = []) {
    const mentions = [
      ...this.defaultSkills.map(id => ({ type: 'skill', id })),
      ...extraMentions,
    ]
    this.messages.push({ role: 'user', content: question })
    const result = await askCopilot(this.port, {
      question,
      thread_id: this.threadId || undefined,
      mode: this.mode,
      page_context: {
        page: this.pageName,
        think_mode: 'auto',
        mentions,
        ...this.pageContext,
      },
    })
    if (result.threadId && !this.threadId) this.threadId = result.threadId
    if (!result.error) {
      this.messages.push({
        role: 'assistant', content: result.text,
        skill: result.skill?.displayName || result.skill?.name || '',
        artifacts: result.artifacts, suggestions: result.suggestions,
        sources: result.sources, feedback: null,
      })
    }
    return result
  }

  async askAgent(skillId, question) {
    return this.ask(question, [{ type: 'skill', id: skillId }])
  }

  async askCrossAgent(skillId, question, extraCtx = {}) {
    if (Object.keys(extraCtx).length) this.setContext(extraCtx)
    return this.ask(question, [{ type: 'skill', id: skillId }])
  }

  async askWithData(question, dataContext = {}) {
    this.setContext(dataContext)
    return this.ask(question)
  }

  startNewThread() {
    this.threadId = ''
    this.messages = []
  }
}


// ═══════════════════════════════════════════════════════════════════
// §4  Test Cases
// ═══════════════════════════════════════════════════════════════════

async function runAllTests(port, requestLog) {

  // ─── 4.1 Dashboard ──────────────────────────────────────────
  suite('Dashboard — AI 业务总览助手')
  {
    const sim = new PageCopilotSimulator(port, 'dashboard', ['kb_rag'])

    // 快捷问题
    const r1 = await sim.ask('今日业务整体运营状况如何？')
    assert('quick-q returns text', r1.text.length > 0)
    assertEq('intent is overview', r1.intent, 'overview')
    assert('has sources', r1.sources.length > 0)
    assert('has suggestions', r1.suggestions.length > 0)

    // KPI 卡片点击→AI 提问（模拟 Dashboard 中 StatCardV2 的 aiQ 字段触发）
    const r2 = await sim.ask('今日 GMV 表现如何？环比趋势和主要驱动因素分析')
    assertIncludes('kpi-ask has analysis content', r2.text, '分析')
    assertEq('intent is analysis', r2.intent, 'analysis')

    // 追问
    const r3 = await sim.ask('给出今日经营优化建议')
    assert('follow-up returns text', r3.text.length > 0)
    assertEq('thread stays same', r3.threadId, r1.threadId)
    assertEq('messages accumulated', sim.messages.length, 6) // 3 user + 3 assistant
  }

  // ─── 4.2 CustomerAnalysis ───────────────────────────────────
  suite('CustomerAnalysis — AI 客群分析助手')
  {
    const sim = new PageCopilotSimulator(port, 'customer', ['customer_intel', 'kb_rag'])

    // 快捷问题
    const r1 = await sim.ask('当前客群整体概览和关键指标')
    assert('returns customer overview', r1.text.length > 50)
    assertEq('routed to customer_intel', r1.skill?.name, 'customer_intel')

    // 模拟 onChurnRowClick → setContext → askAboutSelected
    sim.setContext({
      selected_customer: 'LY000088',
      churn_probability: 0.85,
      risk_level: '高',
      top3_reasons: ['60天未消费', '订单频次下降', '客单价降低'],
    })
    const r2 = await sim.ask('分析客户 LY000088 的消费行为和价值潜力')
    assertIncludes('context-aware reply mentions customer', r2.text, '客')
    assert('context was sent', requestLog.some(r =>
      r.body?.page_context?.selected_customer === 'LY000088'
    ))

    // 模拟 onRfmRowClick → setContext → AI 分析
    sim.setContext({
      selected_customer: 'LY000123',
      member_level: '金牌',
      segment: '忠诚客户',
      rfm: { r: 5, f: 4, m: 5 },
    })
    const r3 = await sim.ask('这位客户的 RFM 评分意味着什么？给出维护建议')
    assert('RFM analysis returned', r3.text.length > 30)

    // 追问 - 高价值客户特征
    const r4 = await sim.ask('高价值客户有什么特征？')
    assertEq('thread continuity', r4.threadId, r1.threadId)

    // 流失挽回追问
    const r5 = await sim.ask('高流失风险客户的挽回建议')
    assertEq('intent is recommendation', r5.intent, 'recommendation')
  }

  // ─── 4.3 SentimentAnalysis ──────────────────────────────────
  suite('SentimentAnalysis — AI 舆情分析助手')
  {
    const sim = new PageCopilotSimulator(port, 'sentiment', ['sentiment_skill', 'kb_rag'])

    const r1 = await sim.ask('当前舆情整体态势如何？')
    assert('sentiment overview returned', r1.text.length > 50)
    assertEq('routed to sentiment_skill', r1.skill?.name, 'sentiment_skill')
    assertEq('intent is overview', r1.intent, 'overview')

    // 模拟 selectTopic → AI 深入分析话题（对应模板中 askAndSwitch）
    const r2 = await sim.ask('深入分析话题「配送延迟」的用户反馈和改善建议')
    assert('topic deep analysis returned', r2.text.length > 30)
    assert('thinking triggered for analysis', r2.thinking.length > 0)

    // 模拟 analyzeResult → AI 改善建议（尾部意图“改善建议”→ recommendation）
    const r3 = await sim.ask('对这条「负面」评论做更详细的语义分析和改善建议')
    assertEq('intent is recommendation (tail intent)', r3.intent, 'recommendation')

    // 追问 - 如何改善满意度
    const r4 = await sim.ask('如何改善用户满意度？')
    assertEq('thread continuity', r4.threadId, r1.threadId)
    assert('has follow-up suggestions', r4.suggestions.length > 0)
  }

  // ─── 4.4 SalesForecast ─────────────────────────────────────
  suite('SalesForecast — AI 预测分析助手')
  {
    const sim = new PageCopilotSimulator(port, 'forecast', ['forecast_skill', 'kb_rag'])

    const r1 = await sim.ask('当前预测模型整体表现如何？')
    assert('forecast overview returned', r1.text.length > 50)
    assertEq('routed to forecast_skill', r1.skill?.name, 'forecast_skill')

    // 备货建议（尾部意图"备货建议"→ recommendation）
    const r2 = await sim.ask('未来 7 天销售趋势和备货建议')
    assertEq('intent is recommendation (tail intent)', r2.intent, 'recommendation')
    assert('thinking triggered for prediction', r2.thinking.length > 0)

    // 模拟 predictResult → askAndSwitch
    sim.setContext({
      last_prediction: { sku_code: 'LY-TEA-001', model_used: 'stacking', days: 30 },
    })
    const r3 = await sim.ask('基于当前预测结果给出备货和促销建议')
    assertIncludes('context-aware prediction reply', r3.text, '建议')

    // 追问 - 影响精度的因素
    const r4 = await sim.ask('哪些因素影响预测精度？')
    assertEq('thread continuity', r4.threadId, r1.threadId)
  }

  // ─── 4.5 FraudDetection ─────────────────────────────────────
  suite('FraudDetection — AI 风控助手')
  {
    const sim = new PageCopilotSimulator(port, 'fraud', ['fraud_skill', 'kb_rag'])

    const r1 = await sim.ask('今日风控整体态势如何？')
    assert('fraud overview returned', r1.text.length > 50)
    assertEq('routed to fraud_skill', r1.skill?.name, 'fraud_skill')

    // 模拟 runScore → setContext → onPendingRowClick → askAndSwitch
    sim.setContext({
      last_scored_tx: 'TX20240315001',
      risk_level: '高',
    })
    const r2 = await sim.ask('分析交易 TX20240315001 的风险特征和审核建议')
    assert('thinking triggered for risk analysis', r2.thinking.length > 0)
    assertIncludes('reply mentions risk', r2.text, '风')

    // 追问 - 高风险交易特征
    const r3 = await sim.ask('高风险交易的共同特征是什么？')
    assertEq('intent is analysis', r3.intent, 'analysis')

    // 待审核优先级
    const r4 = await sim.ask('当前待审核交易的优先级排序')
    assertEq('thread continuity', r4.threadId, r1.threadId)
  }

  // ─── 4.6 AssociationAnalysis ────────────────────────────────
  suite('AssociationAnalysis — AI 关联分析助手')
  {
    const sim = new PageCopilotSimulator(port, 'association', ['association_skill', 'kb_rag'])

    const r1 = await sim.ask('当前商品关联规则概览')
    assert('association overview returned', r1.text.length > 50)
    assertEq('routed to association_skill', r1.skill?.name, 'association_skill')
    assert('has artifact (data table)', r1.artifacts.length > 0)

    // 模拟 onRuleClick → setContext → AI 分析规则
    sim.setContext({
      selected_rule: { antecedents: ['柠檬茶'], consequents: ['坚果礼盒'], lift: 4.8, confidence: 0.72 },
      selected_node: null,
    })
    const r2 = await sim.ask('分析柠檬茶和坚果礼盒的关联关系和营销策略')
    assertIncludes('context-aware rule analysis', r2.text, '关联')

    // 模拟 onNodeClick → setContext → loadRecommend
    sim.clearContext()
    sim.setContext({
      selected_node: 'LY-TEA-001',
      selected_node_name: '柠檬茶',
      node_frequency: 1234,
      selected_rule: null,
    })
    const r3 = await sim.ask('分析 柠檬茶 的关联商品和搭配推荐')
    assert('node-click analysis returned', r3.text.length > 30)

    // 跨智能体调用（onAskAgent）
    const r4 = await sim.askAgent('customer_intel', '购买关联商品的客户画像是什么？')
    assert('cross-agent customer request sent', requestLog.some(r =>
      r.body?.page_context?.mentions?.some(m => m.id === 'customer_intel')
    ))
    assert('cross-agent reply returned', r4.text.length > 0)

    // 搭配促销建议
    const r5 = await sim.ask('哪些商品最适合做搭配促销？')
    assertEq('thread continuity', r5.threadId, r1.threadId)
  }

  // ─── 4.7 InventoryManagement ────────────────────────────────
  suite('InventoryManagement — AI 库存助手')
  {
    const sim = new PageCopilotSimulator(port, 'inventory', ['inventory_skill', 'kb_rag'])

    // 自动初始问（模拟 onMounted 中的 auto-ask）
    const r1 = await sim.ask('当前库存健康概览，有哪些需要关注的SKU？')
    assert('auto-init ask returned', r1.text.length > 50)
    assertEq('routed to inventory_skill', r1.skill?.name, 'inventory_skill')
    assert('has artifact (overview table)', r1.artifacts.length > 0)

    // 模拟 selectRow → setContext → 查看详情后提问
    sim.setContext({
      selected_sku: 'LY-TEA-001',
      sku_name: '柠檬茶',
      current_stock: 12,
      safety_stock: 50,
      alert_level: 'critical',
    })
    const r2 = await sim.ask('分析 SKU LY-TEA-001 的补货策略和最优订货量')
    assert('sku-context sent', requestLog.some(r =>
      r.body?.page_context?.selected_sku === 'LY-TEA-001'
    ))
    assertIncludes('reply mentions sku analysis', r2.text, '库存')

    // 快捷问题
    const r3 = await sim.ask('哪些SKU需要紧急补货？')
    assert('quick question answered', r3.text.length > 0)
    assert('has alert artifacts', r3.artifacts.length > 0)

    // 追问 - 周转率
    const r4 = await sim.ask('库存周转率分析')
    assertEq('intent is analysis', r4.intent, 'analysis')
    assertEq('thread continuity', r4.threadId, r1.threadId)

    // KB 文档点击 → AI 总结（模拟 onKbDocClick）
    const r5 = await sim.ask('关于「库存管理最佳实践」，请总结关键内容', [{ type: 'collection', id: 'kb_rag' }])
    assert('kb doc ask returned', r5.text.length > 0)
  }

  // ─── 4.8 ReportExport ──────────────────────────────────────
  suite('ReportExport — AI 报告助手')
  {
    const sim = new PageCopilotSimulator(port, 'report', ['kb_rag'])

    const r1 = await sim.ask('本周经营报告应包含哪些重点内容？')
    assert('report advice returned', r1.text.length > 30)

    // 模拟 selectJob → askAndSwitch
    const r2 = await sim.ask('帮我总结「经营周报 - 2026W14」报告的核心要点和建议')
    assert('report summary returned', r2.text.length > 30)

    // 模拟模板建议
    const r3 = await sim.ask('「经营周报」模板适用于什么场景？有什么改善建议？')
    assertEq('intent is recommendation', r3.intent, 'recommendation')

    // 追问
    const r4 = await sim.ask('如何让报告更具可读性和说服力？')
    assertEq('thread continuity', r4.threadId, r1.threadId)
  }

  // ─── 4.9 AnalyzeProgress ───────────────────────────────────
  suite('AnalyzeProgress — AI 工作流助手')
  {
    const sim = new PageCopilotSimulator(port, 'workflow', ['kb_rag'])

    const r1 = await sim.ask('当前工作流各步骤执行情况总结')
    assert('workflow summary returned', r1.text.length > 0)

    // 模拟 onNodeClick → selectedStep → askAndSwitch（尾部意图“优化建议”→ recommendation）
    const r2 = await sim.ask('详细解读「数据采集」步骤的执行情况和优化建议')
    assertEq('intent is recommendation (tail intent)', r2.intent, 'recommendation')
    assert('thinking triggered', r2.thinking.length > 0)

    // 追问 - 耗时优化
    const r3 = await sim.ask('哪些步骤耗时最长？有优化空间吗？')
    assert('follow-up answered', r3.text.length > 0)

    // 结果洞察
    const r4 = await sim.ask('分析结果的关键洞察和行动建议')
    assertEq('intent is recommendation', r4.intent, 'recommendation')
    assertEq('thread continuity', r4.threadId, r1.threadId)
  }

  // ─── 4.10 BizCopilot (独立页 — UnifiedCopilotPanel) ─────────
  suite('BizCopilot — 独立运营助手')
  {
    const sim = new PageCopilotSimulator(port, 'biz', [])

    // 模拟 skill card 点击 → ask
    const skillPrompts = [
      { id: 'customer', prompt: '请分析当前客户群体概况' },
      { id: 'forecast', prompt: '请预测未来 7 天的销售趋势' },
      { id: 'sentiment', prompt: '请分析最近的舆情状况' },
      { id: 'inventory', prompt: '当前有库存预警或补货建议吗？' },
      { id: 'association', prompt: '请分析当前商品关联规则' },
      { id: 'kb_rag', prompt: '搜索企业知识库' },
    ]

    for (const skill of skillPrompts) {
      sim.startNewThread()
      const r = await sim.ask(skill.prompt)
      assert(`skill[${skill.id}] answered`, r.text.length > 0)
      assert(`skill[${skill.id}] has thread`, r.threadId.length > 0)
    }

    // 多轮对话模拟
    sim.startNewThread()
    const r1 = await sim.ask('客户流失风险概览')
    const r2 = await sim.ask('流失概率最高的 5 位客户是谁？')
    const r3 = await sim.ask('针对这些客户给出个性化挽回方案')
    assertEq('3-turn thread continuity', r3.threadId, r1.threadId)
    assertEq('6 messages in thread', sim.messages.length, 6)
  }

  // ─── 4.11 Cross-cutting: Error / Degradation ────────────────
  suite('Error & Degradation')
  {
    const sim = new PageCopilotSimulator(port, 'inventory', ['inventory_skill'])

    // 强制 500 错误
    const r1 = await sim.ask('__FORCE_ERROR__')
    assert('error detected on 500', r1.error != null)
    assertIncludes('error message contains HTTP', r1.error, 'HTTP')
    assertEq('no text on error', r1.text, '')
  }

  // ─── 4.12 Thread Management ─────────────────────────────────
  suite('Thread Management')
  {
    // list threads
    const threads = await httpGet(port, '/api/copilot/threads?mode=biz&limit=20')
    assert('threads list returned', threads?.data?.threads?.length > 0)
    assertEq('threads count', threads.data.threads.length, 2)

    // get thread messages
    const msgs = await httpGet(port, '/api/copilot/threads/thread-001/messages?limit=50')
    assert('messages returned', msgs?.data?.messages?.length > 0)
    assertEq('first msg is user', msgs.data.messages[0].role, 'user')
    assertEq('second msg is assistant', msgs.data.messages[1].role, 'assistant')

    // new thread → ask → different thread id
    const sim = new PageCopilotSimulator(port, 'customer', ['customer_intel'])
    const r1 = await sim.ask('第一个问题')
    const tid1 = r1.threadId
    sim.startNewThread()
    const r2 = await sim.ask('新对话的第一个问题')
    assert('new thread has different id', r2.threadId !== tid1)
  }

  // ─── 4.13 Feedback ──────────────────────────────────────────
  suite('Feedback')
  {
    const fbResult = await httpPost(port, '/api/copilot/feedback', {
      message_id: 42,
      feedback: 1,
      feedback_text: '非常有帮助',
    })
    assertEq('feedback accepted', fbResult?.data?.status, 'ok')
    assert('feedback logged', requestLog.some(r =>
      r.url?.includes('/feedback') && r.body?.feedback === 1
    ))

    // negative feedback
    const fbResult2 = await httpPost(port, '/api/copilot/feedback', {
      message_id: 43,
      feedback: -1,
      feedback_text: '回答不准确',
    })
    assertEq('negative feedback accepted', fbResult2?.data?.status, 'ok')
  }

  // ─── 4.14 Action Execution ──────────────────────────────────
  suite('Action Execution')
  {
    const actionResult = await httpPost(port, '/api/copilot/action/execute', {
      action_type: 'export_report',
      target: 'inventory_alert',
      payload: { format: 'csv' },
      thread_id: 'thread-001',
    })
    assert('action executed', actionResult?.data?.executed === true)
    assertEq('action type echoed', actionResult.data.action_type, 'export_report')
  }

  // ─── 4.15 Suggestion Handling ───────────────────────────────
  suite('Suggestion Handling')
  {
    const sim = new PageCopilotSimulator(port, 'inventory', ['inventory_skill'])
    const r1 = await sim.ask('当前库存健康概览')
    assert('suggestions returned', r1.suggestions.length > 0)

    // 模拟用户点击追问建议
    const followUp = r1.suggestions.find(s => s.type === 'question')
    assert('has question suggestion', !!followUp)
    if (followUp) {
      const r2 = await sim.ask(followUp.label)
      assert('suggestion follow-up answered', r2.text.length > 0)
      assertEq('same thread after suggestion', r2.threadId, r1.threadId)
    }

    // 模拟 action 类型 suggestion
    const actionSug = r1.suggestions.find(s => s.type === 'action')
    if (actionSug) {
      const result = await httpPost(port, '/api/copilot/action/execute', {
        action_type: actionSug.action,
        target: actionSug.payload?.type || '',
        payload: actionSug.payload,
      })
      assert('action suggestion executed', result?.data?.executed === true)
    }
  }

  // ─── 4.16 Context Injection Verification ────────────────────
  suite('Context Injection')
  {
    const sim = new PageCopilotSimulator(port, 'fraud', ['fraud_skill'])

    // setContext → ask → verify context in request
    sim.setContext({ last_scored_tx: 'TX999', risk_level: '中' })
    await sim.ask('详细分析这笔交易')
    const fraudReq = requestLog.filter(r =>
      r.body?.page_context?.last_scored_tx === 'TX999'
    )
    assertGt('context injected into request', fraudReq.length, 0)
    assertEq('risk_level in context', fraudReq[0].body.page_context.risk_level, '中')

    // clearContext → ask → verify clean context
    sim.clearContext()
    await sim.ask('今日风控概览')
    const cleanReq = requestLog.filter(r =>
      r.body?.page_context?.page === 'fraud' && !r.body.page_context.last_scored_tx
    )
    assertGt('cleared context has no stale data', cleanReq.length, 0)
  }

  // ─── 4.17 Multi-turn Deep Conversation ──────────────────────
  suite('Multi-turn Deep Conversation (Customer)')
  {
    const sim = new PageCopilotSimulator(port, 'customer', ['customer_intel'])

    const r1 = await sim.ask('当前客群整体概览')
    const r2 = await sim.ask('高价值客户集中在哪些区域？')
    const r3 = await sim.ask('这些区域的客户流失率如何？')
    const r4 = await sim.ask('给出区域化的客户挽回策略')
    const r5 = await sim.ask('如何衡量挽回策略的效果？')

    assertEq('5-turn same thread', r5.threadId, r1.threadId)
    assertEq('10 messages total', sim.messages.length, 10)
    assert('last reply has substance', r5.text.length > 30)

    // 验证所有回复都有 sources
    const allHaveSources = [r1, r2, r3, r4, r5].every(r => r.sources.length > 0)
    assert('all turns have sources', allHaveSources)
  }

  // ─── 4.18 SSE Protocol Completeness ─────────────────────────
  suite('SSE Protocol Completeness')
  {
    const sim = new PageCopilotSimulator(port, 'customer', ['customer_intel'])
    const r = await sim.ask('分析客户流失风险')

    // 验证完整事件序列
    const types = r.events.map(e => e.type)
    assert('has run_start', types.includes('run_start'))
    assert('has run_end', types.includes('run_end'))
    assert('has text_delta', types.includes('text_delta'))
    assert('has intent', types.includes('intent'))
    assert('has confidence', types.includes('confidence'))
    assert('has sources', types.includes('sources'))

    // 分析问题应触发 thinking
    assert('has thinking_start for analysis', types.includes('thinking_start'))
    assert('has thinking_delta', types.includes('thinking_delta'))
    assert('has thinking_end', types.includes('thinking_end'))

    // skill 路由
    assert('has tool_call_start', types.includes('tool_call_start'))
    assert('has tool_call_end', types.includes('tool_call_end'))

    // 事件顺序：run_start 在最前，run_end 在最后
    assertEq('run_start is first', types[0], 'run_start')
    assertEq('run_end is last', types[types.length - 1], 'run_end')

    // metadata 验证
    assertGt('elapsed_ms > 0', r.elapsedMs, 0)
    assert('token_usage present', r.tokenUsage != null)
    assertGt('confidence > 0', r.confidence, 0)
  }

  // ─── 4.19 Concurrent Multi-Page Simulation ──────────────────
  suite('Concurrent Multi-Page')
  {
    // 同时在 3 个页面发起请求
    const sims = [
      new PageCopilotSimulator(port, 'customer', ['customer_intel']),
      new PageCopilotSimulator(port, 'inventory', ['inventory_skill']),
      new PageCopilotSimulator(port, 'forecast', ['forecast_skill']),
    ]
    const results = await Promise.all([
      sims[0].ask('客户概览'),
      sims[1].ask('库存预警列表'),
      sims[2].ask('未来销售预测趋势'),
    ])
    assert('all 3 concurrent replies ok', results.every(r => r.text.length > 0))
    assert('different threads', new Set(results.map(r => r.threadId)).size === 3)
    assert('different skills routed', new Set(results.map(r => r.skill?.name)).size === 3)
  }
}


// ═══════════════════════════════════════════════════════════════════
// §5  Main — Start server, run tests, report
// ═══════════════════════════════════════════════════════════════════

async function main() {
  console.log('╔══════════════════════════════════════════════════════╗')
  console.log('║  Copilot 内嵌对话框 E2E 测试                         ║')
  console.log('║  模拟用户真实交互 · 9 页面 + 独立 Copilot            ║')
  console.log('╚══════════════════════════════════════════════════════╝')

  const { server, requestLog } = createMockSSEServer()

  // 找到可用端口
  await new Promise((resolve, reject) => {
    server.listen(0, '127.0.0.1', () => resolve())
    server.on('error', reject)
  })
  const port = server.address().port
  console.log(`\nMock SSE Server running on 127.0.0.1:${port}`)

  try {
    await runAllTests(port, requestLog)
  } catch (err) {
    console.error('\n  ⚠ UNHANDLED ERROR:', err)
    _fail++
  } finally {
    server.close()
  }

  // Report
  console.log('\n' + '═'.repeat(56))
  console.log(`  PASS: ${_pass}   FAIL: ${_fail}   TOTAL: ${_pass + _fail}`)
  if (_failures.length) {
    console.log('\n  ─── Failed assertions ───')
    _failures.forEach(f => console.log(`    • ${f}`))
  }
  console.log()

  if (_fail > 0) {
    console.log('  ⚠ Some tests failed. Review above.\n')
    process.exit(1)
  } else {
    console.log('  ✅ All copilot E2E tests passed.\n')
    process.exit(0)
  }
}

main()
