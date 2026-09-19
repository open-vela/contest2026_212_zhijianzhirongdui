<template>
  <div class="emp-identity">
    <h3 class="section-title">🪪 我的身份</h3>

    <!-- 身份卡片 -->
    <n-card :bordered="false" class="glass-card identity-card">
      <div class="id-header">
        <n-avatar round :size="64" color="#2080f0">张</n-avatar>
        <div class="id-badge" v-if="false">已验证</div>
      </div>
      <div class="id-name">张 三</div>
      <div class="id-role">研发部 · 高级工程师</div>
      <div class="id-code">EMP001</div>

      <n-divider />

      <n-descriptions label-placement="left" :column="1" size="small">
        <n-descriptions-item label="部门">研发部</n-descriptions-item>
        <n-descriptions-item label="通行级别">敏感区域</n-descriptions-item>
        <n-descriptions-item label="人脸注册">
          <StatusTag status="online" />
        </n-descriptions-item>
        <n-descriptions-item label="BLE 绑定">
          <StatusTag status="online" />
        </n-descriptions-item>
        <n-descriptions-item label="邮箱">zhangsan@example.com</n-descriptions-item>
        <n-descriptions-item label="电话">138****0001</n-descriptions-item>
      </n-descriptions>
    </n-card>

    <!-- 通行记录 -->
    <n-card title="通行记录" :bordered="false" class="glass-card" size="small" style="margin-top: 16px">
      <n-data-table :columns="passColumns" :data="passRecords" :bordered="false" size="small" :max-height="400" :pagination="{ page: 1, pageSize: 10 }" />
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, h } from 'vue'
import { NCard, NAvatar, NDivider, NDescriptions, NDescriptionsItem, NDataTable } from 'naive-ui'
import type { Recognition } from '@/types'
import { getMyRecognitions } from '@/api'
import StatusTag from '@/components/common/StatusTag.vue'

const passRecords = ref<Recognition[]>([])

const passColumns = [
  { title: '时间', key: 'created_at', render: (r: Recognition) => new Date(r.created_at).toLocaleString('zh-CN') },
  { title: '位置', key: 'node_id' },
  { title: '结果', key: 'decision', render: (r: Recognition) => h(StatusTag, { status: r.decision as any, size: 'tiny' }) },
  { title: '置信度', key: 'fusion_conf', render: (r: Recognition) => `${(r.fusion_conf * 100).toFixed(0)}%` },
]

onMounted(async () => {
  const res = await getMyRecognitions(1, 20)
  passRecords.value = res.data.items
})
</script>

<style scoped>
.emp-identity {}
.section-title { font-size: 18px; font-weight: 600; margin-bottom: 16px; }
.identity-card { text-align: center; padding: 20px; }
.id-header { position: relative; display: inline-block; margin-bottom: 12px; }
.id-badge { position: absolute; bottom: 0; right: -4px; background: #18a058; color: white; font-size: 10px; padding: 1px 6px; border-radius: 8px; }
.id-name { font-size: 22px; font-weight: 700; margin-bottom: 4px; }
.id-role { font-size: 14px; color: var(--text-secondary); margin-bottom: 4px; }
.id-code { font-size: 13px; color: var(--text-tertiary); font-family: monospace; }
</style>
