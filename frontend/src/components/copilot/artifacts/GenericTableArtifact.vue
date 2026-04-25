<template>
  <div class="gen-art">
    <div v-if="isObject && !isArray" class="gen-art__kv">
      <div v-for="(val, key) in data" :key="key" class="gen-art__kv-row">
        <span class="gen-art__kv-key">{{ key }}</span>
        <span class="gen-art__kv-val" v-if="typeof val !== 'object'">{{ val }}</span>
        <pre class="gen-art__kv-val gen-art__kv-val--obj" v-else>{{ JSON.stringify(val, null, 2) }}</pre>
      </div>
    </div>
    <div v-else-if="isArray" class="gen-art__table-wrap">
      <table class="gen-art__table">
        <thead>
          <tr><th v-for="col in columns" :key="col">{{ col }}</th></tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in data" :key="i">
            <td v-for="col in columns" :key="col">{{ row[col] != null ? row[col] : '-' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <pre v-else class="gen-art__raw">{{ JSON.stringify(data, null, 2) }}</pre>
  </div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({ data: [Object, Array], metadata: Object })
const isArray = computed(() => Array.isArray(props.data))
const isObject = computed(() => props.data && typeof props.data === 'object')
const columns = computed(() => {
  if (!isArray.value || !props.data.length) return []
  return Object.keys(props.data[0])
})
</script>

<style scoped>
.gen-art__kv { display: flex; flex-direction: column; gap: 4px; }
.gen-art__kv-row { display: flex; gap: 16px; padding: 6px 0; border-bottom: 1px solid rgba(0,0,0,0.03); font-size: 13px; }
.gen-art__kv-key { color: #71717a; min-width: 140px; font-weight: 500; }
.gen-art__kv-val { color: #18181b; font-variant-numeric: tabular-nums; }
.gen-art__kv-val--obj { font-size: 12px; font-family: 'Geist Mono', monospace; margin: 0; white-space: pre-wrap; max-height: 200px; overflow: auto; }
.gen-art__table-wrap { overflow-x: auto; max-height: 340px; }
.gen-art__table { width: 100%; border-collapse: collapse; font-size: 13px; }
.gen-art__table th { text-align: left; padding: 8px 12px; border-bottom: 1px solid rgba(0,0,0,0.08); color: #71717a; font-weight: 500; white-space: nowrap; }
.gen-art__table td { padding: 6px 12px; border-bottom: 1px solid rgba(0,0,0,0.03); }
.gen-art__raw { font-size: 12px; font-family: 'Geist Mono', monospace; white-space: pre-wrap; max-height: 300px; overflow: auto; margin: 0; color: #52525b; }
</style>
