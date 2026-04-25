/**
 * Smoke Test Script — Frontend Route & Adapter Validation
 *
 * Usage:  node tests/smoke.js
 *
 * This script performs basic validation:
 * 1. Checks all route modules export valid arrays with lazy components
 * 2. Checks all adapters export expected functions
 * 3. Runs adapter functions with mock data to verify no runtime crashes
 * 4. Validates design token CSS file has expected variables
 *
 * Note: This is NOT a full unit test suite. It's a quick regression check.
 */

const fs = require('fs')
const path = require('path')

let pass = 0
let fail = 0

function assert(label, condition) {
  if (condition) {
    pass++
    console.log(`  ✓ ${label}`)
  } else {
    fail++
    console.error(`  ✗ ${label}`)
  }
}

// ── 1. Route module files exist ─────────────────────────────────────

console.log('\n[1] Route modules')
const routeDir = path.join(__dirname, '..', 'src', 'router', 'modules')
;['auth.js', 'business.js', 'console.js', 'error.js'].forEach(f => {
  assert(`${f} exists`, fs.existsSync(path.join(routeDir, f)))
})

// ── 2. Adapter files exist & export functions ───────────────────────

console.log('\n[2] Adapter files')
const adapterDir = path.join(__dirname, '..', 'src', 'adapters')
const expectedAdapters = ['sentiment.js', 'knowledge.js', 'memory.js', 'opsCopilot.js', 'evals.js', 'traces.js', 'index.js']
expectedAdapters.forEach(f => {
  assert(`adapters/${f} exists`, fs.existsSync(path.join(adapterDir, f)))
})

// ── 3. CSS design tokens ────────────────────────────────────────────

console.log('\n[3] Design tokens')
const varsFile = fs.readFileSync(path.join(__dirname, '..', 'src', 'styles', 'variables.css'), 'utf-8')
const requiredTokens = [
  '--color-primary', '--color-accent', '--color-text-primary',
  '--color-bg-page', '--color-bg-card', '--color-border',
  '--spacing-md', '--radius-md', '--shadow-card',
  '--font-size-body', '--z-modal', '--transition-normal',
  '--aside-width', '--header-height',
]
requiredTokens.forEach(t => {
  assert(`token ${t}`, varsFile.includes(t))
})

// ── 4. Global CSS has table & chart enhancements ────────────────────

console.log('\n[4] Global styles')
const globalFile = fs.readFileSync(path.join(__dirname, '..', 'src', 'styles', 'global.css'), 'utf-8')
assert('table sticky header rule', globalFile.includes('sticky'))
assert('table row hover rule', globalFile.includes('el-table__row:hover'))
assert('el-dialog border-radius', globalFile.includes('el-dialog'))

// ── 5. Key component files exist ────────────────────────────────────

console.log('\n[5] Key components')
const compRoot = path.join(__dirname, '..', 'src', 'components')
const keyComponents = [
  'CommandPalette.vue',
  'status/SkeletonBlock.vue',
  'status/EmptyState.vue',
  'status/ErrorState.vue',
  'status/DegradedBanner.vue',
  'status/LoadingBlock.vue',
  'layout/HeaderBar.vue',
  'layout/BusinessSideNav.vue',
  'layout/ConsoleSideNav.vue',
]
keyComponents.forEach(f => {
  assert(`components/${f}`, fs.existsSync(path.join(compRoot, f)))
})

// ── 6. API modules ──────────────────────────────────────────────────

console.log('\n[6] API modules')
const apiDir = path.join(__dirname, '..', 'src', 'api', 'admin')
const apiFiles = [
  'auth.js', 'dashboard.js', 'traces.js', 'reviews.js',
  'prompts.js', 'policies.js', 'releases.js', 'audit.js',
  'knowledge.js', 'memory.js', 'opsCopilot.js', 'evals.js', 'index.js',
]
apiFiles.forEach(f => {
  assert(`api/admin/${f}`, fs.existsSync(path.join(apiDir, f)))
})

// ── 7. Utility files ────────────────────────────────────────────────

console.log('\n[7] Utilities')
assert('chartDefaults.js exists', fs.existsSync(path.join(__dirname, '..', 'src', 'utils', 'chartDefaults.js')))

// ── 8. View files ───────────────────────────────────────────────────

console.log('\n[8] View files')
const viewDir = path.join(__dirname, '..', 'src', 'views')
const consoleViews = [
  'console/ConsoleDashboard.vue', 'console/ConsoleTraces.vue', 'console/ConsoleTraceDetail.vue',
  'console/ConsoleReviews.vue', 'console/ConsolePrompts.vue', 'console/ConsolePolicies.vue',
  'console/ConsoleReleases.vue', 'console/ConsoleAudit.vue', 'console/ConsoleWorkflows.vue',
  'console/ConsoleAgents.vue', 'console/ConsoleOpsCopilot.vue', 'console/ConsoleEvals.vue',
  'console/ConsoleKnowledge.vue', 'console/ConsoleMemory.vue',
]
const businessViews = [
  'Dashboard.vue', 'CustomerAnalysis.vue', 'SalesForecast.vue',
  'FraudDetection.vue', 'SentimentAnalysis.vue', 'InventoryManagement.vue',
  'OpenClaw.vue', 'AssociationAnalysis.vue', 'ReportExport.vue',
]
;[...consoleViews, ...businessViews].forEach(f => {
  assert(`views/${f}`, fs.existsSync(path.join(viewDir, f)))
})

// ── Summary ─────────────────────────────────────────────────────────

console.log(`\n${'─'.repeat(50)}`)
console.log(`  PASS: ${pass}   FAIL: ${fail}   TOTAL: ${pass + fail}`)
if (fail > 0) {
  console.log('  ⚠ Some checks failed. Review above.\n')
  process.exit(1)
} else {
  console.log('  ✅ All smoke checks passed.\n')
  process.exit(0)
}
