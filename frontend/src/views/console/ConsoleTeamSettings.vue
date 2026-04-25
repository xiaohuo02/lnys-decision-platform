<template>
  <ConsoleTabPage title="团队与设置" subtitle="团队权限 · 系统设置 · Copilot 配置" :tabs="TABS" />
</template>

<script setup>
import ConsoleTabPage from '@/components/console/ConsoleTabPage.vue'
import ConsoleTeam from './ConsoleTeam.vue'
import ConsoleSettings from './ConsoleSettings.vue'
import ConsoleCopilotConfig from './ConsoleCopilotConfig.vue'

const TABS = [
  { label: '团队权限', value: 'team',    component: ConsoleTeam },
  { label: '系统设置', value: 'system',  component: ConsoleSettings },
  { label: 'Copilot',  value: 'copilot', component: ConsoleCopilotConfig },
]
</script>
