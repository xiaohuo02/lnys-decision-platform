<template>
  <div class="fc-art">
    <div class="fc-art__summary" v-if="data?.summary">
      <div class="fc-art__stat">
        <span class="fc-art__stat-val">{{ data.summary.model_used }}</span>
        <span class="fc-art__stat-label">Model</span>
      </div>
      <div class="fc-art__stat">
        <span class="fc-art__stat-val">{{ formatNum(data.summary.total_forecast) }}</span>
        <span class="fc-art__stat-label">Total Forecast</span>
      </div>
      <div class="fc-art__stat">
        <span class="fc-art__stat-val">{{ data.summary.mape != null ? (data.summary.mape * 100).toFixed(1) + '%' : '-' }}</span>
        <span class="fc-art__stat-label">MAPE</span>
      </div>
      <div class="fc-art__stat fc-art__stat--warn" v-if="data.summary.degraded">
        <span class="fc-art__stat-val">Degraded</span>
        <span class="fc-art__stat-label">Status</span>
      </div>
    </div>
    <div class="fc-art__chart" ref="chartRef"></div>
    <div class="fc-art__models" v-if="data?.model_comparison?.length">
      <div class="fc-art__model-label">Model Comparison</div>
      <div class="fc-art__model-row" v-for="m in data.model_comparison" :key="m.model_name">
        <span class="fc-art__model-name">{{ m.model_name }}</span>
        <span class="fc-art__model-mape">MAPE {{ m.mape != null ? (m.mape * 100).toFixed(1) + '%' : '-' }}</span>
        <span class="fc-art__model-total">{{ formatNum(m.total_forecast) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, nextTick } from 'vue'

const props = defineProps({ data: Object, metadata: Object })
const chartRef = ref(null)
let chartInstance = null

function formatNum(n) {
  return n != null ? Number(n).toLocaleString() : '-'
}

async function renderChart() {
  if (!chartRef.value || !props.data?.daily_forecast?.length) return
  try {
    const echarts = await import('echarts/core')
    const { LineChart } = await import('echarts/charts')
    const { GridComponent, TooltipComponent } = await import('echarts/components')
    const { CanvasRenderer } = await import('echarts/renderers')
    echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])

    if (chartInstance) chartInstance.dispose()
    chartInstance = echarts.init(chartRef.value)

    const dates = props.data.daily_forecast.map(d => d.date)
    const values = props.data.daily_forecast.map(d => d.value)

    chartInstance.setOption({
      grid: { left: 48, right: 16, top: 16, bottom: 32 },
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: dates, axisLine: { lineStyle: { color: '#e4e4e7' } }, axisLabel: { color: '#71717a', fontSize: 11 } },
      yAxis: { type: 'value', splitLine: { lineStyle: { color: '#f4f4f5' } }, axisLabel: { color: '#71717a', fontSize: 11 } },
      series: [{ type: 'line', data: values, smooth: true, lineStyle: { color: '#18181b', width: 1.5 }, itemStyle: { color: '#18181b' }, areaStyle: { color: 'rgba(24,24,27,0.04)' }, symbol: 'circle', symbolSize: 4 }],
    })
  } catch { /* echarts not available */ }
}

onMounted(() => renderChart())
watch(() => props.data, () => nextTick(renderChart), { deep: true })
</script>

<style scoped>
.fc-art__summary { display: flex; gap: 24px; margin-bottom: 16px; }
.fc-art__stat { display: flex; flex-direction: column; }
.fc-art__stat-val { font-size: 20px; font-weight: 600; color: #18181b; }
.fc-art__stat-label { font-size: 12px; color: #71717a; margin-top: 2px; }
.fc-art__stat--warn .fc-art__stat-val { color: #f59e0b; }
.fc-art__chart { height: 220px; width: 100%; }
.fc-art__models { margin-top: 16px; }
.fc-art__model-label { font-size: 12px; color: #71717a; margin-bottom: 8px; font-weight: 500; }
.fc-art__model-row { display: flex; align-items: center; gap: 16px; padding: 6px 0; border-bottom: 1px solid rgba(0,0,0,0.03); font-size: 13px; }
.fc-art__model-name { font-weight: 500; min-width: 120px; }
.fc-art__model-mape { color: #71717a; font-variant-numeric: tabular-nums; }
.fc-art__model-total { margin-left: auto; font-variant-numeric: tabular-nums; }
</style>
