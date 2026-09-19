<template>
  <n-tag :type="config.type" :size="size" :bordered="false" round>
    {{ config.label }}
  </n-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { NTag } from 'naive-ui'
import type { DataProvenance } from '@/types/demo'

const props = withDefaults(defineProps<{
  provenance: DataProvenance
  size?: 'tiny' | 'small' | 'medium'
}>(), { size: 'small' })

const config = computed(() => ({
  real: { label: '真实证据', type: 'success' as const },
  mock: { label: '演练 Mock', type: 'info' as const },
  pending_real: { label: '待实机', type: 'warning' as const },
  reserved: { label: '接口预留', type: 'default' as const },
})[props.provenance])
</script>
