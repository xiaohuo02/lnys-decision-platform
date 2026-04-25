<template>
  <div class="kb-legacy">
    <div class="kb-legacy__card">
      <div class="kb-legacy__icon">
        <ArrowRightCircle :size="44" :stroke-width="1.5" />
      </div>
      <h3 class="kb-legacy__title">FAQ 知识库已合并入「知识库中台」</h3>
      <p class="kb-legacy__desc">
        旧版 16 条企业 FAQ 已迁移到新「知识库中台 · 企业客服 FAQ」域。
        新版提供多知识库管理、文档版本/分块、统一检索（hybrid/vector/keyword）、用户反馈聚合等完整能力，
        旧 FAQ 表（faq_documents）写入接口仍保留以兼容业务前台。
      </p>

      <div class="kb-legacy__actions">
        <V2Button variant="primary" @click="goNew('libs')">
          <FolderOpen :size="14" /> 前往知识库中台
        </V2Button>
        <V2Button variant="secondary" @click="goNew('feedback')">
          <MessageSquare :size="14" /> 查看用户反馈
        </V2Button>
      </div>

      <div class="kb-legacy__hint">
        <code>/console/knowledge-v2</code> · 推荐书签
      </div>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { ArrowRightCircle, FolderOpen, MessageSquare } from 'lucide-vue-next'
import V2Button from '@/components/v2/V2Button.vue'

const router = useRouter()

function goNew(tab = 'libs') {
  router.push({ path: '/console/knowledge-v2', query: { tab } })
}
</script>

<style scoped>
.kb-legacy {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--v2-space-12) var(--v2-space-4);
}

.kb-legacy__card {
  width: min(560px, 100%);
  background: var(--v2-bg-2);
  border: 1px solid var(--v2-border-1);
  border-radius: var(--v2-radius-lg);
  padding: var(--v2-space-8);
  text-align: center;
}

.kb-legacy__icon {
  display: inline-flex;
  width: 72px;
  height: 72px;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--v2-bg-3);
  color: var(--v2-primary);
  margin-bottom: var(--v2-space-4);
}

.kb-legacy__title {
  font-size: var(--v2-text-lg);
  font-weight: var(--v2-font-semibold);
  color: var(--v2-text-1);
  margin: 0 0 var(--v2-space-3);
}

.kb-legacy__desc {
  font-size: var(--v2-text-sm);
  line-height: 1.7;
  color: var(--v2-text-3);
  margin: 0 0 var(--v2-space-6);
}

.kb-legacy__actions {
  display: flex;
  gap: var(--v2-space-3);
  justify-content: center;
  margin-bottom: var(--v2-space-5);
}

.kb-legacy__hint {
  font-size: var(--v2-text-xs);
  color: var(--v2-text-4);
}

.kb-legacy__hint code {
  font-family: var(--v2-font-mono, monospace);
  background: var(--v2-bg-3);
  padding: 1px 6px;
  border-radius: var(--v2-radius-sm);
  color: var(--v2-text-2);
}
</style>
