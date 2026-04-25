<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" :stroke-width="sw" stroke-linecap="round" stroke-linejoin="round">
    <path d="M18 20V10" />
    <path d="M12 20V4" />
    <path d="M6 20v-6" />
    <path d="M3 21h18" />
  </svg>
</template>
<script setup>
defineProps({ size: { type: [Number, String], default: 20 }, sw: { type: [Number, String], default: 1.5 } })
</script>
