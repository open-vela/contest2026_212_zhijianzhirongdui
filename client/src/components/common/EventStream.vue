<template>
  <div class="event-stream">
    <n-timeline>
      <n-timeline-item
        v-for="evt in events"
        :key="evt.id"
        :type="getEventType(evt)"
        :title="getEventTitle(evt)"
        :time="formatTime(evt.ts)"
        :content="getEventContent(evt)"
      />
    </n-timeline>
    <div v-if="!events.length" class="empty-state">
      <n-empty description="暂无事件" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { NTimeline, NTimelineItem, NEmpty } from 'naive-ui'
import type { RealtimeEvent } from '@/types'

const props = withDefaults(defineProps<{ events: RealtimeEvent[] }>(), { events: () => [] })

function getEventType(evt: RealtimeEvent): 'success' | 'warning' | 'error' | 'info' {
  const typeMap: Record<string, 'success' | 'warning' | 'error' | 'info'> = {
    recognition: 'success',
    device_status: 'info',
    device_offline: 'error',
    alert_new: 'warning',
    alert_resolved: 'success',
  }
  return typeMap[evt.type] || 'info'
}

function getEventTitle(evt: RealtimeEvent): string {
  switch (evt.type) {
    case 'recognition': return `${evt.data.person_name} · ${evt.data.decision === 'granted' ? '✅ 通过' : '❌ 拒绝'}`
    case 'device_status': return `设备 ${evt.data.node_id} 心跳上报`
    case 'device_offline': return `设备 ${evt.data.node_id} 已离线`
    case 'alert_new': return `告警: ${evt.data.title}`
    case 'alert_resolved': return `告警已解除: ${evt.data.title}`
    default: return '未知事件'
  }
}

function getEventContent(evt: RealtimeEvent): string {
  if (evt.type === 'recognition') {
    return `${evt.data.node_id} · 融合置信度 ${(evt.data.fusion_conf * 100).toFixed(0)}%`
  }
  return evt.data.explain_text || evt.data.message || ''
}

function formatTime(ts: number): string {
  const d = new Date(ts * 1000)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}
</script>

<style scoped>
.event-stream { max-height: 400px; overflow-y: auto; }
.empty-state { padding: 40px 0; text-align: center; }
</style>
