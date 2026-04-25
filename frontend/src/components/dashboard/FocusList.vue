<template>
  <div class="focus" ref="rootRef">
    <div class="focus__hd">
      <span class="focus__title">需要关注</span>
      <span v-if="todoCount > 0" class="focus__count">{{ todoCount }} 项待办</span>
    </div>
    <div class="focus__list">
      <div
        v-for="(item, i) in items" :key="i"
        class="task-card" :class="'task-card--' + item.level"
      >
        <div class="task-card__hd">
          <span v-if="item.priority !== 'ok'" class="task-card__prio" :class="'task-card__prio--' + item.priority">{{ item.priority }}</span>
          <span class="task-card__title">{{ item.title }}</span>
        </div>
        <p v-if="item.impact" class="task-card__impact">{{ item.impact }}</p>
        <div v-if="item.action" class="task-card__actions">
          <button class="task-card__btn task-card__btn--primary" @click="handleNavigate(item)">
            {{ item.action }}
            <ChevronRight :size="12" />
          </button>
          <button v-if="item.aiQ" class="task-card__btn task-card__btn--ghost" @click="$emit('ask-ai', { question: item.aiQ })">
            AI 诊断
          </button>
        </div>
      </div>
    </div>
    <div class="focus__insight">
      <div class="focus__insight-hd">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
        </svg>
        <span>AI 洞察</span>
        <span class="focus__ai-badge">模型自动生成</span>
      </div>
      <p class="focus__insight-text">{{ insightText }}</p>
      <router-link to="/analyze" class="focus__insight-link">进入分析工作台 →</router-link>
    </div>
  </div>
</template>

<script setup>
import { ref, defineExpose } from 'vue'
import { useRouter } from 'vue-router'
import { ChevronRight } from 'lucide-vue-next'
import { useIntentStore } from '@/stores/useIntentStore'

defineProps({
  items: { type: Array, required: true },
  todoCount: { type: Number, default: 0 },
  insightText: { type: String, default: '' },
})
defineEmits(['ask-ai'])

const router = useRouter()
const intentStore = useIntentStore()

const rootRef = ref(null)

function flash() {
  const el = rootRef.value
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  el.classList.add('focus--flash')
  setTimeout(() => el.classList.remove('focus--flash'), 1200)
}

/**
 * C-α: 点击跳转前 dispatch intent，让目标页知道"为什么来"
 * item 支持可选 { intent, intentPayload } 字段；若缺省则按 link 路径推断
 */
function handleNavigate(item) {
  // 显式 intent 优先
  const intentType = item.intent || _inferIntent(item.link)
  if (intentType) {
    intentStore.dispatch(intentType, item.intentPayload || {}, 'dashboard')
  }
  router.push(item.link)
}

function _inferIntent(link) {
  if (!link) return null
  // 按路径推断，保持跟 task 语义一致
  if (link.startsWith('/console/security')) return 'review_high_risk'
  if (link === '/customer' || link.startsWith('/customer?'))  return 'view_churn_customers'
  if (link === '/inventory' || link.startsWith('/inventory?')) return 'replenish_sku'
  if (link.startsWith('/sentiment/analyze')) return 'analyze_negative'
  return null
}

defineExpose({ flash })
</script>

<style scoped>
.focus {
  display: flex; flex-direction: column; gap: 8px;
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-card); background: var(--v2-bg-card);
  padding: 10px 12px; min-height: 0; overflow-y: auto;
  transition: box-shadow 0.3s;
}
.focus--flash { box-shadow: 0 0 0 3px color-mix(in srgb, var(--v2-error, #dc2626) 40%, transparent); }
.focus__hd { display: flex; align-items: center; justify-content: space-between; margin-bottom: 2px; }
.focus__title { font-family: var(--v2-font-mono); font-size: 11px; letter-spacing: 0.03em; color: var(--v2-text-3); text-transform: uppercase; }
.focus__count {
  font-family: var(--v2-font-mono); font-size: 10px;
  padding: 2px 8px; border-radius: var(--v2-radius-pill);
  color: var(--v2-error-text, #991b1b); background: var(--v2-error-bg, #fee2e2);
}
.focus__list { display: flex; flex-direction: column; gap: 6px; }

.task-card {
  display: flex; flex-direction: column; gap: 0;
  padding: 0;
  border-radius: var(--v2-radius-md);
  border: var(--v2-border-width) solid var(--v2-border-2);
  background: var(--v2-bg-card);
  overflow: hidden;
  transition: border-color var(--v2-trans-fast), background var(--v2-trans-fast);
}
.task-card__hd { display: flex; align-items: center; gap: 8px; padding: 10px 12px 6px; }
.task-card__prio {
  font-family: var(--v2-font-mono); font-size: 10px; font-weight: 700;
  padding: 2px 6px; border-radius: 3px; flex-shrink: 0;
}
.task-card__prio--P0 { color: #fff; background: var(--v2-error, #dc2626); }
.task-card__prio--P1 { color: var(--v2-warning-text, #92400e); background: var(--v2-warning-bg, #fef3c7); }
.task-card__prio--P2 { color: var(--v2-text-2); background: var(--v2-bg-hover); }
.task-card__title {
  flex: 1; min-width: 0;
  font-size: 13px; font-weight: var(--v2-font-medium); color: var(--v2-text-1);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.task-card__impact { margin: 0; padding: 0 12px 8px; font-size: 11px; line-height: 1.5; color: var(--v2-text-4); }
.task-card__actions {
  display: flex; gap: 6px;
  padding: 8px 12px;
  border-top: var(--v2-border-width) solid var(--v2-border-2);
  background: color-mix(in srgb, var(--v2-bg-hover) 50%, transparent);
}
.task-card__btn {
  display: inline-flex; align-items: center; gap: 3px;
  padding: 4px 10px;
  font-family: inherit; font-size: 11px; font-weight: var(--v2-font-medium);
  border-radius: var(--v2-radius-btn); cursor: pointer;
  transition: all var(--v2-trans-fast); border: none;
}
.task-card__btn--primary { color: var(--v2-bg-page); background: var(--v2-text-1); }
.task-card__btn--primary:hover { background: color-mix(in srgb, var(--v2-text-1) 85%, #000); }
.task-card__btn--ghost { color: var(--v2-text-2); background: transparent; border: 1px solid var(--v2-border-1); }
.task-card__btn--ghost:hover { color: var(--v2-text-1); background: var(--v2-bg-hover); }

.task-card--critical {
  border-color: color-mix(in srgb, var(--v2-error, #dc2626) 35%, transparent);
  border-left: 3px solid var(--v2-error, #dc2626);
  background: color-mix(in srgb, var(--v2-error, #dc2626) 5%, var(--v2-bg-card));
}
.task-card--critical .task-card__btn--primary { background: var(--v2-error, #dc2626); }
.task-card--critical .task-card__btn--primary:hover { background: color-mix(in srgb, var(--v2-error, #dc2626) 85%, #000); }
.task-card--warning {
  border-color: color-mix(in srgb, var(--v2-warning, #f59e0b) 30%, transparent);
  border-left: 3px solid var(--v2-warning, #f59e0b);
}
.task-card--info { border-color: var(--v2-border-2); }
.task-card--ok {
  border-color: color-mix(in srgb, var(--v2-success, #22c55e) 25%, transparent);
  background: color-mix(in srgb, var(--v2-success, #22c55e) 4%, var(--v2-bg-card));
}
.task-card--ok .task-card__title { color: var(--v2-text-2); font-weight: var(--v2-font-medium); }

.focus__insight {
  margin-top: auto; padding: 10px;
  border-radius: var(--v2-radius-md);
  background: linear-gradient(135deg, color-mix(in srgb, var(--v2-text-1) 4%, transparent), transparent 70%);
  border: var(--v2-border-width) solid var(--v2-border-2);
}
.focus__insight-hd { display: flex; align-items: center; gap: 6px; font-family: var(--v2-font-mono); font-size: 10px; letter-spacing: 0.04em; color: var(--v2-text-2); text-transform: uppercase; margin-bottom: 4px; }
.focus__insight-text { font-size: 12px; line-height: 1.6; color: var(--v2-text-2); margin: 0; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.focus__insight-link { display: inline-block; margin-top: 6px; font-size: 12px; font-weight: var(--v2-font-medium); color: var(--v2-text-1); text-decoration: none; }
.focus__insight-link:hover { text-decoration: underline; }
.focus__ai-badge {
  font-family: var(--v2-font-mono); font-size: 9px; letter-spacing: 0.03em;
  padding: 1px 6px; border-radius: var(--v2-radius-pill);
  color: var(--v2-text-4); background: var(--v2-bg-hover);
  margin-left: auto; white-space: nowrap;
}
</style>
