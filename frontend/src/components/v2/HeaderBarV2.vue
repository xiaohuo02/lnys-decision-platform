<template>
  <header class="hdr">
    <div class="hdr__left">
      <button class="hdr__toggle v2-magnetic" @click="$emit('toggle-collapse')" :title="collapsed ? '展开' : '收起'">
        <el-icon :size="18"><component :is="collapsed ? PanelRightOpen : PanelLeftClose" /></el-icon>
      </button>

      <!-- Extremely minimal Breadcrumb -->
      <nav v-if="breadcrumbs.length" class="hdr__crumbs">
        <template v-for="(crumb, i) in breadcrumbs" :key="i">
          <span v-if="i > 0" class="hdr__crumb-sep">/</span>
          <router-link v-if="crumb.path" :to="crumb.path" class="hdr__crumb hdr__crumb--link">{{ crumb.label }}</router-link>
          <span v-else class="hdr__crumb hdr__crumb--current">{{ crumb.label }}</span>
        </template>
      </nav>
    </div>

    <div class="hdr__right">
      <!-- Search / Command Palette trigger -->
      <button class="hdr__search" @click="openPalette">
        <span class="hdr__search-icon"><el-icon :size="14"><Search /></el-icon></span>
        <span class="hdr__search-text">搜索...</span>
        <kbd class="hdr__kbd">⌘K</kbd>
      </button>

      <!-- C-β: AI 任务指示器 -->
      <RunTicker />

      <!-- Theme Toggle -->
      <button class="hdr__icon-btn v2-magnetic" @click="toggleTheme" :title="isDark ? '浅色模式' : '深色模式'">
        <el-icon :size="16">
          <Moon v-if="!isDark" />
          <Sun v-else />
        </el-icon>
      </button>

      <!-- User Dropdown (Minimalist) -->
      <el-dropdown trigger="click" @command="handleCommand" :popper-class="'v2-dropdown'">
        <button class="hdr__user v2-magnetic">
          <span class="hdr__avatar">{{ avatarText }}</span>
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item disabled class="v2-dropdown-header">
              <span class="hdr__dd-user">{{ username }}</span>
              <span class="hdr__dd-role">{{ roleLabel }}</span>
            </el-dropdown-item>
            <el-dropdown-item v-if="auth.isAdmin" divided command="settings">
              <el-icon><Settings /></el-icon> 设置
            </el-dropdown-item>
            <el-dropdown-item :divided="!auth.isAdmin" command="logout">
              <el-icon><Power /></el-icon> 退出登录
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </header>
</template>

<script setup>
import { computed, inject } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/useAuthStore'
import { useTheme } from '@/composables/useTheme'
// Note: We use global icon names here, which are mapped to Lucide in main.js. 
// So 'PanelLeftClose' needs to be mapped if not already. We'll fallback to Lucide components if needed.
import { PanelLeftClose, PanelRightOpen, Search, Settings, Power, Moon, Sun } from 'lucide-vue-next'
import RunTicker from '@/components/runs/RunTicker.vue'

defineProps({
  collapsed: { type: Boolean, default: false },
  compact:   { type: Boolean, default: false },
})
defineEmits(['toggle-collapse'])

const route  = useRoute()
const router = useRouter()
const auth   = useAuthStore()

const { isDark, toggle: toggleTheme } = useTheme()
const commandPalette = inject('commandPalette', null)
function openPalette() { commandPalette?.value?.open() }

const username   = computed(() => auth.username || '用户')
const roleLabel  = computed(() => auth.roleLabel)
const avatarText = computed(() => (username.value || 'U').charAt(0).toUpperCase())

const breadcrumbs = computed(() => {
  const matched = route.matched.filter(r => r.meta?.title)
  if (matched.length <= 1) return []
  return matched.map((r, i) => ({
    label: r.meta.title,
    path: i < matched.length - 1 ? r.path : null,
  }))
})

function handleCommand(cmd) {
  if (cmd === 'logout') {
    auth.logout()
    router.replace('/login')
  } else if (cmd === 'settings') {
    router.push('/console/settings')
  }
}
</script>

<style scoped>
.hdr {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--v2-header-height);
  padding: 0 var(--v2-space-6);
  
  /* Glassmorphism setup */
  background: var(--v2-glass-bg);
  backdrop-filter: var(--v2-glass-blur);
  -webkit-backdrop-filter: var(--v2-glass-blur);
  
  /* Hairline bottom border */
  border-bottom: var(--v2-border-width) solid var(--v2-border-2);
  
  z-index: var(--v2-z-header);
}

.hdr__left {
  display: flex;
  align-items: center;
  gap: var(--v2-space-4);
  min-width: 0;
}

.hdr__toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px; 
  height: 32px;
  border: none;
  background: transparent;
  color: var(--v2-text-3);
  cursor: pointer;
  /* Subtly different from previous code - no border radius background initially */
  border-radius: var(--v2-radius-btn);
}
.hdr__toggle:hover {
  color: var(--v2-text-1);
}

/* Breadcrumb - Super minimal */
.hdr__crumbs {
  display: flex;
  align-items: center;
  gap: var(--v2-space-2);
  font-size: 13px;
}
.hdr__crumb-sep { color: var(--v2-border-1); font-weight: 300; }
.hdr__crumb--link {
  color: var(--v2-text-3);
  text-decoration: none;
  transition: color var(--v2-trans-fast);
}
.hdr__crumb--link:hover { color: var(--v2-text-1); }
.hdr__crumb--current {
  color: var(--v2-text-1);
  font-weight: 500;
}

.hdr__right {
  display: flex;
  align-items: center;
  gap: var(--v2-space-4);
  flex-shrink: 0;
}

/* Search Bar - Raycast Style */
.hdr__search {
  display: flex;
  align-items: center;
  gap: var(--v2-space-3);
  padding: 0 8px 0 12px;
  height: 32px;
  border: var(--v2-border-width) solid var(--v2-border-1);
  border-radius: var(--v2-radius-btn);
  background: var(--v2-bg-card); /* Opaque input over glass */
  color: var(--v2-text-3);
  font-size: 13px;
  cursor: pointer;
  transition: var(--v2-trans-spring);
  width: 200px;
}
.hdr__search:hover {
  border-color: var(--v2-text-3);
  color: var(--v2-text-2);
  background: var(--v2-bg-hover);
}
.hdr__search-icon { display: flex; align-items: center; color: var(--v2-text-3); }
.hdr__search-text { flex: 1; text-align: left; }
.hdr__kbd {
  font-family: var(--v2-font-mono);
  font-size: 10px;
  padding: 2px 6px;
  border: var(--v2-border-width) solid var(--v2-border-2);
  border-radius: 4px;
  color: var(--v2-text-3);
  background: var(--v2-bg-page);
}

/* Icon Buttons */
.hdr__icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px; 
  height: 32px;
  border: none;
  background: transparent;
  color: var(--v2-text-3);
  cursor: pointer;
  border-radius: var(--v2-radius-btn);
}
.hdr__icon-btn:hover {
  color: var(--v2-text-1);
}

/* User Avatar */
.hdr__user {
  display: flex;
  align-items: center;
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 0;
  border-radius: var(--v2-radius-full);
}
.hdr__avatar {
  width: 32px; 
  height: 32px;
  border-radius: var(--v2-radius-full);
  background: var(--v2-brand-primary);
  color: var(--v2-bg-card); /* Inverse */
  display: flex; 
  align-items: center; 
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  font-family: var(--v2-font-mono);
  border: var(--v2-border-width) solid var(--v2-border-2);
}

/* Dropdown User Info */
.v2-dropdown-header {
  padding: 8px 12px;
}
.hdr__dd-user { 
  display: block; 
  font-size: 14px; 
  font-weight: 500; 
  color: var(--v2-text-1); 
}
.hdr__dd-role { 
  display: block; 
  font-size: 11px; 
  font-family: var(--v2-font-mono);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--v2-text-3); 
  margin-top: 4px; 
}
</style>
