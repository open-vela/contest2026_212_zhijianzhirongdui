<template>
  <div class="devices-page">
    <div class="page-header">
      <h2 class="page-title">📡 设备管理</h2>
      <n-button type="primary" @click="showRegisterModal = true">
        <template #icon><n-icon :component="AddOutline" /></template>
        注册设备
      </n-button>
    </div>

    <!-- 设备卡片列表 -->
    <n-grid :cols="3" :x-gap="16" :y-gap="16">
      <n-grid-item v-for="dev in devices" :key="dev.id">
        <n-card :bordered="false" class="glass-card device-card" hoverable @click="showDeviceDetail(dev)">
          <div class="device-card-header">
            <div class="device-icon">{{ deviceIcons[dev.device_type] || '📡' }}</div>
            <StatusTag :status="dev.is_online ? 'online' : 'offline'" size="tiny" />
          </div>
          <div class="device-name">{{ dev.name }}</div>
          <div class="device-meta">{{ dev.location }} · {{ dev.node_id }}</div>
          <div class="device-meta">{{ dev.ip_address }} · {{ dev.firmware_ver }}</div>
          <div class="device-time">{{ formatTime(dev.last_seen) }}</div>
        </n-card>
      </n-grid-item>
    </n-grid>

    <!-- 分页 -->
    <div class="pagination-bar" v-if="pagination.total > pagination.pageSize">
      <n-pagination :page="pagination.page" :page-size="pagination.pageSize" :total="pagination.total" :page-slot="5" @update:page="onPageChange" @update:page-size="onPageSizeChange" />
    </div>

    <!-- 注册设备弹窗 -->
    <n-modal v-model:show="showRegisterModal" title="注册新设备" preset="card" style="width: 520px" :bordered="false">
      <n-form :model="regForm" label-placement="left" label-width="100">
        <n-form-item label="节点 ID" path="node_id"><n-input v-model:value="regForm.node_id" placeholder="唯一标识" /></n-form-item>
        <n-form-item label="设备名称"><n-input v-model:value="regForm.name" placeholder="如: 大门摄像头" /></n-form-item>
        <n-form-item label="安装位置"><n-input v-model:value="regForm.location" placeholder="如: 1F 主入口" /></n-form-item>
        <n-form-item label="设备类型"><n-select v-model:value="regForm.device_type" :options="deviceTypeOptions" /></n-form-item>
        <n-form-item label="IP 地址"><n-input v-model:value="regForm.ip_address" placeholder="192.168.1.xxx" /></n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showRegisterModal = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="onRegister">注册</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 设备详情弹窗 -->
    <n-modal v-model:show="showDetailModal" title="设备详情" preset="card" style="width: 640px" :bordered="false">
      <template v-if="detailDevice">
        <n-descriptions label-placement="left" :column="1" bordered size="small">
          <n-descriptions-item label="名称">{{ detailDevice.name }}</n-descriptions-item>
          <n-descriptions-item label="节点 ID">{{ detailDevice.node_id }}</n-descriptions-item>
          <n-descriptions-item label="位置">{{ detailDevice.location }}</n-descriptions-item>
          <n-descriptions-item label="类型">{{ detailDevice.device_type }}</n-descriptions-item>
          <n-descriptions-item label="主板型号">{{ detailDevice.board_model }}</n-descriptions-item>
          <n-descriptions-item label="固件版本">{{ detailDevice.firmware_ver }}</n-descriptions-item>
          <n-descriptions-item label="IP 地址">{{ detailDevice.ip_address }}</n-descriptions-item>
          <n-descriptions-item label="在线状态"><StatusTag :status="detailDevice.is_online ? 'online' : 'offline'" /></n-descriptions-item>
          <n-descriptions-item label="最后心跳">{{ formatTime(detailDevice.last_seen) || '-' }}</n-descriptions-item>
        </n-descriptions>

        <n-divider />
        <n-space>
          <n-button size="small" type="warning" secondary @click="onCommand(detailDevice.id, 'reboot')">重启设备</n-button>
          <n-button size="small" type="info" secondary @click="onCommand(detailDevice.id, 'config_update')">更新配置</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NCard, NGrid, NGridItem, NButton, NInput, NSelect, NModal, NForm, NFormItem, NSpace, NIcon, NPagination, NDivider, NDescriptions, NDescriptionsItem, useMessage } from 'naive-ui'
import { AddOutline } from '@vicons/ionicons5'
import type { Device } from '@/types'
import { getDevices, registerDevice, sendDeviceCommand } from '@/api'
import StatusTag from '@/components/common/StatusTag.vue'

const message = useMessage()

const devices = ref<Device[]>([])
const loading = ref(false)
const showRegisterModal = ref(false)
const showDetailModal = ref(false)
const saving = ref(false)
const detailDevice = ref<Device | null>(null)
const pagination = ref({ page: 1, pageSize: 9, total: 0 })

const deviceIcons: Record<string, string> = { camera: '📷', gate: '🚪', sensor: '📡', lock: '🔒', ble_scanner: '📶' }

const regForm = ref({ node_id: '', name: '', location: '', device_type: 'camera', ip_address: '' })

const deviceTypeOptions = [
  { label: '摄像头', value: 'camera' },
  { label: '门禁', value: 'gate' },
  { label: '传感器', value: 'sensor' },
  { label: '智能锁', value: 'lock' },
  { label: 'BLE 扫描仪', value: 'ble_scanner' },
]

function formatTime(t: string) {
  if (!t) return '-'
  const d = new Date(t)
  const diff = Date.now() - d.getTime()
  if (diff < 60000) return `${Math.floor(diff / 1000)}秒前`
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  return d.toLocaleString('zh-CN')
}

async function loadData() {
  loading.value = true
  try {
    const res = await getDevices(pagination.value.page, pagination.value.pageSize)
    devices.value = res.data.items
    pagination.value.total = res.data.total
  } finally { loading.value = false }
}

function onPageChange(page: number) { pagination.value.page = page; loadData() }
function onPageSizeChange(pageSize: number) { pagination.value.pageSize = pageSize; loadData() }

function showDeviceDetail(dev: Device) {
  detailDevice.value = dev
  showDetailModal.value = true
}

async function onRegister() {
  saving.value = true
  try {
    await registerDevice(regForm.value)
    message.success('设备注册成功')
    showRegisterModal.value = false
    regForm.value = { node_id: '', name: '', location: '', device_type: 'camera', ip_address: '' }
    loadData()
  } finally { saving.value = false }
}

async function onCommand(deviceId: number, cmd: string) {
  const res = await sendDeviceCommand(deviceId, cmd)
  message.success(`指令已下发: ${cmd}`)
}

onMounted(loadData)
</script>

<style scoped>
.devices-page { max-width: 1400px; }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
.page-title { font-size: 22px; }
.device-card { cursor: pointer; transition: transform 0.2s; }
.device-card:hover { transform: translateY(-3px); }
.device-card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.device-icon { font-size: 32px; }
.device-name { font-size: 16px; font-weight: 600; margin-bottom: 4px; }
.device-meta { font-size: 12px; color: var(--text-secondary); line-height: 1.6; }
.device-time { font-size: 11px; color: var(--text-tertiary); margin-top: 8px; }
.pagination-bar { display: flex; justify-content: center; margin-top: 20px; }
</style>
