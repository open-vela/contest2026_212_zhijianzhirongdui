<template>
  <div class="energy-page">
    <div class="page-header">
      <h2 class="page-title">⚡ 能源管理</h2>
    </div>

    <!-- 统计卡片 -->
    <n-grid :cols="4" :x-gap="16" :y-gap="16" class="stat-grid">
      <n-grid-item><n-card :bordered="false" class="glass-card"><StatCard icon="⚡" label="总能耗" :value="overview.total_kwh" color="#2080f0" /></n-card></n-grid-item>
      <n-grid-item><n-card :bordered="false" class="glass-card"><StatCard icon="📊" label="今日能耗" :value="overview.today_kwh" color="#18a058" /></n-card></n-grid-item>
      <n-grid-item><n-card :bordered="false" class="glass-card"><StatCard icon="📈" label="峰值功率" :value="overview.peak_power_kw" color="#f0a020" sub-text="kW" /></n-card></n-grid-item>
      <n-grid-item><n-card :bordered="false" class="glass-card"><StatCard icon="📉" label="平均功率" :value="overview.avg_power_kw" color="#8050e0" sub-text="kW" /></n-card></n-grid-item>
    </n-grid>

    <!-- 能耗趋势 + 区域分布 -->
    <n-grid :cols="2" :x-gap="16" :y-gap="16">
      <n-grid-item>
        <n-card title="能耗趋势（近 7 天）" :bordered="false" class="glass-card">
          <v-chart :option="trendOption" style="height: 320px" autoresize />
        </n-card>
      </n-grid-item>
      <n-grid-item>
        <n-card title="区域能耗分布" :bordered="false" class="glass-card">
          <v-chart :option="pieOption" style="height: 320px" autoresize />
        </n-card>
      </n-grid-item>
    </n-grid>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { NCard, NGrid, NGridItem } from 'naive-ui'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EnergyRecord } from '@/types'
import { getEnergyOverview, getEnergyTrend, getEnergyByZone } from '@/api'
import StatCard from '@/components/common/StatCard.vue'

use([LineChart, PieChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const overview = ref<any>({ total_kwh: 0, today_kwh: 0, peak_power_kw: 0, avg_power_kw: 0 })
const trendData = ref<EnergyRecord[]>([])
const zoneData = ref<Array<{ zone_name: string; energy_kwh: number; percentage: number }>>([])

const trendOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  xAxis: { type: 'category', data: trendData.value.map((d) => d.timestamp), axisLine: { show: false } },
  yAxis: { type: 'value', name: 'kWh', splitLine: { lineStyle: { type: 'dashed' } } },
  series: [
    { name: '能耗', data: trendData.value.map((d) => d.energy_kwh), type: 'line', smooth: true, areaStyle: { opacity: 0.15 }, lineStyle: { width: 3 }, itemStyle: { color: '#f0a020' } },
  ],
}))

const pieOption = computed(() => ({
  tooltip: { trigger: 'item', formatter: '{b}: {c} kWh ({d}%)' },
  series: [{
    type: 'pie', radius: ['40%', '70%'], center: ['50%', '50%'],
    data: zoneData.value.map((z) => ({ name: z.zone_name, value: z.energy_kwh })),
    label: { show: true, formatter: '{b}\n{d}%' },
  }],
}))

onMounted(async () => {
  const [ov, trend, zone] = await Promise.all([getEnergyOverview(), getEnergyTrend(7), getEnergyByZone()])
  overview.value = ov.data
  trendData.value = trend.data
  zoneData.value = zone.data
})
</script>

<style scoped>
.energy-page { max-width: 1400px; }
.page-header { margin-bottom: 20px; }
.page-title { font-size: 22px; }
.stat-grid { margin-bottom: 20px; }
</style>
