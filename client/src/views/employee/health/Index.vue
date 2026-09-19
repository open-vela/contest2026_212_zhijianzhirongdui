<template>
  <div class="emp-health">
    <h3 class="section-title">❤️ 健康数据</h3>

    <!-- 最新数据 -->
    <n-grid :cols="2" :x-gap="16" :y-gap="16" class="mb-4">
      <n-grid-item>
        <n-card :bordered="false" class="glass-card health-stat">
          <div class="health-icon">🌡️</div>
          <div class="health-value">{{ latestTemp }}°C</div>
          <div class="health-label">体温</div>
        </n-card>
      </n-grid-item>
      <n-grid-item>
        <n-card :bordered="false" class="glass-card health-stat">
          <div class="health-icon">💓</div>
          <div class="health-value">{{ latestHeartRate }}</div>
          <div class="health-label">心率 (bpm)</div>
        </n-card>
      </n-grid-item>
    </n-grid>

    <!-- 健康趋势 -->
    <n-card title="历史记录" :bordered="false" class="glass-card">
      <n-data-table :columns="columns" :data="healthRecords" :bordered="false" size="small" />
      <n-empty v-if="!healthRecords.length" description="暂无健康数据" style="margin-top: 20px" />
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { NCard, NGrid, NGridItem, NDataTable, NEmpty } from 'naive-ui'
import type { HealthRecord } from '@/types'
import { getMyHealth } from '@/api'

const healthRecords = ref<HealthRecord[]>([])

const latestTemp = computed(() => healthRecords.value[0]?.temperature.toFixed(1) || '--')
const latestHeartRate = computed(() => healthRecords.value[0]?.heart_rate || '--')

const columns = [
  { title: '日期', key: 'recorded_at', render: (r: HealthRecord) => r.recorded_at },
  { title: '体温', key: 'temperature', render: (r: HealthRecord) => `${r.temperature}°C` },
  { title: '心率', key: 'heart_rate', render: (r: HealthRecord) => `${r.heart_rate} bpm` },
]

onMounted(async () => {
  const res = await getMyHealth()
  healthRecords.value = res.data
})
</script>

<style scoped>
.section-title { font-size: 18px; font-weight: 600; margin-bottom: 16px; }
.health-stat { text-align: center; padding: 20px; }
.health-icon { font-size: 32px; }
.health-value { font-size: 28px; font-weight: 700; margin: 8px 0; }
.health-label { font-size: 12px; color: var(--text-secondary); }
</style>
