<template>
  <div class="emp-booking">
    <div class="flex items-center justify-between mb-4">
      <h3 class="section-title">📅 预约</h3>
      <n-button type="primary" size="small" @click="showBookingModal = true">新建预约</n-button>
    </div>

    <!-- 预约列表 -->
    <n-card v-for="b in bookings" :key="b.id" :bordered="false" class="glass-card booking-card" size="small">
      <div class="booking-header">
        <div class="booking-title">{{ b.zone_name }}</div>
        <StatusTag :status="b.status as any" size="tiny" />
      </div>
      <div class="booking-meta">
        <span>📅 {{ b.date }}</span>
        <span>🕐 {{ b.start_time }} - {{ b.end_time }}</span>
      </div>
      <div class="booking-purpose">{{ b.purpose }}</div>
    </n-card>

    <n-empty v-if="!bookings.length" description="暂无预约记录" style="margin-top: 40px" />

    <!-- 新建预约 -->
    <n-modal v-model:show="showBookingModal" title="新建预约" preset="card" style="width: 400px" :bordered="false">
      <n-form :model="bookingForm" label-placement="top">
        <n-form-item label="会议室"><n-select v-model:value="bookingForm.zone_id" :options="zoneOptions" /></n-form-item>
        <n-form-item label="日期"><n-date-picker v-model:value="bookingDate" type="date" clearable /></n-form-item>
        <n-grid :cols="2" :x-gap="12">
          <n-grid-item><n-form-item label="开始时间"><n-time-picker v-model:value="startTime" format="HH:mm" /></n-form-item></n-grid-item>
          <n-grid-item><n-form-item label="结束时间"><n-time-picker v-model:value="endTime" format="HH:mm" /></n-form-item></n-grid-item>
        </n-grid>
        <n-form-item label="事由"><n-input v-model:value="bookingForm.purpose" type="textarea" :rows="2" /></n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showBookingModal = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="onSave">提交</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NCard, NButton, NModal, NForm, NFormItem, NSelect, NDatePicker, NTimePicker, NInput, NGrid, NGridItem, NSpace, NEmpty, useMessage } from 'naive-ui'
import type { Booking } from '@/types'
import { getMyBookings, createBooking } from '@/api'
import StatusTag from '@/components/common/StatusTag.vue'

const message = useMessage()
const bookings = ref<Booking[]>([])
const showBookingModal = ref(false)
const saving = ref(false)

const bookingForm = ref({ zone_id: null as number | null, purpose: '' })
const bookingDate = ref<number | null>(null)
const startTime = ref<number | null>(null)
const endTime = ref<number | null>(null)

const zoneOptions = [
  { label: '12F-305 会议室 (容量15人)', value: 4 },
  { label: '12F-308 会议室 (容量10人)', value: 5 },
  { label: '3F 讨论区 (容量25人)', value: 9 },
]

async function load() {
  const res = await getMyBookings()
  bookings.value = res.data
}

async function onSave() {
  saving.value = true
  try {
    const dateStr = bookingDate.value ? new Date(bookingDate.value).toISOString().slice(0, 10) : ''
    const startStr = startTime.value ? new Date(startTime.value).toTimeString().slice(0, 5) : ''
    const endStr = endTime.value ? new Date(endTime.value).toTimeString().slice(0, 5) : ''
    await createBooking({ ...bookingForm.value, date: dateStr, start_time: startStr, end_time: endStr } as any)
    message.success('预约成功')
    showBookingModal.value = false
    load()
  } finally { saving.value = false }
}

onMounted(load)
</script>

<style scoped>
.section-title { font-size: 18px; font-weight: 600; }
.booking-card { margin-bottom: 12px; }
.booking-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.booking-title { font-size: 15px; font-weight: 600; }
.booking-meta { display: flex; gap: 16px; font-size: 12px; color: var(--text-secondary); margin-bottom: 6px; }
.booking-purpose { font-size: 13px; color: var(--text-secondary); }
</style>
