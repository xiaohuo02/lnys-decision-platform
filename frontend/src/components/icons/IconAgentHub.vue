<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" :stroke-width="sw" stroke-linecap="round" stroke-linejoin="round">
    <rect x="8" y="2" width="8" height="6" rx="1.5" />
    <rect x="2" y="16" width="7" height="6" rx="1.5" />
    <rect x="15" y="16" width="7" height="6" rx="1.5" />
    <path d="M12 8v4" />
    <path d="M5.5 16v-2a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v2" />
  </svg>
</template>
<script setup>
defineProps({ size: { type: [Number, String], default: 20 }, sw: { type: [Number, String], default: 1.5 } })
</script>
