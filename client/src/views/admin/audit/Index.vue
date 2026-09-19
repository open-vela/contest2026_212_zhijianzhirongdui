<template>
  <div class="audit-page">
    <div class="page-header">
      <h2 class="page-title">🔍 安全审计</h2>
    </div>

    <!-- 统计卡片 -->
    <n-grid :cols="5" :x-gap="16" :y-gap="16" class="stat-grid">
      <n-grid-item><n-card :bordered="false" class="glass-card stat-card"><div class="stat-num total">{{ stats.total }}</div><div class="stat-label">总告警</div></n-card></n-grid-item>
      <n-grid-item><n-card :bordered="false" class="glass-card stat-card"><div class="stat-num warn">{{ stats.critical }}</div><div class="stat-label">严重</div></n-card></n-grid-item>
      <n-grid-item><n-card :bordered="false" class="glass-card stat-card"><div class="stat-num info">{{ stats.warning }}</div><div class="stat-label">警告</div></n-card></n-grid-item>
      <n-grid-item><n-card :bordered="false" class="glass-card stat-card"><div class="stat-num success">{{ stats.resolved }}</div><div class="stat-label">已处理</div></n-card></n-grid-item>
      <n-grid-item><n-card :bordered="false" class="glass-card stat-card"><div class="stat-num error">{{ stats.unresolved }}</div><div class="stat-label">未处理</div></n-card></n-grid-item>
    </n-grid>

    <!-- 筛选 -->
    <n-space style="margin-bottom: 16px;">
      <n-select v-model:value="levelFilter" :options="levelOptions" placeholder="级别筛选" clearable style="width: 130px" @update:value="loadData" />
      <n-select v-model:value="resolvedFilter" :options="resolvedOptions" placeholder="状态筛选" clearable style="width: 130px" @update:value="loadData" />
      <n-button @click="loadData"><template #icon><n-icon :component="RefreshOutline" /></template>刷新</n-button>
    </n-space>

    <!-- 告警列表 -->
    <n-card :bordered="false" class="glass-card">
      <n-data-table :columns="columns" :data="alerts" :bordered="false" :loading="loading" size="small" :pagination="pagination" @update:page="onPageChange" @update:page-size="onPageSizeChange" />
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
import { NCard, NDataTable, NButton, NSelect, NSpace, NIcon, NTag, useMessage } from 'naive-ui'
import { RefreshOutline, CheckmarkCircleOutline } from '@vicons/ionicons5'
import type { Alert } from '@/types'
import { getAlerts, resolveAlert, getAlertStats } from '@/api'
import StatusTag from '@/components/common/StatusTag.vue'

const message = useMessage()

const alerts = ref<Alert[]>([])
const loading = ref(false)
const levelFilter = ref<string | null>(null)
const resolvedFilter = ref<string | null>(null)
const stats = ref<Record<string, number>>({ total: 0, critical: 0, warning: 0, info: 0, resolved: 0, unresolved: 0 })
const pagination = ref({ page: 1, pageSize: 10, total: 0 })

const levelOptions = [
  { label: '严重', value: 'critical' },
  { label: '警告', value: 'warning' },
  { label: '信息', value: 'info' },
]

const resolvedOptions = [
  { label: '未处理', value: 'false' },
  { label: '已处理', value: 'true' },
]

const columns = [
  { title: '级别', key: 'level', width: 70, render: (r: Alert) => h(StatusTag, { status: r.level as any, size: 'tiny' }) },
  { title: '标题', key: 'title', width: 220, ellipsis: { tooltip: true } },
  { title: '消息', key: 'message', width: 250, ellipsis: { tooltip: true } },
  { title: '时间', key: 'created_at', width: 140, render: (r: Alert) => formatTime(r.created_at) },
  { title: '状态', key: 'is_resolved', width: 70, render: (r: Alert) => h(NTag, { type: r.is_resolved ? 'success' : 'warning', size: 'tiny', bordered: false }, { default: () => r.is_resolved ? '已处理' : '未处理' }) },
  { title: '处理人', key: 'resolved_by', width: 80, render: (r: Alert) => r.resolved_by || '-' },
  {
    title: '操作', key: 'actions', width: 100,
    render: (r: Alert) => r.is_resolved ? null : h(NButton, { size: 'tiny', type: 'success', secondary: true, onClick: () => onResolve(r) }, { default: () => '标记处理', icon: () => h(CheckmarkCircleOutline) }),
  },
]

function formatTime(t: string) { return new Date(t).toLocaleString('zh-CN') }

async function loadData() {
  loading.value = true
  try {
    const filter: any = {}
    if (levelFilter.value) filter.level = levelFilter.value
    if (resolvedFilter.value !== null) filter.resolved = resolvedFilter.value === 'true'
    const [res, statsRes] = await Promise.all([getAlerts(pagination.value.page, pagination.value.pageSize, filter), getAlertStats()])
    alerts.value = res.data.items
    pagination.value.total = res.data.total
    stats.value = statsRes.data as any
  } finally { loading.value = false }
}

function onPageChange(page: number) { pagination.value.page = page; loadData() }
function onPageSizeChange(pageSize: number) { pagination.value.pageSize = pageSize; loadData() }

async function onResolve(alert: Alert) {
  await resolveAlert(alert.id)
  message.success('告警已标记为已处理')
  loadData()
}

onMounted(loadData)
</script>

<style scoped>
.audit-page { max-width: 1400px; }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
.page-title { font-size: 22px; }
.stat-grid { margin-bottom: 20px; }
.stat-card { text-align: center; padding: 8px; }
.stat-num { font-size: 28px; font-weight: 700; }
.stat-num.total { color: var(--text-primary); }
.stat-num.warn { color: #f0a020; }
.stat-num.info { color: #2080f0; }
.stat-num.success { color: #18a058; }
.stat-num.error { color: #d03050; }
.stat-label { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
</style>
