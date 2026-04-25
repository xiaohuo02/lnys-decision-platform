<template>
  <div class="ctp">
    <div class="ctp__hd">
      <div class="ctp__hd-left">
        <h2 class="ctp__title">{{ title }}</h2>
        <span v-if="subtitle" class="ctp__sub">{{ subtitle }}</span>
      </div>
      <V2Segment v-model="activeTab" :options="segmentOptions" size="sm" @change="onTabChange" />
    </div>
    <KeepAlive>
      <component :is="activeComponent" />
    </KeepAlive>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import V2Segment from '@/components/v2/V2Segment.vue'

const props = defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  tabs: {
    type: Array,
    required: true,
    validator: (list) =>
      Array.isArray(list) &&
      list.length > 0 &&
      list.every((t) => t && typeof t.value === 'string' && typeof t.label === 'string' && t.component),
  },
  queryKey: { type: String, default: 'tab' },
})

const route = useRoute()
const router = useRouter()

const segmentOptions = computed(() => props.tabs.map(({ label, value }) => ({ label, value })))

const fallbackValue = computed(() => props.tabs[0].value)
const validValues = computed(() => props.tabs.map((t) => t.value))

function pickValid(v) {
  return validValues.value.includes(v) ? v : fallbackValue.value
}

const activeTab = ref(pickValid(route.query[props.queryKey]))

const activeComponent = computed(() => {
  const hit = props.tabs.find((t) => t.value === activeTab.value)
  return hit ? hit.component : props.tabs[0].component
})

function onTabChange(key) {
  router.replace({ query: { ...route.query, [props.queryKey]: key } })
}

watch(
  () => route.query[props.queryKey],
  (v) => {
    if (!v) return
    const next = pickValid(v)
    if (next !== activeTab.value) activeTab.value = next
  },
)
</script>

<style scoped>
.ctp__hd {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--v2-space-4);
}
.ctp__hd-left {
  display: flex;
  align-items: baseline;
  gap: var(--v2-space-2);
}
.ctp__title {
  font-size: var(--v2-text-lg);
  font-weight: var(--v2-font-semibold);
  color: var(--v2-text-1);
  margin: 0;
}
.ctp__sub {
  font-size: var(--v2-text-xs);
  color: var(--v2-text-4);
}
</style>
