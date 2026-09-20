<template>
  <div class="queue-page">
    <div class="queue-toolbar glass-card">
      <div class="toolbar-title">
        <span class="title-text">离线事件队列</span>
        <span class="depth-chip" :class="{ active: depth > 0 }">待补发 {{ depth }}</span>
      </div>
      <div class="toolbar-actions">
        <n-button size="small" :loading="loading" @click="load">
          <template #icon><n-icon :component="RefreshOutline" /></template>
          刷新
        </n-button>
        <n-button size="small" type="primary" :disabled="depth === 0" :loading="replaying" @click="onReplay">
          <template #icon><n-icon :component="SendOutline" /></template>
          立即补发（replay）
        </n-button>
      </div>
    </div>

    <div class="queue-card glass-card">
      <n-data-table
        :columns="columns" :data="items" :loading="loading"
        :bordered="false" :single-line="false" size="small"
        :pagination="{ pageSize: 15 }"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { h, onMounted, ref } from 'vue'
import {
  NButton, NIcon, NDataTable, NTag, useMessage,
} from 'naive-ui'
import { RefreshOutline, SendOutline } from '@vicons/ionicons5'
import { fetchOfflineQueue, replayOfflineQueue } from '@/api/topology'
import type { OfflineQueueItem } from '@/types/topology'

const message = useMessage()
const items = ref<OfflineQueueItem[]>([])
const depth = ref(0)
const loading = ref(false)
const replaying = ref(false)

async function load() {
  loading.value = true
  try {
    const res = await fetchOfflineQueue(100)
    if (!res.success) {
      message.error(res.message || '加载失败')
      return
    }
    items.value = res.data.items || []
    depth.value = res.data.queued_depth || 0
  } finally {
    loading.value = false
  }
}

async function onReplay() {
  replaying.value = true
  try {
    const res = await replayOfflineQueue()
    if (!res.success) {
      message.error(res.message || '补发失败')
      return
    }
    message.success(`已补发 ${res.data.replayed} 条事件`)
    await load()
  } finally {
    replaying.value = false
  }
}

const columns = [
  { title: '#', key: 'id', width: 70, render: (r: OfflineQueueItem) => h('span', { class: 'mono' }, String(r.id)) },
  { title: '中枢', key: 'hub_id', render: (r: OfflineQueueItem) => h('span', { class: 'mono' }, r.hub_id) },
  { title: '边缘节点', key: 'edge_id', render: (r: OfflineQueueItem) => h('span', { class: 'mono' }, r.edge_id) },
  { title: '通道', key: 'channel', width: 90 },
  { title: 'MQTT 主题', key: 'topic', render: (r: OfflineQueueItem) => h('span', { class: 'mono' }, r.topic) },
  {
    title: '状态', key: 'status', width: 100,
    render: (r: OfflineQueueItem) => h(
      NTag,
      { size: 'small', type: r.status === 'queued' ? 'warning' : 'success', bordered: false },
      { default: () => r.status },
    ),
  },
  { title: '入队时间', key: 'created_at', render: (r: OfflineQueueItem) => fmtTime(r.created_at) },
  {
    title: '送达时间', key: 'delivered_at',
    render: (r: OfflineQueueItem) => r.delivered_at ? fmtTime(r.delivered_at) : '—',
  },
]

function fmtTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

onMounted(load)
</script>

<style scoped>
.queue-page { display: flex; flex-direction: column; gap: 14px; }
.queue-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 18px;
}
.toolbar-title { display: flex; align-items: center; gap: 14px; }
.title-text { font-size: 17px; font-weight: 700; }
.depth-chip {
  font-size: 12px; padding: 3px 11px; border-radius: 999px;
  color: var(--text-secondary); border: 1px solid var(--border-color);
}
.depth-chip.active { color: #ffb020; border-color: rgba(255, 176, 32, 0.4); }
.toolbar-actions { display: flex; gap: 10px; }

.queue-card { padding: 10px 14px 16px; }
:deep(.mono) { font-family: 'JetBrains Mono', Consolas, monospace; font-size: 12px; }
</style>
