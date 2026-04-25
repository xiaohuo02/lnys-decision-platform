<template>
  <div class="sr">
    <div class="sr__header">
      <h3 class="sr__title">搭配推荐</h3>
      <span v-if="baseSku" class="sr__base">{{ baseSku }}</span>
    </div>

    <div v-if="loading" class="sr__loading">
      <span v-for="i in 3" :key="i" class="sr__skeleton" />
    </div>

    <div v-else-if="error" class="sr__error" @click="$emit('retry')">
      {{ error }} <span class="sr__retry">点击重试</span>
    </div>

    <div v-else-if="items.length" class="sr__grid">
      <div
        v-for="item in items"
        :key="item.sku_code || item.consequents"
        class="sr__card"
      >
        <div class="sr__card-head">
          <span class="sr__sku">{{ item.sku_code || item.consequents }}</span>
          <span v-if="item.lift" class="sr__lift">Lift {{ item.lift?.toFixed?.(2) ?? item.lift }}</span>
        </div>
        <div class="sr__name">{{ item.sku_name || item.consequent_names || '--' }}</div>
        <div class="sr__metrics">
          <span v-if="item.confidence">Conf <strong>{{ (item.confidence * 100).toFixed(0) }}%</strong></span>
          <span v-if="item.support">Sup <strong>{{ item.support?.toFixed?.(4) ?? item.support }}</strong></span>
        </div>
        <div class="sr__source">
          <span class="sr__source-badge">购物篮共现</span>
        </div>
        <div class="sr__card-actions">
          <button class="sr__action" @click="$emit('ask-ai', `分析 ${baseSku} 和 ${item.sku_code || item.consequents} 的搭配营销价值`)">AI 分析</button>
          <button class="sr__action sr__action--sec" @click="$emit('ask-agent', 'inventory_skill', `${item.sku_code || item.consequents} 库存状态`)">查库存</button>
        </div>
      </div>
    </div>

    <div v-else class="sr__empty">
      {{ baseSku ? '该商品暂无推荐搭配' : '点击图谱节点或规则表行查看推荐' }}
    </div>
  </div>
</template>

<script setup>
defineProps({
  baseSku: { type: String, default: '' },
  items:   { type: Array,  default: () => [] },
  loading: { type: Boolean, default: false },
  error:   { type: String,  default: '' },
})

defineEmits(['ask-ai', 'ask-agent', 'retry'])
</script>

<style scoped>
.sr { display: flex; flex-direction: column; gap: var(--v2-space-3); }
.sr__header { display: flex; align-items: baseline; gap: var(--v2-space-2); }
.sr__title { font-size: var(--v2-text-sm); font-weight: 600; color: var(--v2-text-1); margin: 0; }
.sr__base { font-size: var(--v2-text-xs); font-family: 'Geist Mono', monospace; color: var(--v2-brand-primary); background: var(--v2-brand-bg); padding: 0 6px; border-radius: var(--v2-radius-sm); }
.sr__grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: var(--v2-space-3); }
.sr__card { padding: var(--v2-space-3); background: var(--v2-bg-sunken); border-radius: var(--v2-radius-lg); border: 1px solid var(--v2-border-2); transition: border-color var(--v2-trans-fast); }
.sr__card:hover { border-color: var(--v2-border-1); }
.sr__card-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.sr__sku { font-size: var(--v2-text-xs); font-weight: 600; font-family: 'Geist Mono', monospace; color: var(--v2-brand-primary); }
.sr__lift { font-size: 10px; color: var(--v2-text-3); }
.sr__name { font-size: var(--v2-text-sm); color: var(--v2-text-1); margin-bottom: 6px; line-height: 1.3; }
.sr__metrics { display: flex; gap: var(--v2-space-3); font-size: var(--v2-text-xs); color: var(--v2-text-3); margin-bottom: 6px; }
.sr__source { padding-top: 6px; border-top: 1px solid var(--v2-border-2); }
.sr__source-badge { font-size: 10px; padding: 1px 5px; border-radius: var(--v2-radius-sm); background: var(--v2-bg-card); color: var(--v2-text-3); }
.sr__card-actions { display: flex; gap: var(--v2-space-1); margin-top: var(--v2-space-2); }
.sr__action { flex: 1; padding: 4px 0; font-size: 10px; font-weight: 500; border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-sm); background: var(--v2-text-1); color: #fff; cursor: pointer; text-align: center; transition: opacity var(--v2-trans-fast); }
.sr__action:hover { opacity: .85; }
.sr__action--sec { background: var(--v2-bg-card); color: var(--v2-text-1); }
.sr__loading { display: flex; gap: var(--v2-space-3); }
.sr__skeleton { width: 200px; height: 100px; background: var(--v2-bg-sunken); border-radius: var(--v2-radius-lg); animation: sr-pulse 1.2s ease-in-out infinite; }
.sr__error { font-size: var(--v2-text-xs); color: var(--v2-error); cursor: pointer; }
.sr__retry { text-decoration: underline; margin-left: 4px; }
.sr__empty { font-size: var(--v2-text-xs); color: var(--v2-text-4); padding: var(--v2-space-4) 0; text-align: center; }
@keyframes sr-pulse { 0%,100% { opacity: .5; } 50% { opacity: .3; } }
</style>
