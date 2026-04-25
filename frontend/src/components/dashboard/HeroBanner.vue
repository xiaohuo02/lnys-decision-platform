<template>
  <section class="hero">
    <div class="hero__bar">
      <div class="hero__bar-left">
        <h1 class="hero__title">业务总览</h1>
        <span class="hero__time">{{ currentTime }}</span>
      </div>
      <div class="hero__bar-right">
        <button class="hero__btn" :disabled="loading" @click="$emit('refresh')">
          <RefreshCw :size="14" :class="{ 'is-spin': loading }" /> 刷新
        </button>
        <button class="hero__btn" :title="isPresenting ? '退出演示' : '演示模式'" @click="$emit('toggle-present')">
          <component :is="isPresenting ? Minimize2 : Maximize2" :size="14" />
          {{ isPresenting ? '退出演示' : '演示模式' }}
        </button>
        <button class="hero__toggle" :class="{ 'hero__toggle--active': showRight }" @click="$emit('toggle-right')" title="AI 面板">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="3" y="3" width="18" height="18" rx="3" />
            <line x1="15" y1="3" x2="15" y2="21" />
          </svg>
        </button>
      </div>
    </div>
    <div class="hero__content">
      <div class="hero__left">
        <div class="hero__greeting">
          <span class="hero__emoji">{{ greetingEmoji }}</span>
          <span class="hero__hello">{{ greeting }}{{ userName ? '，' + userName : '' }}</span>
          <span class="hero__chips">
            <span class="chip"><Calendar :size="11" /> {{ dateChip }}</span>
            <span class="chip" :class="'chip--' + businessStatus.level">
              <span class="chip-dot" :class="'chip-dot--' + businessStatus.level"></span>
              {{ businessStatus.label }}
            </span>
          </span>
        </div>
        <p class="hero__narrative">{{ narrative }}</p>
      </div>
      <div class="hero__right">
        <!-- C-γ.1: 一键委托 AI 做完整经营诊断 -->
        <button
          class="hero__delegate"
          :disabled="delegating"
          title="触发 business_overview workflow，可切换到其他页面查看进度（任务栏在右上角）"
          @click="$emit('delegate-ai')"
        >
          <Sparkles :size="13" :class="{ 'is-spin': delegating }" />
          <span>{{ delegating ? '委派中…' : '让 AI 生成诊断' }}</span>
        </button>
        <button class="hero__cta" :class="{ 'hero__cta--alert': todoCount > 0 }" @click="$emit('cta-click')">
          <span v-if="todoCount > 0">{{ todoCount }} 项待办需处理</span>
          <span v-else>今日一切正常</span>
          <ChevronRight :size="14" />
        </button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { RefreshCw, Maximize2, Minimize2, Calendar, ChevronRight, Sparkles } from 'lucide-vue-next'

const props = defineProps({
  userName: { type: String, default: '' },
  currentTime: { type: String, default: '' },
  now: { type: Date, required: true },
  narrative: { type: String, default: '' },
  todoCount: { type: Number, default: 0 },
  loading: { type: Boolean, default: false },
  isPresenting: { type: Boolean, default: false },
  showRight: { type: Boolean, default: false },
  delegating: { type: Boolean, default: false },
})
defineEmits(['refresh', 'toggle-present', 'toggle-right', 'cta-click', 'delegate-ai'])

const greeting = computed(() => {
  const h = props.now.getHours()
  if (h < 6) return '凌晨好'
  if (h < 11) return '早上好'
  if (h < 13) return '中午好'
  if (h < 18) return '下午好'
  if (h < 22) return '晚上好'
  return '夜深了'
})

const greetingEmoji = computed(() => {
  const h = props.now.getHours()
  if (h < 6) return '🌙'
  if (h < 11) return '☀️'
  if (h < 13) return '🌤'
  if (h < 18) return '🌞'
  if (h < 22) return '🌆'
  return '🌃'
})

const dateChip = computed(() => {
  const d = props.now
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
})

const businessStatus = computed(() => {
  const minutes = props.now.getHours() * 60 + props.now.getMinutes()
  if (minutes >= 9 * 60 && minutes < 22 * 60) {
    const remain = 22 * 60 - minutes
    if (remain <= 120) return { level: 'warn', label: `距打烊 ${Math.round((remain / 60) * 10) / 10} 小时` }
    return { level: 'ok', label: '营业中' }
  }
  return { level: 'idle', label: '非营业时段' }
})
</script>

<style scoped>
.hero {
  display: flex; flex-direction: column; gap: 6px;
  padding: 10px 14px;
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: var(--v2-radius-card);
  background: linear-gradient(115deg, var(--v2-bg-card) 60%, var(--v2-bg-hover) 100%);
}
.hero__bar { display: flex; justify-content: space-between; align-items: center; }
.hero__bar-left { display: flex; align-items: baseline; gap: 10px; }
.hero__bar-right { display: flex; align-items: center; gap: 8px; }
.hero__title { font-size: var(--v2-text-xl); font-weight: var(--v2-font-semibold); color: var(--v2-text-1); margin: 0; letter-spacing: -0.02em; }
.hero__time { font-family: var(--v2-font-mono); font-size: var(--v2-text-xs); color: var(--v2-text-4); }

.hero__btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 14px; border: var(--v2-border-width) solid var(--v2-border-1);
  border-radius: var(--v2-radius-btn); background: var(--v2-bg-card);
  color: var(--v2-text-2); font-size: var(--v2-text-sm); cursor: pointer;
  transition: var(--v2-trans-fast);
}
.hero__btn:hover { background: var(--v2-bg-hover); color: var(--v2-text-1); }
.hero__btn:disabled { opacity: 0.5; cursor: not-allowed; }
.hero__toggle {
  display: flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; border: 1px solid var(--v2-border-1);
  border-radius: var(--v2-radius-md); background: var(--v2-bg-card);
  color: var(--v2-text-3); cursor: pointer; transition: all var(--v2-trans-fast);
}
.hero__toggle:hover { color: var(--v2-text-1); }
.hero__toggle--active { background: var(--v2-text-1); color: #fff; border-color: var(--v2-text-1); }

.hero__content { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.hero__left { min-width: 0; display: flex; flex-direction: column; gap: 2px; flex: 1; }
.hero__greeting { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.hero__emoji { font-size: 16px; line-height: 1; }
.hero__hello { font-size: 14px; font-weight: var(--v2-font-semibold); color: var(--v2-text-1); letter-spacing: -0.01em; }
.hero__chips { display: inline-flex; gap: 6px; align-items: center; margin-left: 4px; }
.hero__narrative { margin: 0; font-size: 12px; line-height: 1.5; color: var(--v2-text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.chip {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 4px 10px;
  font-family: var(--v2-font-mono); font-size: 11px;
  color: var(--v2-text-3); background: var(--v2-bg-hover);
  border-radius: var(--v2-radius-pill); white-space: nowrap;
}
.chip--ok   { color: var(--v2-success-text, #15803d); background: var(--v2-success-bg, #dcfce7); }
.chip--warn { color: var(--v2-warning-text, #92400e); background: var(--v2-warning-bg, #fef3c7); }
.chip--idle { color: var(--v2-text-4); }
.chip-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
.chip-dot--ok   { background: var(--v2-success, #22c55e); }
.chip-dot--warn { background: var(--v2-warning, #f59e0b); }
.chip-dot--idle { background: var(--v2-text-4); }

.hero__right { display: flex; gap: 8px; align-items: center; }

/* C-γ.1: 委托 AI 按钮 */
.hero__delegate {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 7px 13px;
  font-family: inherit; font-size: 12px; font-weight: var(--v2-font-medium);
  color: var(--v2-text-1);
  background: var(--v2-bg-card);
  border: 1px solid var(--v2-border-1);
  border-radius: var(--v2-radius-btn);
  cursor: pointer;
  transition: all var(--v2-trans-fast);
  white-space: nowrap;
}
.hero__delegate:hover { border-color: var(--v2-text-1); background: var(--v2-bg-hover); }
.hero__delegate:disabled { opacity: 0.55; cursor: not-allowed; }
.hero__delegate .is-spin { animation: spin 0.8s linear infinite; }

.hero__cta {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 14px;
  font-family: inherit; font-size: 13px; font-weight: var(--v2-font-medium);
  color: var(--v2-bg-page); background: var(--v2-text-1);
  border: none; border-radius: var(--v2-radius-btn);
  cursor: pointer; transition: all var(--v2-trans-fast);
  white-space: nowrap;
}
.hero__cta:hover { transform: translateY(-1px); box-shadow: 0 4px 10px -2px rgba(0,0,0,0.15); }
.hero__cta--alert {
  background: var(--v2-error, #dc2626); color: #fff;
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--v2-error, #dc2626) 15%, transparent);
}
.hero__cta--alert:hover { background: color-mix(in srgb, var(--v2-error, #dc2626) 90%, #000); }

.is-spin { animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 768px) {
  .hero { padding: 12px 14px; gap: 8px; }
  .hero__bar { flex-wrap: wrap; gap: 8px; }
  .hero__content { flex-direction: column; align-items: stretch; }
  .hero__narrative { white-space: normal; }
  .hero__chips { margin-left: 0; margin-top: 4px; }
}
</style>
