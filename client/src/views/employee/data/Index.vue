<template>
  <div class="emp-data">
    <h3 class="section-title">📊 我的数据</h3>

    <!-- 月度通行统计 -->
    <n-card title="月度通行统计" :bordered="false" class="glass-card">
      <v-chart :option="passOption" style="height: 250px" autoresize />
    </n-card>

    <!-- 本周通行 -->
    <n-card title="本周通行明细" :bordered="false" class="glass-card" style="margin-top: 16px">
      <div v-for="(item, i) in weeklyPass" :key="i" class="weekly-item">
        <div class="weekly-day">{{ item.day }}</div>
        <div class="weekly-info">
          <span>{{ item.node }}</span>
          <span class="weekly-time">{{ item.time }}</span>
        </div>
        <StatusTag :status="item.status as any" size="tiny" />
      </div>
      <n-empty v-if="!weeklyPass.length" description="暂无数据" style="margin-top: 20px" />
    </n-card>

    <!-- 模态占比 -->
    <n-card title="识别模态统计" :bordered="false" class="glass-card" style="margin-top: 16px">
      <v-chart :option="modalOption" style="height: 220px" autoresize />
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { NCard, NEmpty } from 'naive-ui'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart, PieChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { getMyRecognitions } from '@/api'
import StatusTag from '@/components/common/StatusTag.vue'

use([LineChart, PieChart, BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const weeklyPass = ref<Array<{ day: string; node: string; time: string; status: string }>>([])

const days = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const passCounts = [8, 12, 7, 15, 10, 3, 1]

const passOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  xAxis: { type: 'category', data: days, axisLine: { show: false } },
  yAxis: { type: 'value', splitLine: { lineStyle: { type: 'dashed' } } },
  series: [{ name: '通行次数', data: passCounts, type: 'bar', itemStyle: { borderRadius: [4, 4, 0, 0], color: '#2080f0' } }],
}))

const modalOption = computed(() => ({
  tooltip: { trigger: 'item', formatter: '{b}: {c} 次 ({d}%)' },
  series: [{
    type: 'pie', radius: ['40%', '70%'], center: ['50%', '50%'],
    data: [
      { name: '人脸识别', value: 85, itemStyle: { color: '#2080f0' } },
      { name: '步态识别', value: 42, itemStyle: { color: '#18a058' } },
      { name: 'BLE 识别', value: 56, itemStyle: { color: '#f0a020' } },
    ],
    label: { show: true, formatter: '{b}\n{d}%' },
  }],
}))

onMounted(async () => {
  const locs = ['主入口', '东门', '12F 会议室', '地下车库', '3F 办公区']
  weeklyPass.value = days.map((d, i) => ({
    day: d,
    node: locs[Math.floor(Math.random() * 5)],
    time: `${8 + Math.floor(Math.random() * 10)}:${String(Math.floor(Math.random() * 60)).padStart(2, '0')}`,
    status: Math.random() > 0.1 ? 'granted' : 'denied',
  }))
})
</script>

<style scoped>
.section-title { font-size: 18px; font-weight: 600; margin-bottom: 16px; }
.weekly-item { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--border-color); }
.weekly-item:last-child { border-bottom: none; }
.weekly-day { width: 40px; font-weight: 600; font-size: 13px; }
.weekly-info { flex: 1; display: flex; justify-content: space-between; font-size: 13px; }
.weekly-time { color: var(--text-secondary); }
</style>
