<template>
  <div class="bc">
    <div class="bc__layout">
      <!-- ── Left: Skill Panel (toggleable) ── -->
      <Transition name="bc-slide">
        <aside v-if="showSkills" class="bc__skills">
          <div class="bc__skills-hd">
            <span class="bc__skills-title">AI 技能</span>
            <button class="bc__skills-close" @click="showSkills = false">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
          <div class="bc__skill-list">
            <button
              v-for="skill in skills" :key="skill.id"
              class="bc__skill-card"
              @click="askSkill(skill)"
            >
              <span class="bc__skill-emoji">{{ skill.emoji }}</span>
              <div class="bc__skill-info">
                <span class="bc__skill-name">{{ skill.name }}</span>
                <span class="bc__skill-desc">{{ skill.desc }}</span>
              </div>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="bc__skill-arrow"><polyline points="9 18 15 12 9 6"/></svg>
            </button>
          </div>

          <div class="bc__quick-section">
            <span class="bc__quick-label">快捷操作</span>
            <button class="bc__quick-btn" @click="$router.push('/analyze')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              新建经营分析
            </button>
            <button class="bc__quick-btn" @click="$router.push('/report')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              生成报告
            </button>
          </div>
        </aside>
      </Transition>

      <!-- ── Main: Chat Panel ── -->
      <div class="bc__main">
        <div class="bc__top-bar">
          <button class="bc__bar-btn" :class="{ 'bc__bar-btn--active': showSkills }" @click="showSkills = !showSkills" title="技能面板">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
          </button>
          <span class="bc__top-title">AI 运营助手</span>
          <span class="bc__top-desc">客户洞察 · 销售预测 · 舆情分析 · 知识库</span>
        </div>
        <UnifiedCopilotPanel ref="copilotRef" mode="biz" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import UnifiedCopilotPanel from '@/components/copilot/UnifiedCopilotPanel.vue'

const route = useRoute()
const copilotRef = ref(null)
const showSkills = ref(false)

const skills = [
  { id: 'customer', name: '客群洞察', desc: 'RFM · CLV · 流失分析', emoji: '👥', prompt: '请分析当前客户群体概况' },
  { id: 'forecast', name: '销售预测', desc: '多模型融合预测', emoji: '📈', prompt: '请预测未来 7 天的销售趋势' },
  { id: 'sentiment', name: '舆情分析', desc: '情感识别 · 话题发现', emoji: '💬', prompt: '请分析最近的舆情状况' },
  { id: 'inventory', name: '库存优化', desc: 'ABC-XYZ · 补货策略', emoji: '📦', prompt: '当前有库存预警或补货建议吗？' },
  { id: 'association', name: '关联分析', desc: '商品关联 · 交叉推荐', emoji: '🔗', prompt: '请分析当前商品关联规则' },
  { id: 'kb_rag', name: '知识库搜索', desc: '企业知识库 FAQ', emoji: '📚', prompt: '搜索企业知识库' },
]

function askSkill(skill) {
  // UnifiedCopilotPanel exposes an `ask` method from template ref
  // We'll use the input approach to trigger the question
  if (copilotRef.value?.ask) {
    copilotRef.value.ask(skill.prompt)
  }
}

onMounted(async () => {
  // Support ?q= query param from CommandPalette AI mode
  const q = route.query?.q
  if (q && copilotRef.value?.ask) {
    await nextTick()
    setTimeout(() => copilotRef.value.ask(q), 300)
  }
})
</script>

<style scoped>
.bc { height: calc(100vh - 64px); overflow: hidden; }
.bc__layout { display: flex; height: 100%; }

/* ── Skill Panel ── */
.bc__skills { width: 260px; flex-shrink: 0; display: flex; flex-direction: column; border-right: 1px solid var(--v2-border-2); background: var(--v2-bg-page); overflow-y: auto; }
.bc__skills-hd { display: flex; align-items: center; justify-content: space-between; padding: 14px 16px; border-bottom: 1px solid var(--v2-border-2); }
.bc__skills-title { font-size: 12px; font-weight: 600; color: var(--v2-text-1); text-transform: uppercase; letter-spacing: 0.5px; }
.bc__skills-close { display: flex; align-items: center; justify-content: center; width: 24px; height: 24px; border: none; background: none; color: var(--v2-text-4); cursor: pointer; border-radius: 4px; }
.bc__skills-close:hover { background: var(--v2-bg-hover); color: var(--v2-text-1); }

.bc__skill-list { display: flex; flex-direction: column; gap: 2px; padding: 8px; flex: 1; }
.bc__skill-card { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border: none; background: none; border-radius: 8px; cursor: pointer; text-align: left; transition: background 0.15s; font-family: inherit; }
.bc__skill-card:hover { background: var(--v2-bg-hover); }
.bc__skill-emoji { font-size: 20px; width: 28px; text-align: center; flex-shrink: 0; }
.bc__skill-info { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.bc__skill-name { font-size: 13px; font-weight: 500; color: var(--v2-text-1); }
.bc__skill-desc { font-size: 11px; color: var(--v2-text-4); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bc__skill-arrow { color: var(--v2-text-4); flex-shrink: 0; opacity: 0; transition: opacity 0.15s; }
.bc__skill-card:hover .bc__skill-arrow { opacity: 1; }

.bc__quick-section { padding: 12px 16px; border-top: 1px solid var(--v2-border-2); display: flex; flex-direction: column; gap: 6px; }
.bc__quick-label { font-size: 10px; font-weight: 600; color: var(--v2-text-4); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px; }
.bc__quick-btn { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border: 1px solid var(--v2-border-1); border-radius: 8px; background: var(--v2-bg-card); font-size: 12px; font-weight: 500; color: var(--v2-text-2); cursor: pointer; transition: all 0.15s; font-family: inherit; }
.bc__quick-btn:hover { color: var(--v2-text-1); background: var(--v2-bg-hover); border-color: var(--v2-text-1); }

/* ── Main area ── */
.bc__main { flex: 1; display: flex; flex-direction: column; min-width: 0; overflow: hidden; }
.bc__top-bar { display: flex; align-items: center; gap: 10px; padding: 8px 16px; border-bottom: 1px solid var(--v2-border-2); flex-shrink: 0; }
.bc__bar-btn { display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; border: 1px solid var(--v2-border-1); border-radius: 6px; background: var(--v2-bg-card); color: var(--v2-text-3); cursor: pointer; transition: all 0.15s; }
.bc__bar-btn:hover { color: var(--v2-text-1); }
.bc__bar-btn--active { background: var(--v2-text-1); color: #fff; border-color: var(--v2-text-1); }
.bc__top-title { font-size: 13px; font-weight: 600; color: var(--v2-text-1); }
.bc__top-desc { font-size: 11px; color: var(--v2-text-4); }

/* ── Slide Transition ── */
.bc-slide-enter-active, .bc-slide-leave-active { transition: width 0.2s ease, opacity 0.2s ease; overflow: hidden; }
.bc-slide-enter-from, .bc-slide-leave-to { width: 0; opacity: 0; }

/* Responsive */
@media (max-width: 900px) {
  .bc__skills { position: absolute; z-index: 10; left: 0; top: 0; bottom: 0; box-shadow: 4px 0 12px rgba(0,0,0,0.08); }
}
</style>
