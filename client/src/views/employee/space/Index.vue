<template>
  <div class="emp-space">
    <h3 class="section-title">🏗️ 空间占用</h3>

    <!-- 占用率图表 -->
    <n-card title="区域占用率" :bordered="false" class="glass-card">
      <div v-for="s in spaceData" :key="s.zone_name" class="space-item">
        <div class="space-label">
          <span>{{ s.zone_name }}</span>
          <span class="space-percent">{{ s.current }}/{{ s.capacity }} ({{ s.rate }}%)</span>
        </div>
        <div class="space-bar">
          <div
            class="space-fill"
            :style="{ width: s.rate + '%' }"
            :class="{ warn: s.rate > 70, danger: s.rate > 90 }"
          />
        </div>
      </div>
      <n-empty v-if="!spaceData.length" description="暂无数据" style="margin-top: 20px" />
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NCard, NEmpty } from 'naive-ui'
import { getSpaceOccupancy } from '@/api'

const spaceData = ref<Array<{ zone_name: string; capacity: number; current: number; rate: number }>>([])

onMounted(async () => {
  const res = await getSpaceOccupancy()
  spaceData.value = res.data
})
</script>

<style scoped>
.section-title { font-size: 18px; font-weight: 600; margin-bottom: 16px; }
.space-item { margin-bottom: 16px; }
.space-label { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 6px; }
.space-percent { color: var(--text-secondary); }
.space-bar { height: 10px; background: var(--bg-secondary); border-radius: 5px; overflow: hidden; }
.space-fill { height: 100%; background: #2080f0; border-radius: 5px; transition: width 0.8s; }
.space-fill.warn { background: #f0a020; }
.space-fill.danger { background: #d03050; }
</style>
