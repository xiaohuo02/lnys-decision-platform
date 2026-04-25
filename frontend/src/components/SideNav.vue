<template>
  <div class="side-nav">
    <div class="logo">
      <span class="logo-text">柠优生活</span>
      <span class="logo-sub">大数据平台</span>
    </div>
    <el-menu :default-active="activeRoute" router :background-color="'transparent'"
             :text-color="'var(--v2-sidebar-text)'"
             :active-text-color="'var(--v2-sidebar-text-active)'" :collapse="collapsed">
      <el-menu-item v-for="item in navItems" :key="item.path" :index="item.path">
        <el-icon><component :is="item.icon" /></el-icon>
        <template #title>{{ item.title }}</template>
      </el-menu-item>

      <el-divider style="border-color: var(--v2-sidebar-border); margin: 8px 0" />

      <el-sub-menu index="console">
        <template #title>
          <el-icon><Setting /></el-icon>
          <span>治理控制台</span>
        </template>
        <el-menu-item v-for="item in consoleItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>{{ item.title }}</template>
        </el-menu-item>
      </el-sub-menu>
    </el-menu>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Setting } from '@element-plus/icons-vue'

const route = useRoute()
const collapsed = false
const activeRoute = computed(() => {
  const path = route.path
  if (path.startsWith('/console/')) return path
  return '/' + path.split('/')[1]
})

const navItems = [
  { path: '/dashboard',   title: '平台总览',     icon: 'DataAnalysis' },
  { path: '/customer',    title: '客户分析',     icon: 'User' },
  { path: '/forecast',    title: '销售预测',     icon: 'TrendCharts' },
  { path: '/fraud',       title: '欺诈风控',     icon: 'Warning' },
  { path: '/sentiment',   title: '舆情分析',     icon: 'ChatDotRound' },
  { path: '/inventory',   title: '库存优化',     icon: 'Box' },
  { path: '/chat',        title: 'OpenClaw客服', icon: 'Service' },
  { path: '/association', title: '关联分析',     icon: 'Share' },
  { path: '/report',      title: '报告导出',     icon: 'Document' },
]

const consoleItems = [
  { path: '/console/dashboard', title: '治理总览',     icon: 'Monitor' },
  { path: '/console/workflows', title: 'Workflows',    icon: 'Connection' },
  { path: '/console/agents',    title: 'Agents',       icon: 'Cpu' },
  { path: '/console/traces',    title: 'Traces',       icon: 'List' },
  { path: '/console/reviews',   title: 'HITL 审核',    icon: 'Finished' },
  { path: '/console/prompts',   title: 'Prompt Center',icon: 'EditPen' },
  { path: '/console/policies',  title: 'Policies',     icon: 'Lock' },
  { path: '/console/releases',  title: 'Release Center',icon: 'Upload' },
  { path: '/console/audit',       title: 'Audit',        icon: 'Memo' },
  { path: '/console/ops-copilot', title: 'Ops Copilot',    icon: 'ChatLineRound' },
  { path: '/console/evals',        title: 'Eval Center',    icon: 'DataAnalysis' },
  { path: '/console/knowledge',    title: 'Knowledge',      icon: 'Collection' },
  { path: '/console/memory',       title: 'Memory Center',  icon: 'Coin' },
]
</script>

<style scoped>
.side-nav { height: 100vh; display: flex; flex-direction: column; }
.logo { padding: 20px 16px 12px; border-bottom: 1px solid var(--v2-sidebar-border); }
.logo-text { display: block; color: var(--v2-sidebar-text-active); font-size: 18px; font-weight: 700; }
.logo-sub  { display: block; color: var(--v2-sidebar-text); font-size: 11px; margin-top: 2px; }
.el-menu  { border-right: none; flex: 1; }
</style>
