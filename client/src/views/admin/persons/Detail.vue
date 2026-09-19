<template>
  <div class="person-detail" v-if="person">
    <n-button quaternary @click="$router.back()" class="back-btn">
      <template #icon><n-icon :component="ArrowBackOutline" /></template>
      返回
    </n-button>

    <!-- 基础信息卡片 -->
    <n-card :bordered="false" class="glass-card profile-card">
      <div class="profile-header">
        <n-avatar round :size="72" color="#18a058">
          {{ person.name.charAt(0) }}
        </n-avatar>
        <div class="profile-info">
          <div class="profile-name">{{ person.name }}</div>
          <div class="profile-meta">{{ person.employee_id }} · {{ person.department }}</div>
          <div class="profile-tags">
            <StatusTag :status="person.person_type as any" />
            <StatusTag :status="person.is_active ? 'online' : 'offline'" />
          </div>
        </div>
      </div>
    </n-card>

    <!-- 详细信息 -->
    <n-grid :cols="2" :x-gap="16" :y-gap="16">
      <n-grid-item>
        <n-card title="详细信息" :bordered="false" class="glass-card">
          <n-descriptions label-placement="left" :column="1" bordered :size="'small'">
            <n-descriptions-item label="姓名">{{ person.name }}</n-descriptions-item>
            <n-descriptions-item label="工号">{{ person.employee_id }}</n-descriptions-item>
            <n-descriptions-item label="部门">{{ person.department }}</n-descriptions-item>
            <n-descriptions-item label="人员类型">{{ person.person_type }}</n-descriptions-item>
            <n-descriptions-item label="电话">{{ person.phone }}</n-descriptions-item>
            <n-descriptions-item label="邮箱">{{ person.email }}</n-descriptions-item>
            <n-descriptions-item label="BLE MAC">{{ person.ble_mac || '-' }}</n-descriptions-item>
            <n-descriptions-item label="通行级别">{{ { 1: '普通区域', 2: '敏感区域', 3: '全区域' }[person.access_level] }}</n-descriptions-item>
            <n-descriptions-item label="人脸注册">{{ person.has_face ? '✅ 已注册' : '❌ 未注册' }}</n-descriptions-item>
            <n-descriptions-item label="状态">{{ person.is_active ? '正常' : '停用' }}</n-descriptions-item>
            <n-descriptions-item label="创建时间">{{ formatTime(person.created_at) }}</n-descriptions-item>
            <n-descriptions-item label="更新时间">{{ formatTime(person.updated_at) }}</n-descriptions-item>
          </n-descriptions>
        </n-card>
      </n-grid-item>

      <n-grid-item>
        <n-card title="通行记录" :bordered="false" class="glass-card">
          <n-data-table :columns="recogColumns" :data="recognitions" :bordered="false" size="small" :max-height="400" />
        </n-card>
      </n-grid-item>
    </n-grid>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, h } from 'vue'
import { useRoute } from 'vue-router'
import { NCard, NGrid, NGridItem, NDescriptions, NDescriptionsItem, NDataTable, NButton, NIcon, NAvatar } from 'naive-ui'
import { ArrowBackOutline } from '@vicons/ionicons5'
import type { Person, Recognition } from '@/types'
import { getPersonById } from '@/api'
import StatusTag from '@/components/common/StatusTag.vue'

const route = useRoute()
const person = ref<Person | null>(null)
const recognitions = ref<Recognition[]>([])

const recogColumns = [
  { title: '时间', key: 'created_at', render: (r: Recognition) => formatTime(r.created_at) },
  { title: '位置', key: 'node_id' },
  { title: '结果', key: 'decision', render: (r: Recognition) => h(StatusTag, { status: r.decision as any, size: 'tiny' }) },
  { title: '置信度', key: 'fusion_conf', render: (r: Recognition) => `${(r.fusion_conf * 100).toFixed(0)}%` },
]

function formatTime(t: string) {
  return new Date(t).toLocaleString('zh-CN')
}

onMounted(async () => {
  const id = Number(route.params.id)
  const res = await getPersonById(id)
  person.value = res.data
  // Generate some mock recognitions
  recognitions.value = Array.from({ length: 8 }, (_, i) => ({
    id: i, person_id: id, person_name: person.value?.name, node_id: ['主入口', '东门', '12F 会议室', '地下车库'][Math.floor(Math.random() * 4)], face_conf: 0.85, gait_conf: 0.3, ble_conf: 0.5, fusion_conf: +(0.6 + Math.random() * 0.35).toFixed(2), modality_count: Math.floor(Math.random() * 3) + 1, decision: Math.random() > 0.1 ? 'granted' : 'denied' as any, explain_text: '', created_at: new Date(Date.now() - i * 7200000).toISOString(),
  }))
})
</script>

<style scoped>
.person-detail { max-width: 1200px; }
.back-btn { margin-bottom: 16px; }
.profile-card { margin-bottom: 20px; }
.profile-header { display: flex; align-items: center; gap: 20px; }
.profile-info {}
.profile-name { font-size: 22px; font-weight: 700; }
.profile-meta { font-size: 14px; color: var(--text-secondary); margin: 4px 0; }
.profile-tags { display: flex; gap: 8px; margin-top: 8px; }
</style>
