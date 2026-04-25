<template>
  <div class="trend">
    <div class="trend__hd">
      <span class="trend__title">近 7 天销售趋势</span>
      <span class="trend__legend">
        <span class="dot dot--solid"></span> 实际
        <span class="dot dot--dash"></span> 预测
      </span>
    </div>
    <div class="trend__body">
      <v-chart v-if="data.length" :option="option" autoresize />
      <div v-else class="trend__empty">暂无趋势数据</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useTheme } from '@/composables/useTheme'

const props = defineProps({
  data: { type: Array, default: () => [] },
})

const { isDark } = useTheme()

const option = computed(() => {
  const txt = isDark.value ? '#a1a1aa' : '#71717a'
  const grid = isDark.value ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)'
  const pri = isDark.value ? '#ffffff' : '#000000'
  const sec = '#71717a'
  const errC = '#dc2626'
  const actuals   = props.data.map((d) => d.actual)
  const predicted = props.data.map((d) => d.predicted)
  const dates     = props.data.map((d) => d.date)

  const validActuals = actuals.filter((v) => v != null)
  const maxVal = validActuals.length ? Math.max(...validActuals) : 0
  const minVal = validActuals.length ? Math.min(...validActuals) : 0
  const maxIdx = actuals.indexOf(maxVal)
  const minIdx = actuals.indexOf(minVal)

  const riskAreas = []
  let riskStart = null
  props.data.forEach((d, i) => {
    const isRisk = d.actual != null && d.predicted != null && d.actual < d.predicted * 0.95
    if (isRisk && riskStart === null) riskStart = i
    if (!isRisk && riskStart !== null) {
      riskAreas.push([{ xAxis: dates[riskStart] }, { xAxis: dates[i - 1] }])
      riskStart = null
    }
  })
  if (riskStart !== null) riskAreas.push([{ xAxis: dates[riskStart] }, { xAxis: dates[dates.length - 1] }])

  return {
    backgroundColor: 'transparent',
    grid: { top: 30, right: 12, bottom: 4, left: 8, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: isDark.value ? '#18181b' : '#fff',
      borderColor: isDark.value ? '#27272a' : '#e5e7eb',
      textStyle: { color: isDark.value ? '#fafafa' : '#09090b', fontSize: 11, fontFamily: 'Geist Mono, monospace' },
      axisPointer: { lineStyle: { color: grid, type: 'dashed' } },
      padding: [8, 12],
      extraCssText: 'border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);',
      formatter(params) {
        const a = params.find((p) => p.seriesName === '实际')
        const p = params.find((p) => p.seriesName === '预测')
        const av = a?.value, pv = p?.value
        let html = `<div style="font-weight:600;margin-bottom:4px">${params[0].axisValue}</div>`
        if (av != null) html += `<div>实际：<b>¥${Number(av).toLocaleString()}</b></div>`
        if (pv != null) html += `<div style="color:${sec}">预测：¥${Number(pv).toLocaleString()}</div>`
        if (av != null && pv != null && pv > 0) {
          const devPct = ((av - pv) / pv * 100).toFixed(1)
          const devColor = devPct < -5 ? errC : devPct > 5 ? '#22c55e' : txt
          html += `<div style="margin-top:3px;color:${devColor};font-size:10px">`
          html += `偏差 ${devPct > 0 ? '+' : ''}${devPct}%`
          if (devPct < -5) html += ' ⚠ 显著低于预期'
          else if (devPct > 5) html += ' ✦ 超出预期'
          html += `</div>`
        }
        return html
      },
    },
    xAxis: {
      type: 'category', data: dates,
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: txt, fontFamily: 'Geist Mono', fontSize: 10, margin: 8 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: grid, type: 'dashed' } },
      axisLabel: { color: txt, fontFamily: 'Geist Mono', fontSize: 10 },
    },
    series: [
      {
        name: '实际', type: 'line', data: actuals, smooth: 0.3,
        lineStyle: { width: 2.5, color: pri },
        itemStyle: { color: pri },
        showSymbol: false,
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: isDark.value ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)' },
              { offset: 1, color: 'transparent' },
            ],
          },
        },
        markPoint: {
          symbol: 'circle', symbolSize: 8,
          label: { fontSize: 9, fontFamily: 'Geist Mono', color: txt, position: 'top', distance: 8, formatter: (p) => '¥' + Number(p.value).toLocaleString() },
          data: [
            ...(maxIdx >= 0 ? [{ coord: [dates[maxIdx], maxVal], itemStyle: { color: '#22c55e', borderColor: '#fff', borderWidth: 1.5 } }] : []),
            ...(minIdx >= 0 && minIdx !== maxIdx ? [{ coord: [dates[minIdx], minVal], itemStyle: { color: errC, borderColor: '#fff', borderWidth: 1.5 } }] : []),
          ],
        },
        markArea: riskAreas.length
          ? { silent: true, itemStyle: { color: isDark.value ? 'rgba(220,38,38,0.08)' : 'rgba(220,38,38,0.06)' }, data: riskAreas }
          : undefined,
      },
      {
        name: '预测', type: 'line', data: predicted, smooth: 0.3,
        lineStyle: { width: 1.5, color: sec, type: 'dashed' },
        itemStyle: { color: sec }, symbol: 'none',
      },
    ],
  }
})
</script>

<style scoped>
.trend {
  display: flex; flex-direction: column;
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-card); background: var(--v2-bg-card);
  padding: 10px 12px; min-height: 0;
}
.trend__hd { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; flex-shrink: 0; }
.trend__title { font-family: var(--v2-font-mono); font-size: 11px; letter-spacing: 0.03em; color: var(--v2-text-3); text-transform: uppercase; }
.trend__legend { display: flex; align-items: center; gap: 10px; font-size: 10px; color: var(--v2-text-4); }
.dot { display: inline-block; width: 16px; height: 0; margin-right: 3px; vertical-align: middle; }
.dot--solid { border-top: 2px solid var(--v2-text-1); }
.dot--dash  { border-top: 2px dashed var(--v2-text-3); }
.trend__body { flex: 1; min-height: 0; }
.trend__empty { display: flex; align-items: center; justify-content: center; height: 100%; color: var(--v2-text-4); font-size: var(--v2-text-sm); }
</style>
