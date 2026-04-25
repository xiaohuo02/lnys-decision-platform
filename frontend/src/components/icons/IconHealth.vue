<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" :stroke-width="sw" stroke-linecap="round" stroke-linejoin="round">
    <path d="M3 12h4l3-9 4 18 3-9h4" />
  </svg>
</template>
<script setup>
defineProps({ size: { type: [Number, String], default: 20 }, sw: { type: [Number, String], default: 1.5 } })
</script>
