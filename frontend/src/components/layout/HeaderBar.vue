<template>
  <header class="header-bar">
    <div class="header-bar__left">
      <el-button
        v-if="showCollapse"
        class="header-bar__collapse-btn"
        :icon="collapsed ? 'Expand' : 'Fold'"
        text
        @click="$emit('toggle-collapse')"
      />
      <div class="header-bar__title-group">
        <h1 class="header-bar__title">{{ title }}</h1>
        <span v-if="desc" class="header-bar__desc">{{ desc }}</span>
      </div>
    </div>
    <div class="header-bar__right">
      <div class="header-bar__search" @click="openPalette">
        <el-icon :size="16"><Search /></el-icon>
        <span class="header-bar__search-text">搜索…</span>
        <kbd class="header-bar__kbd">⌘K</kbd>
      </div>
      <el-dropdown trigger="click" @command="handleCommand">
        <div class="header-bar__user-trigger">
          <div class="header-bar__avatar">{{ avatarText }}</div>
          <div class="header-bar__user-info">
            <span class="header-bar__username">{{ username }}</span>
            <span class="header-bar__role">{{ roleLabel }}</span>
          </div>
          <el-icon :size="14"><ArrowDown /></el-icon>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item disabled>
              <el-icon><User /></el-icon>
              {{ username }}
            </el-dropdown-item>
            <el-dropdown-item divided command="logout">
              <el-icon><SwitchButton /></el-icon>
              退出登录
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </header>
</template>

<script setup>
import { computed, inject } from 'vue'
import { useRouter } from 'vue-router'
import { Search, ArrowDown, User, SwitchButton } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/useAuthStore'

const props = defineProps({
  title:        { type: String, default: '' },
  desc:         { type: String, default: '' },
  collapsed:    { type: Boolean, default: false },
  showCollapse: { type: Boolean, default: true },
})

defineEmits(['toggle-collapse', 'search'])

const commandPalette = inject('commandPalette', null)
function openPalette() { commandPalette?.value?.open() }

const router = useRouter()
const auth = useAuthStore()

const username  = computed(() => auth.username || '用户')
const roleLabel = computed(() => auth.roleLabel)
const avatarText = computed(() => (username.value || 'U').charAt(0).toUpperCase())

function handleCommand(cmd) {
  if (cmd === 'logout') {
    auth.logout()
    router.replace('/login')
  }
}
</script>

<style scoped>
.header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--header-height, 52px);
  padding: 0 20px;
  background: var(--color-bg-card);
  border-bottom: 1px solid var(--color-border-light);
}

.header-bar__left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.header-bar__collapse-btn {
  color: var(--color-text-tertiary);
  padding: 4px;
}

.header-bar__title-group {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}

.header-bar__title {
  font-size: 15px;
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0;
  white-space: nowrap;
}

.header-bar__desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-bar__right {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-shrink: 0;
}

.header-bar__search {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
  transition: border-color var(--transition-fast);
  background: var(--color-bg-elevated);
}
.header-bar__search:hover {
  border-color: var(--color-border-dark);
}
.header-bar__search-text { user-select: none; }
.header-bar__kbd {
  font-size: 10px;
  padding: 1px 5px;
  background: var(--color-bg-page);
  border: 1px solid var(--color-border);
  border-radius: 3px;
  color: var(--color-text-disabled);
  font-family: inherit;
}

.header-bar__user-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 0;
}

.header-bar__avatar {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-full);
  background: var(--color-accent);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  flex-shrink: 0;
}

.header-bar__user-info {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}

.header-bar__username {
  font-size: var(--font-size-body);
  color: var(--color-text-primary);
  font-weight: var(--font-weight-medium);
}

.header-bar__role {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}
</style>
