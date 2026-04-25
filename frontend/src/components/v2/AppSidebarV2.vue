<template>
  <nav class="sidebar" :class="[
    `sidebar--${variant}`,
    { 'sidebar--collapsed': collapsed }
  ]">
    <!-- Brand -->
    <div class="sidebar__brand">
      <div class="sidebar__logo v2-magnetic" :class="`sidebar__logo--${variant}`">L</div>
      <div v-if="!collapsed" class="sidebar__brand-text">
        <span class="sidebar__brand-name">柠优生活</span>
        <span class="sidebar__brand-sub">{{ variant === 'console' ? '治理控制台' : 'AI 经营决策中枢' }}</span>
      </div>
    </div>

    <!-- Navigation (grouped for both business & console) -->
    <div class="sidebar__nav">
      <template v-for="group in navGroups" :key="group.key">
        <div v-if="group.items.length" class="sidebar__group">
          <transition name="sidebar-fade">
            <div v-if="!collapsed" class="sidebar__group-label">{{ group.label }}</div>
          </transition>
          <div
            v-for="item in group.items"
            :key="item.path"
            class="sidebar__item"
            :class="{ 'sidebar__item--active': isActive(item.path) }"
            @click="navigate(item.path)"
          >
            <component
              v-if="variant === 'console'"
              :is="consoleIconMap[item.iconKey]"
              :size="20"
            />
            <el-icon v-else :size="20"><component :is="item.icon" /></el-icon>
            <transition name="sidebar-fade">
              <span v-if="!collapsed" class="sidebar__item-label">{{ item.title }}</span>
            </transition>
            <transition name="sidebar-fade">
              <span v-if="!collapsed && item.badge" class="sidebar__badge">{{ item.badge }}</span>
            </transition>
          </div>
        </div>
      </template>
    </div>

    <!-- Switch -->
    <div class="sidebar__footer">
      <div class="sidebar__divider" />
      <div class="sidebar__item sidebar__item--switch" @click="navigate(switchTarget)">
        <component :is="switchIconComponent" :size="20" />
        <transition name="sidebar-fade">
          <span v-if="!collapsed" class="sidebar__item-label">{{ switchLabel }}</span>
        </transition>
      </div>
    </div>
  </nav>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/useAuthStore'
import { hasAccess } from '@/constants/roles'
import businessRoutes from '@/router/modules/business'
import consoleRoutes from '@/router/modules/console'
import {
  IconDashboard, IconActivityFeed, IconOpsCopilot,
  IconTraceExplorer, IconAgentHub, IconHealth,
  IconPromptStudio, IconKnowledge, IconKnowledgeV2, IconEvalCenter,
  IconSecurity, IconReleases, IconTeamSettings,
  IconSwitchBiz, IconSwitchConsole,
} from '@/components/icons'

const props = defineProps({
  collapsed: { type: Boolean, default: false },
  variant:   { type: String, default: 'business', validator: v => ['business', 'console'].includes(v) },
})

const route  = useRoute()
const router = useRouter()
const auth   = useAuthStore()

const sourceRoutes = computed(() => props.variant === 'console' ? consoleRoutes : businessRoutes)
const menuGroup    = computed(() => props.variant)
const pathPrefix   = computed(() => props.variant === 'console' ? '/console/' : '/')

/** Console nav group definitions (order matters) */
const CONSOLE_NAV_GROUP_META = [
  { key: 'command',        label: '指挥中心' },
  { key: 'observability',  label: '可观测性' },
  { key: 'ai-engineering', label: 'AI 工程' },
  { key: 'security',       label: '安全与管理' },
]

/** Business nav group definitions — 业务决策循环 */
const BUSINESS_NAV_GROUP_META = [
  { key: 'overview', label: '经营总览' },
  { key: 'insight',  label: '业务诊断' },
  { key: 'risk',     label: '风险与应答' },
  { key: 'tools',    label: '输出与工具' },
]

/** Bespoke SVG icon map: route name → icon component */
const consoleIconMap = {
  ConsoleDashboard:      IconDashboard,
  ConsoleActivityFeed:   IconActivityFeed,
  ConsoleOpsCopilot:     IconOpsCopilot,
  ConsoleTraceExplorer:  IconTraceExplorer,
  ConsoleAgentHub:       IconAgentHub,
  ConsoleHealth:         IconHealth,
  ConsolePromptStudio:   IconPromptStudio,
  ConsoleKnowledgeMemory: IconKnowledge,
  ConsoleKnowledgeV2:    IconKnowledgeV2,
  ConsoleEvalCenter:     IconEvalCenter,
  ConsoleSecurity:       IconSecurity,
  ConsoleReleases:       IconReleases,
  ConsoleTeamSettings:   IconTeamSettings,
}

/** Build flat item list (for business) */
const visibleItems = computed(() => {
  return sourceRoutes.value
    .filter(r => r.name && r.meta?.menuGroup === menuGroup.value && !r.meta?.hidden)
    .filter(r => hasAccess(auth.primaryRole, r.meta?.roles))
    .map(r => ({
      path:     pathPrefix.value + r.path,
      title:    r.meta.title,
      icon:     r.meta.icon,
      badge:    r.meta.badge || null,
      navGroup: r.meta.navGroup || null,
      iconKey:  r.name || '',
    }))
})

/** Build grouped nav (for both business & console) */
const groupMeta = computed(() =>
  props.variant === 'console' ? CONSOLE_NAV_GROUP_META : BUSINESS_NAV_GROUP_META
)

const navGroups = computed(() => {
  const items = visibleItems.value
  const groups = groupMeta.value.map(g => ({
    ...g,
    items: items.filter(i => i.navGroup === g.key),
  }))
  // 未显式归组的项兜底放到最后一组，避免菜单丢失
  const assigned = new Set(items.filter(i => i.navGroup).map(i => i.path))
  const orphans = items.filter(i => !assigned.has(i.path))
  if (orphans.length) {
    groups.push({ key: '_other', label: '其他', items: orphans })
  }
  return groups
})

// 业务应用首屏走 '/' 由 router redirect 决定（目前指向 /analyze）；治理后台保留明确路径
const switchTarget = computed(() => props.variant === 'console' ? '/' : '/console/dashboard')
const switchLabel  = computed(() => props.variant === 'console' ? '业务应用' : '治理控制台')
const switchIconComponent = computed(() => props.variant === 'console' ? IconSwitchBiz : IconSwitchConsole)

function isActive(path) {
  return route.path === path || route.path.startsWith(path + '/')
}

function navigate(path) {
  router.push(path)
}
</script>

<style scoped>
.sidebar {
  height: 100vh;
  display: flex;
  flex-direction: column;
  width: var(--v2-sidebar-width);
  transition: width var(--v2-trans-spring);
  overflow: hidden;
  user-select: none;
  background: transparent;
  border-right: var(--v2-border-width) solid var(--v2-border-2);
}
.sidebar--collapsed { width: var(--v2-sidebar-collapsed-width); }

/* Remove explicit background, let the app page background show through */

/* ── Brand ── */
.sidebar__brand {
  display: flex;
  align-items: center;
  gap: var(--v2-space-3);
  padding: var(--v2-space-4) var(--v2-space-5);
  height: var(--v2-header-height);
  flex-shrink: 0;
  /* Transparent border to match header */
}
.sidebar--collapsed .sidebar__brand { justify-content: center; padding: var(--v2-space-4) 0; }

.sidebar__logo {
  width: 28px; height: 28px;
  border-radius: var(--v2-radius-btn);
  display: flex; align-items: center; justify-content: center;
  font-family: var(--v2-font-mono);
  font-size: 14px; 
  font-weight: 700;
  flex-shrink: 0;
  background: var(--v2-text-1);
  color: var(--v2-bg-page);
}

.sidebar__brand-text { min-width: 0; overflow: hidden; display: flex; flex-direction: column; justify-content: center; }
.sidebar__brand-name { 
  display: block; 
  color: var(--v2-text-1); 
  font-size: 14px; 
  font-weight: 600; 
  white-space: nowrap; 
  letter-spacing: -0.01em;
}
.sidebar__brand-sub  { 
  display: block; 
  color: var(--v2-text-3); 
  font-family: var(--v2-font-mono);
  font-size: 10px; 
  margin-top: 2px;
  white-space: nowrap; 
  text-transform: uppercase; 
  letter-spacing: 0.05em; 
}

/* ── Navigation (Twitter Style) ── */
.sidebar__nav {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: var(--v2-space-2) var(--v2-space-3);
}

/* ── Group (Console only) ── */
.sidebar__group {
  margin-bottom: var(--v2-space-1);
}
.sidebar__group-label {
  font-size: 9px;
  font-weight: var(--v2-font-semibold);
  color: var(--v2-text-4);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: var(--v2-space-3) var(--v2-space-3) var(--v2-space-1);
  user-select: none;
}

.sidebar__item {
  display: flex;
  align-items: center;
  gap: var(--v2-space-4);
  height: 44px;
  padding: 0 var(--v2-space-3);
  margin-bottom: 4px;
  border-radius: var(--v2-radius-btn);
  color: var(--v2-text-3);
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition: color 0.15s ease, transform 0.4s cubic-bezier(0.16, 1, 0.3, 1);
  white-space: nowrap;
  position: relative;
}
.sidebar--collapsed .sidebar__item {
  justify-content: center;
  padding: 0;
}
.sidebar__item:hover {
  color: var(--v2-text-1);
  /* No background color on hover, only text color change (Twitter style) */
}
.sidebar__item:active {
  transform: scale(0.96);
}

/* Active State (True Flat) */
.sidebar__item--active {
  color: var(--v2-text-1) !important;
  font-weight: 600;
}
.sidebar__item--active::before {
  content: '';
  position: absolute;
  left: -12px; /* Pull it slightly out of the padding */
  top: 10px; 
  bottom: 10px;
  width: 4px;
  border-radius: 999px;
  background: var(--v2-text-1);
}
.sidebar--collapsed .sidebar__item--active::before { 
  left: 6px; 
}

.sidebar__item-label { overflow: hidden; text-overflow: ellipsis; }

.sidebar__badge {
  margin-left: auto;
  font-size: 11px;
  font-family: var(--v2-font-mono);
  background: var(--v2-error);
  color: #fff;
  border-radius: var(--v2-radius-full);
  padding: 2px 6px;
  line-height: 1.2;
}

/* ── Footer / Switch ── */
.sidebar__footer {
  flex-shrink: 0;
  padding: 0 var(--v2-space-3) var(--v2-space-4);
}
.sidebar__divider {
  height: var(--v2-border-width);
  background: var(--v2-border-2);
  margin: var(--v2-space-3) var(--v2-space-3) var(--v2-space-4);
}
.sidebar__item--switch {
  color: var(--v2-text-3) !important;
  font-size: 14px;
}
.sidebar__item--switch:hover {
  color: var(--v2-text-1) !important;
}

/* ── Transitions ── */
.sidebar-fade-enter-active { transition: opacity .2s ease .1s; }
.sidebar-fade-leave-active { transition: opacity .1s ease; }
.sidebar-fade-enter-from, .sidebar-fade-leave-to { opacity: 0; }

/* Hide scrollbar for a cleaner look */
.sidebar__nav::-webkit-scrollbar { display: none; }
</style>
