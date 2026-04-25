<template>
  <el-config-provider :locale="zhCn">
    <router-view />
    <CommandPalette ref="paletteRef" />
  </el-config-provider>
</template>

<script setup>
import { ref, provide } from 'vue'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import CommandPalette from '@/components/CommandPalette.vue'

const paletteRef = ref(null)
provide('commandPalette', paletteRef)
</script>

<style>
/* Global reset and font are in styles/global.css — no overrides needed here */
</style>
