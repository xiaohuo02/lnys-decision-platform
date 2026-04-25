<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" :stroke-width="sw" stroke-linecap="round" stroke-linejoin="round">
    <path d="M3 6h18" />
    <path d="M7 12h14" />
    <path d="M5 18h12" />
    <circle cx="4" cy="12" r="1" />
    <circle cx="3" cy="18" r="1" />
  </svg>
</template>
<script setup>
defineProps({ size: { type: [Number, String], default: 20 }, sw: { type: [Number, String], default: 1.5 } })
</script>
