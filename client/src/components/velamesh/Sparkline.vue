<template>
  <svg :width="width" :height="height" class="sparkline" preserveAspectRatio="none">
    <polyline
      v-if="points.length > 1"
      :points="polylineStr"
      fill="none"
      :stroke="color"
      stroke-width="1.6"
      stroke-linejoin="round"
      stroke-linecap="round"
      vector-effect="non-scaling-stroke"
    />
    <line
      v-else-if="points.length === 1"
      :x1="points[0].x" :y1="points[0].y" :x2="points[0].x + 1" :y2="points[0].y"
      :stroke="color" stroke-width="1.6"
    />
    <circle
      v-for="p in points"
      :key="p.x"
      :cx="p.x" :cy="p.y" r="1.6"
      :fill="color"
    />
  </svg>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  values: number[]
  color?: string
  width?: number
  height?: number
  min?: number
  max?: number
}>(), {
  color: '#5aaeff',
  width: 220,
  height: 44,
})

const points = computed(() => {
  const vals = props.values
  if (vals.length === 0) return []
  let lo = props.min
  let hi = props.max
  if (lo === undefined || hi === undefined) {
    const dataLo = Math.min(...vals)
    const dataHi = Math.max(...vals)
    lo = props.min ?? (dataLo === dataHi ? dataLo - 1 : dataLo)
    hi = props.max ?? (dataLo === dataHi ? dataHi + 1 : dataHi)
  }
  const pad = 4
  const span = (hi as number) - (lo as number) || 1
  return vals.map((v, i) => {
    const x = vals.length === 1 ? pad : pad + (i / (vals.length - 1)) * (props.width - pad * 2)
    const y = props.height - pad - ((v - (lo as number)) / span) * (props.height - pad * 2)
    return { x: Number(x.toFixed(1)), y: Number(y.toFixed(1)) }
  })
})

const polylineStr = computed(() => points.value.map((p) => `${p.x},${p.y}`).join(' '))
</script>
