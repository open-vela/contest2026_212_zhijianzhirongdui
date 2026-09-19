<template>
  <div class="dashboard-page">
    <h2 class="page-title">📊 仪表板</h2>

    <!-- 统计卡片 -->
    <n-grid :cols="5" :x-gap="16" :y-gap="16" class="stat-grid">
      <n-grid-item>
        <StatCard icon="👤" label="总人数" :value="overview.total_persons" color="#18a058" sub-text="已注册人员" />
      </n-grid-item>
      <n-grid-item>
        <StatCard icon="📡" label="在线设备" :value="overview.total_devices" color="#2080f0" :sub-text="`在线率 ${(overview.device_online_rate * 100).toFixed(1)}%`" />
      </n-grid-item>
      <n-grid-item>
        <StatCard icon="🚪" label="今日通行" :value="overview.today_pass_count" color="#f0a020" sub-text="较昨日 +12%" />
      </n-grid-item>
      <n-grid-item>
        <StatCard icon="🎫" label="活跃访客" :value="overview.active_visitors" color="#8050e0" sub-text="今日到访" />
      </n-grid-item>
      <n-grid-item>
        <StatCard icon="🔔" label="告警" :value="overview.alert_count" color="#d03050" sub-text="待处理" clickable @click="$router.push('/admin/audit')" />
      </n-grid-item>
    </n-grid>

    <!-- 图表区域 -->
    <n-grid :cols="2" :x-gap="16" :y-gap="16" class="chart-grid">
      <n-grid-item>
        <n-card title="通行趋势（近 6 小时）" :bordered="false" class="glass-card">
          <v-chart :option="trendOption" style="height: 300px" autoresize />
        </n-card>
      </n-grid-item>
      <n-grid-item>
        <n-card title="设备状态分布" :bordered="false" class="glass-card">
          <v-chart :option="pieOption" style="height: 300px" autoresize />
        </n-card>
      </n-grid-item>
    </n-grid>

    <!-- 实时事件流 -->
    <n-grid :cols="2" :x-gap="16" :y-gap="16">
      <n-grid-item>
        <n-card title="实时事件流" :bordered="false" class="glass-card">
          <EventStream :events="events" />
        </n-card>
      </n-grid-item>
      <n-grid-item>
        <n-card title="最近通行记录" :bordered="false" class="glass-card">
          <n-data-table
            :columns="recogColumns"
            :data="recentRecognitions"
            :bordered="false"
            size="small"
            :max-height="400"
          />
        </n-card>
      </n-grid-item>
    </n-grid>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, h } from 'vue'
import { NGrid, NGridItem, NCard, NDataTable, NTag } from 'naive-ui'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { DashboardOverview, TrendDataPoint, Recognition } from '@/types'
import { getDashboardOverview, getPassTrend, getRecentEvents } from '@/api'
import StatCard from '@/components/common/StatCard.vue'
import EventStream from '@/components/common/EventStream.vue'
import StatusTag from '@/components/common/StatusTag.vue'

use([LineChart, PieChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const overview = ref<DashboardOverview>({} as any)
const events = ref<any[]>([])
const trendData = ref<TrendDataPoint[]>([])
// 最近通行记录由 WebSocket 事件转换而来，字段为 Recognition 子集，故用宽松类型
const recentRecognitions = ref<any[]>([])

const trendOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  xAxis: { type: 'category', data: trendData.value.map((d) => d.time), axisLine: { show: false } },
  yAxis: { type: 'value', splitLine: { lineStyle: { type: 'dashed' } } },
  series: [{
    data: trendData.value.map((d) => d.count),
    type: 'line',
    smooth: true,
    areaStyle: { opacity: 0.15 },
    lineStyle: { width: 3 },
    itemStyle: { color: '#2080f0' },
  }],
}))

const pieOption = computed(() => ({
  tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
  series: [{
    type: 'pie',
    radius: ['40%', '70%'],
    center: ['50%', '50%'],
    data: [
      { value: 18, name: '在线', itemStyle: { color: '#18a058' } },
      { value: 2, name: '离线', itemStyle: { color: '#d03050' } },
      { value: 1, name: '告警', itemStyle: { color: '#f0a020' } },
    ],
    label: { show: true, formatter: '{b}\n{d}%' },
    emphasis: { itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,0.15)' } },
  }],
}))

const recogColumns = [
  { title: '时间', key: 'created_at', width: 80, render: (r: Recognition) => new Date(r.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) },
  { title: '姓名', key: 'person_name', width: 70 },
  { title: '位置', key: 'node_id', width: 100 },
  { title: '结果', key: 'decision', width: 80, render: (r: Recognition) => h(StatusTag, { status: r.decision as any, size: 'tiny' }) },
  { title: '置信度', key: 'fusion_conf', width: 70, render: (r: Recognition) => `${(r.fusion_conf * 100).toFixed(0)}%` },
]

onMounted(async () => {
  const [ov, trend, evts] = await Promise.all([
    getDashboardOverview(),
    getPassTrend(),
    getRecentEvents(),
  ])
  overview.value = ov.data
  trendData.value = trend.data

  // 转换 RealtimeEvent 为最近通行记录
  events.value = evts?.data || []
  recentRecognitions.value = events.value.slice(0, 10).map((e: any) => ({
    id: e.id,
    person_name: e.person_name || '未知',
    node_id: e.node_id || '',
    fusion_conf: e.fusion_conf || 0,
    decision: e.decision || 'unknown',
    created_at: e.created_at || new Date().toISOString(),
  }))
})
</script>

<style scoped>
.dashboard-page { max-width: 1400px; }
.page-title { margin-bottom: 20px; font-size: 22px; }
.stat-grid { margin-bottom: 20px; }
.chart-grid { margin-bottom: 20px; }
</style>
