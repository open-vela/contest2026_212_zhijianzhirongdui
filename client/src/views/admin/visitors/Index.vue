<template>
  <div class="visitors-page">
    <div class="page-header">
      <h2 class="page-title">🎫 访客管理</h2>
      <n-button type="primary" @click="showBookingModal = true">
        <template #icon><n-icon :component="CalendarOutline" /></template>
        新建预约
      </n-button>
    </div>

    <!-- 统计卡片 -->
    <n-grid :cols="5" :x-gap="16" :y-gap="16" class="stat-grid">
      <n-grid-item><n-card :bordered="false" class="glass-card stat-card"><div class="stat-num warn">{{ stats.pending }}</div><div class="stat-label">待审批</div></n-card></n-grid-item>
      <n-grid-item><n-card :bordered="false" class="glass-card stat-card"><div class="stat-num success">{{ stats.approved }}</div><div class="stat-label">已批准</div></n-card></n-grid-item>
      <n-grid-item><n-card :bordered="false" class="glass-card stat-card"><div class="stat-num info">{{ stats.checked_in }}</div><div class="stat-label">已签到</div></n-card></n-grid-item>
      <n-grid-item><n-card :bordered="false" class="glass-card stat-card"><div class="stat-num default">{{ stats.checked_out }}</div><div class="stat-label">已签出</div></n-card></n-grid-item>
      <n-grid-item><n-card :bordered="false" class="glass-card stat-card"><div class="stat-num error">{{ stats.rejected }}</div><div class="stat-label">已拒绝</div></n-card></n-grid-item>
    </n-grid>

    <!-- 搜索与筛选 -->
    <n-space style="margin-bottom: 16px;">
      <n-input v-model:value="searchKeyword" placeholder="搜索访客姓名/电话" clearable style="width: 240px" />
      <n-select v-model:value="statusFilter" :options="statusOptions" placeholder="状态筛选" clearable style="width: 140px" @update:value="loadData" />
    </n-space>

    <!-- 访客列表 -->
    <n-card :bordered="false" class="glass-card">
      <n-data-table :columns="columns" :data="visitors" :bordered="false" :loading="loading" size="small" :pagination="pagination" @update:page="onPageChange" @update:page-size="onPageSizeChange" />
    </n-card>

    <!-- 新建预约弹窗 -->
    <n-modal v-model:show="showBookingModal" title="新建访客预约" preset="card" style="width: 560px" :bordered="false" :segmented="{ content: true }">
      <n-form :model="bookingForm" label-placement="left" label-width="90">
        <n-form-item label="访客姓名" path="name"><n-input v-model:value="bookingForm.name" placeholder="请输入访客姓名" /></n-form-item>
        <n-form-item label="联系电话"><n-input v-model:value="bookingForm.phone" placeholder="手机号" /></n-form-item>
        <n-form-item label="受访人"><n-input v-model:value="bookingForm.host_name" placeholder="如: 张三" /></n-form-item>
        <n-form-item label="来访事由"><n-input v-model:value="bookingForm.purpose" type="textarea" :rows="2" placeholder="来访目的" /></n-form-item>
        <n-grid :cols="2" :x-gap="16">
          <n-grid-item><n-form-item label="有效期从"><n-date-picker v-model:value="validFrom" type="datetime" clearable /></n-form-item></n-grid-item>
          <n-grid-item><n-form-item label="有效期至"><n-date-picker v-model:value="validUntil" type="datetime" clearable /></n-form-item></n-grid-item>
        </n-grid>
        <n-form-item label="访问区域"><n-select v-model:value="bookingForm.access_level" :options="[{ label: '普通区域', value: 1 }, { label: '敏感区域', value: 2 }, { label: '全区域', value: 3 }]" /></n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showBookingModal = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="onCreateBooking">提交预约</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 详情弹窗 -->
    <n-modal v-model:show="showDetailModal" title="访客详情" preset="card" style="width: 520px" :bordered="false">
      <template v-if="detailVisitor">
        <n-steps :current="stepIndex" size="small">
          <n-step title="待审批" />
          <n-step title="已批准" />
          <n-step title="已签到" />
          <n-step title="已签出" />
        </n-steps>
        <n-descriptions label-placement="left" :column="1" bordered size="small" style="margin-top: 16px">
          <n-descriptions-item label="姓名">{{ detailVisitor.name }}</n-descriptions-item>
          <n-descriptions-item label="电话">{{ detailVisitor.phone }}</n-descriptions-item>
          <n-descriptions-item label="受访人">{{ detailVisitor.host_name || '-' }}</n-descriptions-item>
          <n-descriptions-item label="事由">{{ detailVisitor.purpose || '-' }}</n-descriptions-item>
          <n-descriptions-item label="状态"><StatusTag :status="detailVisitor.status as any" /></n-descriptions-item>
          <n-descriptions-item label="签到时间">{{ detailVisitor.check_in_at ? formatTime(detailVisitor.check_in_at) : '-' }}</n-descriptions-item>
          <n-descriptions-item label="签出时间">{{ detailVisitor.check_out_at ? formatTime(detailVisitor.check_out_at) : '-' }}</n-descriptions-item>
        </n-descriptions>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
import { NCard, NDataTable, NButton, NInput, NSelect, NModal, NForm, NFormItem, NGrid, NGridItem, NDatePicker, NSpace, NIcon, NSteps, NStep, NDescriptions, NDescriptionsItem, useMessage } from 'naive-ui'
import { CalendarOutline, EyeOutline, CheckmarkCircleOutline, CloseCircleOutline } from '@vicons/ionicons5'
import type { Visitor } from '@/types'
import { getVisitors, createVisitor, updateVisitorStatus, getVisitorStats } from '@/api'
import StatusTag from '@/components/common/StatusTag.vue'

const message = useMessage()

const visitors = ref<Visitor[]>([])
const loading = ref(false)
const searchKeyword = ref('')
const statusFilter = ref<string | null>(null)
const showBookingModal = ref(false)
const showDetailModal = ref(false)
const saving = ref(false)
const detailVisitor = ref<Visitor | null>(null)
const stats = ref<Record<string, number>>({ pending: 0, approved: 0, checked_in: 0, checked_out: 0, rejected: 0, total: 0 })
const pagination = ref({ page: 1, pageSize: 10, total: 0 })

const validFrom = ref<number | null>(null)
const validUntil = ref<number | null>(null)
const bookingForm = ref({ name: '', phone: '', host_name: '', purpose: '', access_level: 1 })

const statusOptions = [
  { label: '待审批', value: 'pending' },
  { label: '已批准', value: 'approved' },
  { label: '已拒绝', value: 'rejected' },
  { label: '已签到', value: 'checked_in' },
  { label: '已签出', value: 'checked_out' },
]

const stepMap: Record<string, number> = { pending: 0, approved: 1, rejected: 0, checked_in: 2, checked_out: 3 }
const stepIndex = ref(0)

const columns = [
  { title: '姓名', key: 'name', width: 80 },
  { title: '电话', key: 'phone', width: 120 },
  { title: '受访人', key: 'host_name', width: 80 },
  { title: '事由', key: 'purpose', width: 120, ellipsis: { tooltip: true } },
  { title: '有效期', key: 'created_at', width: 120, render: (r: Visitor) => formatTime(r.created_at) },
  { title: '状态', key: 'status', width: 90, render: (r: Visitor) => h(StatusTag, { status: r.status as any, size: 'tiny' }) },
  {
    title: '操作', key: 'actions', width: 200,
    render: (r: Visitor) => h(NSpace, null, {
      default: () => {
        const btns: any[] = [h(NButton, { size: 'tiny', quaternary: true, onClick: () => showDetail(r) }, { default: () => '详情' })]
        if (r.status === 'pending') btns.push(h(NButton, { size: 'tiny', type: 'success', secondary: true, onClick: () => onChangeStatus(r, 'approved') }, { default: () => '批准' }), h(NButton, { size: 'tiny', type: 'error', secondary: true, onClick: () => onChangeStatus(r, 'rejected') }, { default: () => '拒绝' }))
        if (r.status === 'approved') btns.push(h(NButton, { size: 'tiny', type: 'info', secondary: true, onClick: () => onChangeStatus(r, 'checked_in') }, { default: () => '签到' }))
        if (r.status === 'checked_in') btns.push(h(NButton, { size: 'tiny', secondary: true, onClick: () => onChangeStatus(r, 'checked_out') }, { default: () => '签出' }))
        return btns
      },
    }),
  },
]

function formatTime(t: string) { return new Date(t).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) }

async function loadData() {
  loading.value = true
  try {
    const [res, statsRes] = await Promise.all([getVisitors(pagination.value.page, pagination.value.pageSize), getVisitorStats()])
    visitors.value = res.data.items
    pagination.value.total = res.data.total
    stats.value = statsRes.data as any
  } finally { loading.value = false }
}

function onPageChange(page: number) { pagination.value.page = page; loadData() }
function onPageSizeChange(pageSize: number) { pagination.value.pageSize = pageSize; loadData() }

function showDetail(v: Visitor) {
  detailVisitor.value = v
  stepIndex.value = stepMap[v.status] || 0
  showDetailModal.value = true
}

async function onChangeStatus(v: Visitor, status: string) {
  await updateVisitorStatus(v.id, status)
  message.success(`已${status === 'approved' ? '批准' : status === 'rejected' ? '拒绝' : status === 'checked_in' ? '签到' : '签出'}`)
  loadData()
}

async function onCreateBooking() {
  saving.value = true
  try {
    await createVisitor({
      ...bookingForm.value,
      valid_from: validFrom.value ? new Date(validFrom.value).toISOString() : undefined,
      valid_until: validUntil.value ? new Date(validUntil.value).toISOString() : undefined,
    })
    message.success('预约提交成功')
    showBookingModal.value = false
    bookingForm.value = { name: '', phone: '', host_name: '', purpose: '', access_level: 1 }
    validFrom.value = null
    validUntil.value = null
    loadData()
  } finally { saving.value = false }
}

onMounted(loadData)
</script>

<style scoped>
.visitors-page { max-width: 1400px; }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
.page-title { font-size: 22px; }
.stat-grid { margin-bottom: 20px; }
.stat-card { text-align: center; padding: 8px; }
.stat-num { font-size: 28px; font-weight: 700; }
.stat-num.warn { color: #f0a020; }
.stat-num.success { color: #18a058; }
.stat-num.info { color: #2080f0; }
.stat-num.error { color: #d03050; }
.stat-num.default { color: #666; }
.stat-label { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
</style>
