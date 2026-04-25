<template>
  <div class="inv-art">
    <div class="inv-art__summary" v-if="data?.summary">
      <div class="inv-art__stat">
        <span class="inv-art__stat-val">{{ data.summary.total_skus }}</span>
        <span class="inv-art__stat-label">SKU</span>
      </div>
      <div class="inv-art__stat inv-art__stat--alert" v-if="data.summary.urgent_count > 0">
        <span class="inv-art__stat-val">{{ data.summary.urgent_count }}</span>
        <span class="inv-art__stat-label">Urgent</span>
      </div>
      <div class="inv-art__stat">
        <span class="inv-art__stat-val">{{ formatNum(data.summary.total_reorder_qty) }}</span>
        <span class="inv-art__stat-label">Reorder Qty</span>
      </div>
    </div>
    <div class="inv-art__table-wrap" v-if="rows.length">
      <table class="inv-art__table">
        <thead>
          <tr>
            <th @click="sortBy('sku_id')">SKU</th>
            <th @click="sortBy('current_stock')" class="num">Stock</th>
            <th @click="sortBy('safety_stock')" class="num">Safety</th>
            <th @click="sortBy('eoq')" class="num">EOQ</th>
            <th @click="sortBy('reorder_qty')" class="num">Reorder</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in sortedRows" :key="r.sku_id" :class="{ 'inv-art__row--urgent': r.urgent }">
            <td class="mono">{{ r.sku_id }}</td>
            <td class="num">{{ formatNum(r.current_stock) }}</td>
            <td class="num">{{ formatNum(r.safety_stock) }}</td>
            <td class="num">{{ formatNum(r.eoq) }}</td>
            <td class="num">{{ formatNum(r.reorder_qty) }}</td>
            <td><span class="inv-art__badge" :class="r.urgent ? 'inv-art__badge--urgent' : ''">{{ r.urgent ? 'URGENT' : 'OK' }}</span></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({ data: Object, metadata: Object })

const sortKey = ref('reorder_qty')
const sortDir = ref(-1)

const rows = computed(() => props.data?.recommendations || [])
const sortedRows = computed(() => {
  const arr = [...rows.value]
  arr.sort((a, b) => {
    const va = a[sortKey.value] ?? 0
    const vb = b[sortKey.value] ?? 0
    return (va - vb) * sortDir.value
  })
  return arr
})

function sortBy(key) {
  if (sortKey.value === key) sortDir.value *= -1
  else { sortKey.value = key; sortDir.value = -1 }
}

function formatNum(n) {
  if (n == null) return '-'
  return Number(n).toLocaleString()
}
</script>

<style scoped>
.inv-art__summary { display: flex; gap: 24px; margin-bottom: 16px; }
.inv-art__stat { display: flex; flex-direction: column; }
.inv-art__stat-val { font-size: 24px; font-weight: 600; color: #18181b; font-variant-numeric: tabular-nums; }
.inv-art__stat-label { font-size: 12px; color: #71717a; margin-top: 2px; }
.inv-art__stat--alert .inv-art__stat-val { color: #dc2626; }
.inv-art__table-wrap { overflow-x: auto; max-height: 340px; }
.inv-art__table { width: 100%; border-collapse: collapse; font-size: 13px; }
.inv-art__table th { text-align: left; padding: 8px 12px; border-bottom: 1px solid rgba(0,0,0,0.08); color: #71717a; font-weight: 500; cursor: pointer; user-select: none; white-space: nowrap; }
.inv-art__table th:hover { color: #18181b; }
.inv-art__table td { padding: 6px 12px; border-bottom: 1px solid rgba(0,0,0,0.03); }
.inv-art__table .num { text-align: right; font-variant-numeric: tabular-nums; }
.inv-art__table .mono { font-family: 'Geist Mono', monospace; font-size: 12px; }
.inv-art__row--urgent { background: rgba(220,38,38,0.03); }
.inv-art__badge { font-size: 11px; padding: 2px 8px; border-radius: 999px; background: rgba(0,0,0,0.04); }
.inv-art__badge--urgent { background: rgba(220,38,38,0.08); color: #dc2626; font-weight: 500; }
</style>
