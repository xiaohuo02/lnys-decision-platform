<template>
  <div class="rdp">
    <template v-if="rule">
      <div class="rdp__section">
        <h4 class="rdp__heading">关联商品</h4>
        <div class="rdp__group">
          <div class="rdp__label">前项</div>
          <div class="rdp__tags">
            <span v-for="(a, i) in toArr(rule.antecedent_names || rule.antecedents)" :key="i" class="rdp__tag rdp__tag--ant" :title="toArr(rule.antecedents)[i]">{{ a }}</span>
          </div>
        </div>
        <div class="rdp__group">
          <div class="rdp__label">后项</div>
          <div class="rdp__tags">
            <span v-for="(c, i) in toArr(rule.consequent_names || rule.consequents)" :key="i" class="rdp__tag rdp__tag--con" :title="toArr(rule.consequents)[i]">{{ c }}</span>
          </div>
        </div>
      </div>

      <div class="rdp__section">
        <h4 class="rdp__heading">统计指标</h4>
        <div class="rdp__row"><span>Support</span><span>{{ fmt(rule.support, 4) }}</span></div>
        <div class="rdp__row"><span>Confidence</span><span>{{ fmt(rule.confidence, 3) }}</span></div>
        <div class="rdp__row rdp__row--bold"><span>Lift</span><span :class="liftClass">{{ fmt(rule.lift, 2) }}</span></div>
        <div v-if="rule.conviction" class="rdp__row"><span>Conviction</span><span>{{ fmt(rule.conviction, 2) }}</span></div>
        <div v-if="rule.leverage" class="rdp__row"><span>Leverage</span><span>{{ fmt(rule.leverage, 4) }}</span></div>
      </div>

      <div class="rdp__section">
        <h4 class="rdp__heading">策略标签</h4>
        <div class="rdp__strategy-tags">
          <span v-if="rule.lift > 4" class="rdp__stag rdp__stag--strong">核心搭配</span>
          <span v-else-if="rule.lift > 2" class="rdp__stag rdp__stag--normal">推荐搭配</span>
          <span v-else class="rdp__stag">弱关联</span>
          <span v-if="rule.confidence > 0.8" class="rdp__stag rdp__stag--conf">高确定性</span>
        </div>
      </div>

      <div class="rdp__actions">
        <button class="rdp__btn" @click="$emit('ask-ai', `分析 ${toArr(rule.antecedents).join('+')} 和 ${toArr(rule.consequents).join('+')} 的搭配营销价值`)">
          让 AI 分析搭配价值
        </button>
        <button class="rdp__btn rdp__btn--secondary" @click="$emit('ask-ai', `${toArr(rule.antecedents)[0]} 库存状态`)">
          查看库存状态
        </button>
      </div>
    </template>

    <template v-else-if="node">
      <div class="rdp__section">
        <h4 class="rdp__heading">商品信息</h4>
        <div class="rdp__row"><span>SKU 编码</span><span class="rdp__mono">{{ node.id }}</span></div>
        <div class="rdp__row"><span>商品名称</span><span>{{ node.name || node.id }}</span></div>
        <div class="rdp__row"><span>出现频次</span><span>{{ node.frequency || 0 }}</span></div>
      </div>

      <div v-if="skuRules.length" class="rdp__section">
        <h4 class="rdp__heading">参与的关联规则 ({{ skuRules.length }})</h4>
        <div v-for="(r, i) in skuRules.slice(0, 8)" :key="i" class="rdp__mini-rule" @click="$emit('select-rule', r)">
          <div class="rdp__mini-items">
            <span v-for="(a, ai) in toArr(r.antecedent_names || r.antecedents)" :key="'a'+ai" class="rdp__tag rdp__tag--ant rdp__tag--sm">{{ a }}</span>
            <span class="rdp__arrow">→</span>
            <span v-for="(c, ci) in toArr(r.consequent_names || r.consequents)" :key="'c'+ci" class="rdp__tag rdp__tag--con rdp__tag--sm">{{ c }}</span>
          </div>
          <span class="rdp__mini-lift">{{ r.lift?.toFixed(2) }}</span>
        </div>
      </div>

      <div class="rdp__actions">
        <button class="rdp__btn" @click="$emit('ask-ai', `分析 ${node.id} 的关联商品和搭配推荐`)">
          让 AI 分析搭配
        </button>
        <button class="rdp__btn rdp__btn--secondary" @click="$emit('ask-agent', 'inventory_skill', `${node.id} 库存状态`)">
          查看库存状态
        </button>
      </div>
    </template>

    <div v-else class="rdp__empty">
      <p>点击图谱节点或规则表行查看详情</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  rule:     { type: Object, default: null },
  node:     { type: Object, default: null },
  skuRules: { type: Array,  default: () => [] },
})

defineEmits(['ask-ai', 'ask-agent', 'select-rule'])

function toArr(v) {
  if (Array.isArray(v)) return v
  if (typeof v === 'string') {
    if (v.startsWith('frozenset')) { const m = v.match(/\{(.+?)\}/); return m ? m[1].split(',').map(s => s.trim().replace(/'/g, '')) : [v] }
    return v.split(/[,+]/).map(s => s.trim()).filter(Boolean)
  }
  return v ? [String(v)] : []
}

function fmt(val, dec) {
  if (val == null) return '--'
  return Number(val).toFixed(dec)
}

const liftClass = computed(() => {
  if (!props.rule) return ''
  if (props.rule.lift > 3) return 'rdp__lift--strong'
  if (props.rule.lift > 1.5) return 'rdp__lift--mid'
  return ''
})
</script>

<style scoped>
.rdp { padding: var(--v2-space-4); display: flex; flex-direction: column; gap: var(--v2-space-4); height: 100%; overflow-y: auto; }
.rdp__section { display: flex; flex-direction: column; gap: var(--v2-space-2); }
.rdp__heading { font-size: var(--v2-text-xs); font-weight: 600; color: var(--v2-text-3); text-transform: uppercase; letter-spacing: .5px; padding-bottom: var(--v2-space-1); border-bottom: 1px solid var(--v2-border-2); margin: 0; }
.rdp__group { margin-top: var(--v2-space-1); }
.rdp__label { font-size: var(--v2-text-xs); color: var(--v2-text-4); margin-bottom: 2px; }
.rdp__tags { display: flex; flex-wrap: wrap; gap: 3px; }
.rdp__tag { font-size: var(--v2-text-xs); padding: 1px 8px; border-radius: var(--v2-radius-sm); font-weight: 500; white-space: nowrap; }
.rdp__tag--ant { background: var(--v2-brand-bg); color: var(--v2-brand-primary); }
.rdp__tag--con { background: var(--v2-success-bg); color: var(--v2-success-text); }
.rdp__tag--sm { font-size: 10px; padding: 0 5px; }
.rdp__row { display: flex; justify-content: space-between; padding: 3px 0; font-size: var(--v2-text-sm); }
.rdp__row > span:first-child { color: var(--v2-text-3); }
.rdp__row--bold > span:last-child { font-weight: 700; }
.rdp__mono { font-family: 'Geist Mono', monospace; }
.rdp__lift--strong { color: var(--v2-text-1); }
.rdp__lift--mid { color: var(--v2-text-2); }
.rdp__strategy-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.rdp__stag { font-size: 10px; padding: 1px 6px; border-radius: var(--v2-radius-sm); background: var(--v2-bg-sunken); color: var(--v2-text-3); }
.rdp__stag--strong { background: var(--v2-text-1); color: #fff; }
.rdp__stag--normal { background: var(--v2-text-3); color: #fff; }
.rdp__stag--conf { background: var(--v2-brand-bg); color: var(--v2-brand-primary); }
.rdp__mini-rule { display: flex; align-items: center; justify-content: space-between; gap: var(--v2-space-2); padding: 4px 0; cursor: pointer; border-bottom: 1px solid var(--v2-border-2); }
.rdp__mini-rule:hover { background: var(--v2-bg-sunken); margin: 0 calc(-1 * var(--v2-space-2)); padding: 4px var(--v2-space-2); border-radius: var(--v2-radius-sm); }
.rdp__mini-items { display: flex; flex-wrap: wrap; align-items: center; gap: 2px; }
.rdp__arrow { color: var(--v2-text-4); font-size: 10px; margin: 0 2px; }
.rdp__mini-lift { font-size: var(--v2-text-xs); font-weight: 600; color: var(--v2-text-2); flex-shrink: 0; }
.rdp__actions { display: flex; flex-direction: column; gap: var(--v2-space-2); margin-top: auto; padding-top: var(--v2-space-3); }
.rdp__btn { padding: 6px 12px; font-size: var(--v2-text-xs); font-weight: 500; border: 1px solid var(--v2-border-1); border-radius: var(--v2-radius-md); background: var(--v2-text-1); color: #fff; cursor: pointer; transition: opacity var(--v2-trans-fast); text-align: center; }
.rdp__btn:hover { opacity: .85; }
.rdp__btn--secondary { background: var(--v2-bg-card); color: var(--v2-text-1); }
.rdp__btn--secondary:hover { background: var(--v2-bg-sunken); }
.rdp__empty { display: flex; align-items: center; justify-content: center; height: 100%; color: var(--v2-text-4); font-size: var(--v2-text-sm); }
</style>
