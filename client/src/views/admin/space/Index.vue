<template>
  <div class="space-page">
    <div class="page-header">
      <h2 class="page-title">🏗️ 空间管理</h2>
    </div>

    <!-- 楼层筛选 -->
    <n-space style="margin-bottom: 16px;">
      <n-button v-for="f in floors" :key="f" :type="selectedFloor === f ? 'primary' : 'default'" size="small" @click="selectedFloor = f">
        {{ f === -1 ? 'B1' : f + 'F' }}
      </n-button>
      <n-button :type="selectedFloor === -99 ? 'primary' : 'default'" size="small" @click="selectedFloor = -99">全部</n-button>
    </n-space>

    <!-- 空间卡片 -->
    <n-grid :cols="3" :x-gap="16" :y-gap="16">
      <n-grid-item v-for="zone in filteredZones" :key="zone.id">
        <n-card :bordered="false" class="glass-card zone-card" :class="{ crowded: zone.status === 'crowded', idle: zone.status === 'idle' }">
          <div class="zone-header">
            <div class="zone-icon">{{ zoneIcons[zone.zone_type] || '🏠' }}</div>
            <StatusTag :status="zone.status as any" size="tiny" />
          </div>
          <div class="zone-name">{{ zone.name }}</div>
          <div class="zone-detail">
            <span>楼层: {{ zone.floor === -1 ? 'B1' : zone.floor + 'F' }}</span>
            <span>面积: {{ zone.area }}m²</span>
          </div>
          <div class="zone-detail">
            <span>容量: {{ zone.capacity }}人</span>
            <span>设备: {{ zone.device_count }}台</span>
          </div>
          <div class="occupancy-bar">
            <div class="occupancy-fill" :style="{ width: occupancyPercent(zone) + '%' }" :class="{ warn: occupancyPercent(zone) > 70, danger: occupancyPercent(zone) > 90 }" />
          </div>
          <div class="occupancy-label">{{ zone.current_occupancy }}/{{ zone.capacity }} 人 ({{ occupancyPercent(zone) }}%)</div>
        </n-card>
      </n-grid-item>
    </n-grid>

    <n-empty v-if="!filteredZones.length" description="该楼层暂无空间" style="margin-top: 40px" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { NCard, NGrid, NGridItem, NButton, NSpace, NEmpty } from 'naive-ui'
import type { Zone } from '@/types'
import { getZones } from '@/api'
import StatusTag from '@/components/common/StatusTag.vue'

const zones = ref<Zone[]>([])
const selectedFloor = ref(-99)

const zoneIcons: Record<string, string> = { office: '🏢', meeting_room: '📋', corridor: '🚶', entrance: '🚪', rest_area: '☕', utility: '🔧' }

const floors = computed(() => [...new Set(zones.value.map((z) => z.floor))].sort((a, b) => a - b))

const filteredZones = computed(() => selectedFloor.value === -99 ? zones.value : zones.value.filter((z) => z.floor === selectedFloor.value))

function occupancyPercent(zone: Zone): number {
  return zone.capacity > 0 ? Math.round((zone.current_occupancy / zone.capacity) * 100) : 0
}

onMounted(async () => {
  const res = await getZones()
  zones.value = res.data
})
</script>

<style scoped>
.space-page { max-width: 1400px; }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
.page-title { font-size: 22px; }
.zone-card { transition: transform 0.2s; }
.zone-card:hover { transform: translateY(-3px); }
.zone-card.crowded { border-left: 3px solid #f0a020; }
.zone-card.idle { border-left: 3px solid #18a058; }
.zone-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.zone-icon { font-size: 28px; }
.zone-name { font-size: 16px; font-weight: 600; margin-bottom: 8px; }
.zone-detail { display: flex; gap: 16px; font-size: 12px; color: var(--text-secondary); line-height: 1.8; }
.occupancy-bar { height: 6px; background: var(--bg-secondary); border-radius: 3px; margin-top: 10px; overflow: hidden; }
.occupancy-fill { height: 100%; background: #2080f0; border-radius: 3px; transition: width 0.5s; }
.occupancy-fill.warn { background: #f0a020; }
.occupancy-fill.danger { background: #d03050; }
.occupancy-label { font-size: 11px; color: var(--text-tertiary); margin-top: 4px; text-align: right; }
</style>
