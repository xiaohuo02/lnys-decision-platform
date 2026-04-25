<template>
  <div class="skd" v-if="sku">
    <div class="skd__header">
      <div class="skd__badge" :class="`skd__badge--${sku.alert_level || 'normal'}`">
        {{ sku.alert_level || 'healthy' }}
      </div>
      <h3 class="skd__title">{{ sku.sku_code }}</h3>
      <p class="skd__name">{{ sku.sku_name || '-' }}</p>
    </div>

    <div class="skd__sections">
      <!-- Stock Section -->
      <section class="skd__sec">
        <h4 class="skd__sec-title">库存状态</h4>
        <dl class="skd__dl">
          <div class="skd__dl-row">
            <dt>当前库存</dt>
            <dd :class="{ 'skd__val--danger': sku.current_stock < sku.safety_stock }">
              {{ sku.current_stock }}
            </dd>
          </div>
          <div class="skd__dl-row">
            <dt>安全库存</dt>
            <dd>{{ sku.safety_stock }}</dd>
          </div>
          <div class="skd__dl-row">
            <dt>建议补货</dt>
            <dd class="skd__val--primary">{{ sku.reorder_qty ?? '-' }}</dd>
          </div>
          <div class="skd__dl-row">
            <dt>EOQ</dt>
            <dd>{{ sku.eoq ?? '-' }}</dd>
          </div>
          <div class="skd__dl-row">
            <dt>紧急度</dt>
            <dd>{{ sku.urgency_days != null ? sku.urgency_days + ' 天' : '-' }}</dd>
          </div>
        </dl>
        <!-- Sparkline -->
        <div class="skd__spark-wrap" v-if="sku.stock_history_7d?.length">
          <span class="skd__spark-label">7天趋势</span>
          <StockSparkline
            :data="sku.stock_history_7d"
            :width="160"
            :height="32"
            :color="sparkColor"
          />
        </div>
      </section>

      <!-- Classification -->
      <section class="skd__sec" v-if="sku.abc_class || sku.matrix_cell">
        <h4 class="skd__sec-title">ABC-XYZ 分类</h4>
        <dl class="skd__dl">
          <div class="skd__dl-row" v-if="sku.matrix_cell">
            <dt>象限</dt>
            <dd class="skd__val--bold">{{ sku.matrix_cell }}</dd>
          </div>
          <div class="skd__dl-row" v-if="sku.abc_class">
            <dt>ABC</dt>
            <dd>{{ sku.abc_class }}</dd>
          </div>
          <div class="skd__dl-row" v-if="sku.xyz_class">
            <dt>XYZ</dt>
            <dd>{{ sku.xyz_class }}</dd>
          </div>
          <div class="skd__dl-row" v-if="sku.strategy">
            <dt>策略</dt>
            <dd>{{ sku.strategy }}</dd>
          </div>
          <div class="skd__dl-row" v-if="sku.sales_contribution_pct != null">
            <dt>销售占比</dt>
            <dd>{{ sku.sales_contribution_pct.toFixed(1) }}%</dd>
          </div>
        </dl>
      </section>

      <!-- Store -->
      <section class="skd__sec" v-if="sku.store_id">
        <h4 class="skd__sec-title">门店信息</h4>
        <dl class="skd__dl">
          <div class="skd__dl-row">
            <dt>门店</dt>
            <dd>{{ sku.store_id }}</dd>
          </div>
        </dl>
      </section>
    </div>

    <!-- AI Quick Actions -->
    <div class="skd__actions">
      <button class="skd__action-btn" @click="$emit('askAi', `${sku.sku_code} 需要补货吗？`)">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3M12 17h.01"/></svg>
        AI 分析
      </button>
      <button class="skd__action-btn" @click="$emit('askAi', `预测 ${sku.sku_code} 下月需求`)">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
        需求预测
      </button>
    </div>
  </div>

  <div class="skd__empty" v-else>
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1"><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>
    <p>点击表格行查看 SKU 详情</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import StockSparkline from './StockSparkline.vue'

const props = defineProps({
  sku: { type: Object, default: null },
})

defineEmits(['askAi'])

const sparkColor = computed(() => {
  if (!props.sku) return '#18181b'
  if (props.sku.alert_level === 'critical') return '#ef4444'
  if (props.sku.alert_level === 'warning') return '#f59e0b'
  return '#18181b'
})
</script>

<style scoped>
.skd { display: flex; flex-direction: column; gap: 0; height: 100%; }

.skd__header {
  padding: 16px;
  border-bottom: 1px solid rgba(0,0,0,0.06);
}
.skd__badge {
  display: inline-block;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 2px 8px;
  border-radius: 999px;
  margin-bottom: 8px;
}
.skd__badge--critical { background: rgba(239,68,68,0.1); color: #dc2626; }
.skd__badge--warning { background: rgba(245,158,11,0.1); color: #d97706; }
.skd__badge--normal, .skd__badge--healthy { background: rgba(0,0,0,0.04); color: #71717a; }

.skd__title {
  font-size: 16px;
  font-weight: 600;
  color: #18181b;
  margin: 0;
  font-variant-numeric: tabular-nums;
}
.skd__name {
  font-size: 13px;
  color: #71717a;
  margin: 2px 0 0;
}

.skd__sections {
  flex: 1;
  overflow-y: auto;
  padding: 0;
}

.skd__sec {
  padding: 14px 16px;
  border-bottom: 1px solid rgba(0,0,0,0.04);
}
.skd__sec-title {
  font-size: 11px;
  font-weight: 600;
  color: #a1a1aa;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin: 0 0 10px;
}

.skd__dl { display: flex; flex-direction: column; gap: 6px; }
.skd__dl-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}
.skd__dl-row dt { color: #71717a; }
.skd__dl-row dd { margin: 0; color: #18181b; font-weight: 500; font-variant-numeric: tabular-nums; }

.skd__val--danger { color: #dc2626 !important; font-weight: 600 !important; }
.skd__val--primary { color: #18181b !important; font-weight: 700 !important; }
.skd__val--bold { font-weight: 700 !important; font-size: 15px; }

.skd__spark-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid rgba(0,0,0,0.04);
}
.skd__spark-label {
  font-size: 11px;
  color: #a1a1aa;
  white-space: nowrap;
}

.skd__actions {
  padding: 12px 16px;
  border-top: 1px solid rgba(0,0,0,0.06);
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}
.skd__action-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 12px;
  border: 1px solid rgba(0,0,0,0.08);
  border-radius: 8px;
  background: #fff;
  font-size: 12px;
  font-weight: 500;
  color: #18181b;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
}
.skd__action-btn:hover { background: #f4f4f5; border-color: rgba(0,0,0,0.15); }

.skd__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  height: 100%;
  color: #a1a1aa;
}
.skd__empty p { font-size: 13px; margin: 0; }
</style>
