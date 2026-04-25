<template>
  <div class="cust-art">
    <div class="cust-art__summary" v-if="data?.summary">
      <div class="cust-art__stat">
        <span class="cust-art__stat-val">{{ formatNum(data.summary.rfm_total_customers) }}</span>
        <span class="cust-art__stat-label">Customers</span>
      </div>
      <div class="cust-art__stat cust-art__stat--warn" v-if="data.summary.churn_high_risk_count > 0">
        <span class="cust-art__stat-val">{{ data.summary.churn_high_risk_count }}</span>
        <span class="cust-art__stat-label">High Churn Risk</span>
      </div>
      <div class="cust-art__stat">
        <span class="cust-art__stat-val">{{ pct(data.summary.churn_high_risk_ratio) }}</span>
        <span class="cust-art__stat-label">Churn Ratio</span>
      </div>
      <div class="cust-art__stat">
        <span class="cust-art__stat-val">{{ formatCurrency(data.summary.clv_avg_90d) }}</span>
        <span class="cust-art__stat-label">Avg CLV (90d)</span>
      </div>
    </div>

    <!-- RFM Distribution -->
    <div class="cust-art__section" v-if="rfmData.length">
      <div class="cust-art__sec-label">RFM Segments</div>
      <div class="cust-art__rfm-grid">
        <div v-for="s in rfmData" :key="s.segment" class="cust-art__rfm-item">
          <div class="cust-art__rfm-bar" :style="{ width: (s.count / maxRfm * 100) + '%' }"></div>
          <span class="cust-art__rfm-seg">{{ s.segment }}</span>
          <span class="cust-art__rfm-count">{{ s.count }}</span>
        </div>
      </div>
    </div>

    <!-- Churn Top Risk -->
    <div class="cust-art__section" v-if="data?.churn_top_risk?.length">
      <div class="cust-art__sec-label">Top Churn Risk</div>
      <table class="cust-art__table">
        <thead><tr><th>Customer</th><th class="num">Risk Score</th><th class="num">CLV</th></tr></thead>
        <tbody>
          <tr v-for="c in data.churn_top_risk.slice(0, 10)" :key="c.customer_id">
            <td class="mono">{{ c.customer_id }}</td>
            <td class="num">{{ (c.score * 100).toFixed(0) }}%</td>
            <td class="num">{{ formatCurrency(c.extra?.clv || c.score) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({ data: Object, metadata: Object })
function formatNum(n) { return n != null ? Number(n).toLocaleString() : '-' }
function formatCurrency(n) { return n != null ? '\u00a5' + Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 }) : '-' }
function pct(n) { return n != null ? (n * 100).toFixed(1) + '%' : '-' }
const rfmData = computed(() => props.data?.rfm_segment_distribution || props.data?.rfm_distribution || [])
const maxRfm = computed(() => {
  return Math.max(...rfmData.value.map(s => s.count), 1)
})
</script>

<style scoped>
.cust-art__summary { display: flex; gap: 24px; margin-bottom: 16px; flex-wrap: wrap; }
.cust-art__stat { display: flex; flex-direction: column; }
.cust-art__stat-val { font-size: 20px; font-weight: 600; color: #18181b; font-variant-numeric: tabular-nums; }
.cust-art__stat-label { font-size: 12px; color: #71717a; margin-top: 2px; }
.cust-art__stat--warn .cust-art__stat-val { color: #dc2626; }
.cust-art__section { margin-top: 16px; }
.cust-art__sec-label { font-size: 12px; color: #71717a; font-weight: 500; margin-bottom: 8px; }
.cust-art__rfm-grid { display: flex; flex-direction: column; gap: 4px; }
.cust-art__rfm-item { display: flex; align-items: center; gap: 8px; position: relative; padding: 4px 0; }
.cust-art__rfm-bar { position: absolute; left: 0; top: 0; bottom: 0; background: rgba(24,24,27,0.04); border-radius: 3px; z-index: 0; }
.cust-art__rfm-seg { position: relative; z-index: 1; font-size: 13px; min-width: 120px; }
.cust-art__rfm-count { position: relative; z-index: 1; font-size: 13px; color: #71717a; font-variant-numeric: tabular-nums; margin-left: auto; }
.cust-art__table { width: 100%; border-collapse: collapse; font-size: 13px; }
.cust-art__table th { text-align: left; padding: 8px 12px; border-bottom: 1px solid rgba(0,0,0,0.08); color: #71717a; font-weight: 500; }
.cust-art__table td { padding: 6px 12px; border-bottom: 1px solid rgba(0,0,0,0.03); }
.cust-art__table .num { text-align: right; font-variant-numeric: tabular-nums; }
.cust-art__table .mono { font-family: 'Geist Mono', monospace; font-size: 12px; }
</style>
