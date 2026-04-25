<template>
  <div class="sent-art">
    <div class="sent-art__summary" v-if="data?.summary">
      <div class="sent-art__stat">
        <span class="sent-art__stat-val">{{ formatNum(data.summary.total_reviews) }}</span>
        <span class="sent-art__stat-label">Total Reviews</span>
      </div>
      <div class="sent-art__stat sent-art__stat--pos">
        <span class="sent-art__stat-val">{{ pct(data.summary.positive_ratio) }}</span>
        <span class="sent-art__stat-label">Positive</span>
      </div>
      <div class="sent-art__stat">
        <span class="sent-art__stat-val">{{ pct(data.summary.neutral_ratio) }}</span>
        <span class="sent-art__stat-label">Neutral</span>
      </div>
      <div class="sent-art__stat" :class="{ 'sent-art__stat--neg': data.summary.negative_alert }">
        <span class="sent-art__stat-val">{{ pct(data.summary.negative_ratio) }}</span>
        <span class="sent-art__stat-label">Negative</span>
      </div>
    </div>
    <div class="sent-art__bar">
      <div class="sent-art__bar-seg sent-art__bar-seg--pos" :style="{ width: pct(data?.summary?.positive_ratio) }"></div>
      <div class="sent-art__bar-seg sent-art__bar-seg--neu" :style="{ width: pct(data?.summary?.neutral_ratio) }"></div>
      <div class="sent-art__bar-seg sent-art__bar-seg--neg" :style="{ width: pct(data?.summary?.negative_ratio) }"></div>
    </div>
    <div class="sent-art__alert" v-if="data?.summary?.negative_alert">Negative ratio exceeds threshold</div>
    <div class="sent-art__themes" v-if="data?.top_themes?.length">
      <div class="sent-art__themes-label">Top Themes</div>
      <div class="sent-art__theme" v-for="t in data.top_themes" :key="t.theme">
        <span class="sent-art__theme-name">{{ t.theme }}</span>
        <span class="sent-art__theme-count">{{ t.count }}</span>
        <span class="sent-art__theme-sent" :class="'sent-art__theme-sent--' + t.sentiment">{{ t.sentiment }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({ data: Object, metadata: Object })
function formatNum(n) { return n != null ? Number(n).toLocaleString() : '-' }
function pct(n) { return n != null ? (n * 100).toFixed(1) + '%' : '-' }
</script>

<style scoped>
.sent-art__summary { display: flex; gap: 24px; margin-bottom: 16px; }
.sent-art__stat { display: flex; flex-direction: column; }
.sent-art__stat-val { font-size: 20px; font-weight: 600; color: #18181b; font-variant-numeric: tabular-nums; }
.sent-art__stat-label { font-size: 12px; color: #71717a; margin-top: 2px; }
.sent-art__stat--pos .sent-art__stat-val { color: #16a34a; }
.sent-art__stat--neg .sent-art__stat-val { color: #dc2626; }
.sent-art__bar { display: flex; height: 6px; border-radius: 3px; overflow: hidden; background: #f4f4f5; margin-bottom: 12px; }
.sent-art__bar-seg { height: 100%; transition: width 0.4s ease; }
.sent-art__bar-seg--pos { background: #18181b; }
.sent-art__bar-seg--neu { background: #a1a1aa; }
.sent-art__bar-seg--neg { background: #dc2626; }
.sent-art__alert { font-size: 12px; color: #dc2626; padding: 6px 12px; background: rgba(220,38,38,0.04); border-radius: 6px; margin-bottom: 12px; }
.sent-art__themes-label { font-size: 12px; color: #71717a; font-weight: 500; margin-bottom: 8px; }
.sent-art__theme { display: flex; align-items: center; gap: 12px; padding: 6px 0; border-bottom: 1px solid rgba(0,0,0,0.03); font-size: 13px; }
.sent-art__theme-name { flex: 1; font-weight: 500; }
.sent-art__theme-count { color: #71717a; font-variant-numeric: tabular-nums; }
.sent-art__theme-sent { font-size: 11px; padding: 2px 8px; border-radius: 999px; background: rgba(0,0,0,0.04); }
.sent-art__theme-sent--negative { background: rgba(220,38,38,0.06); color: #dc2626; }
.sent-art__theme-sent--positive { background: rgba(22,163,74,0.06); color: #16a34a; }
</style>
