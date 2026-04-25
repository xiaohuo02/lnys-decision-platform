<template>
  <transition name="banner-slide">
    <div v-if="show" class="db" :class="`db--${level}`">
      <div class="db__content">
        <el-icon :size="16" class="db__icon"><WarningFilled /></el-icon>
        <div class="db__text">
          <span class="db__title">{{ title }}</span>
          <span v-if="desc" class="db__desc">{{ desc }}</span>
        </div>
      </div>
      <button v-if="closable" class="db__close" @click="show = false">&times;</button>
    </div>
  </transition>
</template>

<script setup>
import { ref } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'

defineProps({
  title:   { type: String, default: '部分数据可能不完整' },
  desc:    { type: String, default: '' },
  level:   { type: String, default: 'warning', validator: v => ['warning', 'error', 'info'].includes(v) },
  closable:{ type: Boolean, default: true },
})

const show = ref(true)
</script>

<style scoped>
.db {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--v2-space-2) var(--v2-space-4);
  border-radius: var(--v2-radius-md);
  margin-bottom: var(--v2-space-4);
  font-size: var(--v2-text-sm);
}
.db--warning { background: var(--v2-warning-bg); color: var(--v2-warning-text); border: 1px solid rgba(217,119,6,.15); }
.db--error   { background: var(--v2-error-bg);   color: var(--v2-error-text);   border: 1px solid rgba(220,38,38,.15); }
.db--info    { background: var(--v2-info-bg);    color: var(--v2-info-text);    border: 1px solid rgba(37,99,235,.15); }

.db__content { display: flex; align-items: center; gap: var(--v2-space-2); min-width: 0; }
.db__icon { flex-shrink: 0; }
.db__text { display: flex; align-items: baseline; gap: var(--v2-space-2); flex-wrap: wrap; }
.db__title { font-weight: var(--v2-font-medium); }
.db__desc { font-size: var(--v2-text-xs); opacity: .8; }

.db__close {
  border: none; background: transparent; cursor: pointer;
  font-size: 16px; color: inherit; opacity: .5;
  width: 24px; height: 24px; display: flex; align-items: center; justify-content: center;
  border-radius: var(--v2-radius-sm);
  transition: all var(--v2-trans-fast);
}
.db__close:hover { opacity: 1; background: rgba(0,0,0,.06); }

.banner-slide-enter-active { transition: all .2s ease; }
.banner-slide-leave-active { transition: all .15s ease; }
.banner-slide-enter-from, .banner-slide-leave-to { opacity: 0; max-height: 0; margin-bottom: 0; padding-top: 0; padding-bottom: 0; }
</style>
