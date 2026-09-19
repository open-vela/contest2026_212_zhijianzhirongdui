<template>
  <n-tag
    :type="tagType"
    :bordered="false"
    :size="size"
    round
  >
    <template #icon>
      <n-icon :component="iconComponent" />
    </template>
    {{ label }}
  </n-tag>
</template>

<script setup lang="ts">
import { computed, h } from 'vue'
import { NTag, NIcon } from 'naive-ui'
import {
  CheckmarkCircleOutline,
  AlertCircleOutline,
  InformationCircleOutline,
  CloseCircleOutline,
  TimeOutline,
} from '@vicons/ionicons5'

type StatusType = 'online' | 'offline' | 'alert' | 'granted' | 'denied' | 'pending' | 'approved' | 'rejected' | 'checked_in' | 'checked_out' | 'employee' | 'visitor' | 'vip' | 'contractor' | 'normal' | 'warning' | 'critical' | 'idle' | 'crowded'

const props = withDefaults(defineProps<{ status: StatusType; size?: 'small' | 'tiny' | 'medium' }>(), { size: 'small' })

const statusMap: Record<string, { type: 'success' | 'warning' | 'error' | 'info' | 'default'; label: string; icon: any }> = {
  online: { type: 'success', label: '在线', icon: CheckmarkCircleOutline },
  offline: { type: 'error', label: '离线', icon: CloseCircleOutline },
  alert: { type: 'warning', label: '告警', icon: AlertCircleOutline },
  granted: { type: 'success', label: '已通行', icon: CheckmarkCircleOutline },
  denied: { type: 'error', label: '拒绝', icon: CloseCircleOutline },
  pending: { type: 'warning', label: '待处理', icon: TimeOutline },
  approved: { type: 'success', label: '已批准', icon: CheckmarkCircleOutline },
  rejected: { type: 'error', label: '已拒绝', icon: CloseCircleOutline },
  checked_in: { type: 'info', label: '已签到', icon: CheckmarkCircleOutline },
  checked_out: { type: 'default', label: '已签出', icon: TimeOutline },
  employee: { type: 'info', label: '员工', icon: InformationCircleOutline },
  visitor: { type: 'warning', label: '访客', icon: InformationCircleOutline },
  vip: { type: 'success', label: 'VIP', icon: InformationCircleOutline },
  contractor: { type: 'default', label: '承包商', icon: InformationCircleOutline },
  normal: { type: 'success', label: '正常', icon: CheckmarkCircleOutline },
  warning: { type: 'warning', label: '警告', icon: AlertCircleOutline },
  critical: { type: 'error', label: '严重', icon: AlertCircleOutline },
  idle: { type: 'default', label: '空闲', icon: TimeOutline },
  crowded: { type: 'warning', label: '拥挤', icon: AlertCircleOutline },
}

const cfg = computed(() => statusMap[props.status] || statusMap.pending)
const tagType = computed(() => cfg.value.type as any)
const label = computed(() => cfg.value.label)
const iconComponent = computed(() => cfg.value.icon)
</script>
