<template>
  <div class="oc-page">
    <UnifiedCopilotPanel mode="ops" />
  </div>
</template>

<script setup>
import UnifiedCopilotPanel from '@/components/copilot/UnifiedCopilotPanel.vue'
</script>

<style scoped>
.oc-page {
  height: calc(100vh - 64px);
  overflow: hidden;
}
</style>
