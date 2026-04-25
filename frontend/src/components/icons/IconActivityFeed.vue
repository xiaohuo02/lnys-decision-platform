<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" :stroke-width="sw" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="5" cy="6" r="1.5" />
    <line x1="9" y1="6" x2="21" y2="6" />
    <circle cx="5" cy="12" r="1.5" />
    <line x1="9" y1="12" x2="21" y2="12" />
    <circle cx="5" cy="18" r="1.5" />
    <line x1="9" y1="18" x2="17" y2="18" />
  </svg>
</template>
<script setup>
defineProps({ size: { type: [Number, String], default: 20 }, sw: { type: [Number, String], default: 1.5 } })
</script>
