<template>
  <div class="stat-card glass-card" :class="{ clickable: clickable }" @click="$emit('click')">
    <div class="stat-card-header">
      <n-icon :size="28" :color="color">
        <component :is="icon" />
      </n-icon>
      <span class="stat-label">{{ label }}</span>
    </div>
    <div class="stat-value">
      <n-number-animation :from="0" :to="value" :duration="1500" />
    </div>
    <div v-if="subText" class="stat-sub">{{ subText }}</div>
  </div>
</template>

<script setup lang="ts">
import { NIcon, NNumberAnimation } from 'naive-ui'

defineProps<{
  icon: any
  label: string
  value: number
  color?: string
  subText?: string
  clickable?: boolean
}>()

defineEmits<{ click: [] }>()
</script>

<style scoped>
.stat-card { padding: 20px; border-radius: 16px; cursor: default; transition: transform 0.2s, box-shadow 0.2s; }
.stat-card:hover { transform: translateY(-2px); }
.stat-card.clickable { cursor: pointer; }
.stat-card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.stat-label { font-size: 14px; color: var(--text-secondary); }
.stat-value { font-size: 28px; font-weight: 700; line-height: 1.2; }
.stat-sub { font-size: 12px; color: var(--text-tertiary); margin-top: 4px; }
</style>
