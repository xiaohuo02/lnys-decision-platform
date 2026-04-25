<template>
  <span class="v2-odometer v2-tabular">
    {{ displayValue }}
  </span>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  value: { type: [Number, String], required: true },
  duration: { type: Number, default: 800 },
  decimals: { type: Number, default: 0 }
})

const displayValue = ref('0')
let animationFrame = null

function easeOutQuart(x) {
  return 1 - Math.pow(1 - x, 4)
}

function animateValue(start, end, duration) {
  if (start === end) return
  let startTime = null

  const step = (timestamp) => {
    if (!startTime) startTime = timestamp
    const progress = Math.min((timestamp - startTime) / duration, 1)
    const current = start + (end - start) * easeOutQuart(progress)
    
    // Add commas for thousands and respect decimals
    displayValue.value = current.toLocaleString(undefined, {
      minimumFractionDigits: props.decimals,
      maximumFractionDigits: props.decimals
    })

    if (progress < 1) {
      animationFrame = window.requestAnimationFrame(step)
    } else {
      displayValue.value = end.toLocaleString(undefined, {
        minimumFractionDigits: props.decimals,
        maximumFractionDigits: props.decimals
      })
    }
  }

  if (animationFrame) window.cancelAnimationFrame(animationFrame)
  animationFrame = window.requestAnimationFrame(step)
}

function parseVal(val) {
  if (typeof val === 'number') return val
  // Remove commas and convert string to float
  return parseFloat(String(val).replace(/,/g, '')) || 0
}

watch(() => props.value, (newVal, oldVal) => {
  const start = parseVal(oldVal || 0)
  const end = parseVal(newVal)
  animateValue(start, end, props.duration)
})

onMounted(() => {
  const end = parseVal(props.value)
  animateValue(0, end, props.duration)
})

onUnmounted(() => {
  if (animationFrame) window.cancelAnimationFrame(animationFrame)
})
</script>

<style scoped>
.v2-odometer {
  display: inline-block;
  /* Tabular nums rule from global.css ensures characters have equal width */
}
</style>
