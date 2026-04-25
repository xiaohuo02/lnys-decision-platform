<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" :stroke-width="sw" stroke-linecap="round" stroke-linejoin="round">
    <path d="M2 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v1H2V7z" />
    <path d="M2 10h20v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V10z" />
    <path d="M9 14h6" />
    <path d="M12 14v3" />
  </svg>
</template>
<script setup>
defineProps({ size: { type: [Number, String], default: 20 }, sw: { type: [Number, String], default: 1.5 } })
</script>
