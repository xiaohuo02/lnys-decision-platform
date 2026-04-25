/**
 * 修复验证测试 — 只测试之前 FAIL/WARN 的场景
 * 节约 LLM token，跳过已通过项
 *
 * 运行: node frontend/tests/copilot_fix_verify.js
 */
const { execSync } = require('child_process')
const fs = require('fs')
const path = require('path')

const SSH = 'lnys'
const API = 'http://127.0.0.1:8000'
let _token = ''
const results = []
const PAUSE = 8000

function ssh(cmd) {
  const b64 = Buffer.from(cmd).toString('base64')
  try {
    return execSync(`ssh ${SSH} "echo ${b64} | base64 -d | bash"`, {
      encoding: 'utf-8', timeout: 120_000, windowsHide: true,
    }).trim()
  } catch (e) {
    return e.stdout?.trim?.() || e.stderr?.trim?.() || `ERROR: ${e.message}`
  }
}
function sshJson(cmd) {
  const raw = ssh(cmd)
  try { return JSON.parse(raw) } catch { return { _raw: raw, _parseError: true } }
}
function delay(ms) { execSync(`powershell -c "Start-Sleep -Milliseconds ${ms}"`, { windowsHide: true }) }

function stream(body) {
  const bodyJson = JSON.stringify(body).replace(/'/g, "'\\''")
  const raw = ssh(`curl -s -m 90 -X POST ${API}/api/copilot/stream -H 'Content-Type:application/json' -H 'Authorization:Bearer ${_token}' -d '${bodyJson}'`)
  const r = { text: '', skill: null, intent: '', confidence: 0, threadId: '', events: [], artifacts: [] }
  if (!raw) return r
  for (const line of raw.split('\n')) {
    if (!line.startsWith('data: ')) continue
    try {
      const evt = JSON.parse(line.slice(6).trim())
      r.events.push(evt.type)
      if (evt.type === 'text_delta') r.text += evt.content || ''
      if (evt.type === 'tool_call_start') r.skill = evt.metadata?.skill
      if (evt.type === 'run_start') r.threadId = evt.metadata?.thread_id || ''
      if (evt.type === 'intent') r.intent = evt.content || ''
      if (evt.type === 'confidence') r.confidence = evt.content || 0
      if (evt.type === 'artifact_start') r.artifacts.push(evt.artifact_type)
      if (evt.type === 'artifact_delta') r.artifactData = evt.content
    } catch {}
  }
  return r
}

function check(name, r, expect = {}) {
  const ok = []
  const fail = []

  if (r.text.length > 20) ok.push(`text=${r.text.length}c`)
  else fail.push(`text too short (${r.text.length}c)`)

  if (r.events.includes('run_start')) ok.push('run_start')
  else fail.push('no run_start')

  if (r.events.includes('run_end')) ok.push('run_end')
  else fail.push('no run_end')

  if (r.intent) ok.push(`intent=${r.intent}`)
  else fail.push('no intent')

  if (r.confidence > 0) ok.push(`conf=${r.confidence}`)

  if (expect.skill && r.skill === expect.skill) ok.push(`skill=${r.skill} ✓`)
  else if (expect.skill) fail.push(`skill expected=${expect.skill} got=${r.skill}`)

  if (expect.keyword && r.text.includes(expect.keyword)) ok.push(`"${expect.keyword}" ✓`)
  else if (expect.keyword) fail.push(`missing "${expect.keyword}"`)

  if (expect.artifactData) {
    const ad = r.artifactData
    if (ad && JSON.stringify(ad).includes(expect.artifactData)) ok.push(`artifact has "${expect.artifactData}" ✓`)
    else fail.push(`artifact missing "${expect.artifactData}"`)
  }

  const status = fail.length === 0 ? 'PASS' : 'FAIL'
  const icon = status === 'PASS' ? '✅' : '❌'
  console.log(`${icon} ${name}`)
  console.log(`   OK: ${ok.join(', ')}`)
  if (fail.length) console.log(`   FAIL: ${fail.join(', ')}`)
  console.log(`   reply: ${r.text.slice(0, 120).replace(/\n/g, ' ')}...`)
  results.push({ name, status, ok, fail })
}

// ═══════════════════════════════════════════════════════
function main() {
  console.log('╔════════════════════════════════════════════════╗')
  console.log('║  修复验证 — 仅测试之前失败项                  ║')
  console.log('╚════════════════════════════════════════════════╝')

  // Login
  const login = sshJson(`curl -sf -X POST ${API}/admin/auth/login -H 'Content-Type:application/json' -d '{"username":"admin","password":"admin"}'`)
  if (!login?.access_token) { console.error('登录失败'); process.exit(1) }
  _token = login.access_token
  console.log(`✓ token ok\n`)

  // ── FIX1: Sentiment 数据文件名修复 ──
  console.log('── FIX1: Sentiment 舆情数据 ──')
  const s1 = stream({
    question: '当前舆情整体态势如何？正负面比例',
    page_context: { page: 'sentiment', think_mode: 'auto', mentions: [{ type: 'skill', id: 'sentiment_skill' }] },
  })
  check('Sentiment · 舆情概览', s1, { skill: 'sentiment_skill', keyword: '负面' })

  delay(PAUSE)

  // ── FIX2: Fraud 路由 biz 模式 ──
  console.log('\n── FIX2: Fraud biz 模式路由 ──')
  const f1 = stream({
    question: '今日风控整体态势如何？拦截率和高风险特征',
    page_context: { page: 'fraud', think_mode: 'auto', mentions: [{ type: 'skill', id: 'fraud_skill' }] },
  })
  check('Fraud · 风控态势(biz)', f1, { skill: 'fraud_skill', keyword: '风险' })

  delay(PAUSE)

  // ── FIX3: Inventory 数据上传验证 ──
  console.log('\n── FIX3: Inventory 库存数据 ──')
  const i1 = stream({
    question: '当前库存健康概览，有哪些需要紧急补货的SKU？',
    page_context: { page: 'inventory', think_mode: 'auto', mentions: [{ type: 'skill', id: 'inventory_skill' }] },
  })
  check('Inventory · 库存概览', i1, { skill: 'inventory_skill', keyword: '补货' })

  delay(PAUSE)

  // ── FIX4: Customer 多轮 RFM 数据不丢失 ──
  console.log('\n── FIX4: Customer 多轮 RFM ──')
  const c1 = stream({
    question: '当前客群整体概览和关键指标',
    page_context: { page: 'customer', think_mode: 'auto', mentions: [{ type: 'skill', id: 'customer_intel' }] },
  })
  check('Customer · 概览(Turn1)', c1, { skill: 'customer_intel_skill' })

  const c2 = stream({
    question: '高价值客户的RFM分层分布情况如何？',
    thread_id: c1.threadId,
    page_context: { page: 'customer', think_mode: 'auto', mentions: [{ type: 'skill', id: 'customer_intel' }] },
  })
  // 关键：验证 artifact 中 rfm_total_customers > 0
  const rfmTotal = c2.artifactData?.summary?.rfm_total_customers || 0
  console.log(`   RFM客户数: ${rfmTotal} ${rfmTotal > 0 ? '✅' : '❌ 仍然为0'}`)
  check('Customer · RFM追问(Turn2)', c2, { skill: 'customer_intel_skill' })

  delay(PAUSE)

  // ── FIX5: Report/Workflow 路由到 kb_rag ──
  console.log('\n── FIX5: Report 路由 ──')
  const rp = stream({
    question: '本周经营报告应包含哪些重点内容？',
    page_context: { page: 'report', think_mode: 'auto', mentions: [{ type: 'collection', id: 'kb_rag' }] },
  })
  check('Report · 报告建议', rp, { keyword: '报告' })

  delay(PAUSE)

  // ── FIX6: Intent/Confidence SSE 事件 ──
  console.log('\n── FIX6: Intent/Confidence 验证 ──')
  const ic = stream({
    question: '预测模型整体表现如何',
    page_context: { page: 'forecast', think_mode: 'auto', mentions: [{ type: 'skill', id: 'forecast_skill' }] },
  })
  check('Forecast · intent/conf', ic, { skill: 'forecast_skill' })

  // ═══════════ Summary ═══════════
  const pass = results.filter(r => r.status === 'PASS').length
  const fail = results.filter(r => r.status === 'FAIL').length
  console.log(`\n${'═'.repeat(50)}`)
  console.log(`  ✅ PASS: ${pass}   ❌ FAIL: ${fail}   TOTAL: ${results.length}`)
  process.exit(fail > 0 ? 1 : 0)
}

main()
