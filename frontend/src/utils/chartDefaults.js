/**
 * V2 Chart Theme — Enterprise AI Data Product
 *
 * Design principles:
 * - Low saturation, harmonious palette (no high-sat rainbow)
 * - Consistent grid / axis / tooltip / legend across all charts
 * - Clean whitespace, subtle grid lines
 */

const FONT = "'Inter', 'PingFang SC', 'Helvetica Neue', sans-serif"

/* ── Color Palette (ordered by contrast, low saturation) ────── */
export const chartColors = [
  '#2563eb',  // blue-600
  '#7c3aed',  // violet-600
  '#0891b2',  // cyan-600
  '#059669',  // emerald-600
  '#d97706',  // amber-600
  '#dc2626',  // red-600
  '#4f46e5',  // indigo-600
  '#0d9488',  // teal-600
  '#ca8a04',  // yellow-600
  '#9333ea',  // purple-600
]

export const chartColorsLight = [
  '#93bbfd', '#c4b5fd', '#67e8f9', '#6ee7b7',
  '#fcd34d', '#fca5a5', '#a5b4fc', '#5eead4',
]

/* ── Tooltip ──────────────────────────────────────────────────── */
export const defaultTooltip = {
  trigger: 'axis',
  backgroundColor: 'rgba(255,255,255,.98)',
  borderColor: '#e5e7eb',
  borderWidth: 1,
  textStyle: { color: '#171717', fontSize: 12, fontFamily: FONT },
  padding: [8, 12],
  extraCssText: 'box-shadow: 0 4px 12px rgba(0,0,0,.08); border-radius: 6px; backdrop-filter: blur(4px);',
  axisPointer: {
    type: 'line',
    lineStyle: { color: '#d1d5db', type: 'dashed', width: 1 },
  },
}

/* ── Legend ────────────────────────────────────────────────────── */
export const defaultLegend = {
  type: 'scroll',
  bottom: 0,
  itemWidth: 10,
  itemHeight: 10,
  itemGap: 16,
  icon: 'roundRect',
  textStyle: { color: '#737373', fontSize: 11, fontFamily: FONT },
}

/* ── Grid ─────────────────────────────────────────────────────── */
export const defaultGrid = {
  left: 12,
  right: 16,
  top: 36,
  bottom: 40,
  containLabel: true,
}

/* ── Axis defaults ────────────────────────────────────────────── */
export const defaultXAxis = {
  axisLine:  { lineStyle: { color: '#e5e7eb' } },
  axisTick:  { show: false },
  axisLabel: { color: '#737373', fontSize: 11, fontFamily: FONT },
  splitLine: { show: false },
}

export const defaultYAxis = {
  axisLine:  { show: false },
  axisTick:  { show: false },
  axisLabel: { color: '#a3a3a3', fontSize: 11, fontFamily: FONT },
  splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } },
}

/* ── Toolbox (save / data view / restore) ────────────────────── */
export const defaultToolbox = {
  show: true,
  right: 12,
  top: 4,
  feature: {
    saveAsImage: { title: 'Save PNG', pixelRatio: 2, iconStyle: { borderColor: '#a3a3a3' } },
    dataView:    { show: true, title: 'Data', lang: ['Data View', 'Close', 'Refresh'], readOnly: true, textareaColor: '#f5f5f5', textColor: '#171717' },
    restore:     { title: 'Reset' },
  },
  iconStyle: { borderColor: '#d4d4d4' },
  emphasis:  { iconStyle: { borderColor: '#2563eb' } },
}

/**
 * Build a base option object with V2 unified defaults.
 * @param {Object} overrides - page-specific options merged on top
 */
export function baseChartOption(overrides = {}) {
  return {
    color: chartColors,
    tooltip: { ...defaultTooltip },
    legend:  { ...defaultLegend },
    grid:    { ...defaultGrid },
    toolbox: { ...defaultToolbox, ...(overrides.toolbox || {}) },
    xAxis:   { ...defaultXAxis, ...(overrides.xAxis || {}) },
    yAxis:   { ...defaultYAxis, ...(overrides.yAxis || {}) },
    ...overrides,
  }
}

/**
 * Build a pie/donut chart base option.
 */
export function basePieOption(overrides = {}) {
  return {
    color: chartColors,
    tooltip: { ...defaultTooltip, trigger: 'item' },
    legend:  { ...defaultLegend },
    ...overrides,
  }
}

/**
 * Download chart as PNG.
 */
export function exportChartPNG(chartRef, filename = 'chart') {
  const instance = chartRef?.chart || chartRef
  if (!instance?.getDataURL) return
  const url = instance.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#fff' })
  const a = document.createElement('a')
  a.href = url
  a.download = `${filename}.png`
  a.click()
}

/**
 * Export data rows as CSV.
 */
export function exportCSV(rows, filename = 'data') {
  if (!rows?.length) return
  const keys = Object.keys(rows[0])
  const csv = [keys.join(','), ...rows.map(r => keys.map(k => `"${r[k] ?? ''}"`).join(','))].join('\n')
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${filename}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
}
