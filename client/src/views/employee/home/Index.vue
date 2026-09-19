<template>
  <div class="emp-home">
    <!-- 欢迎卡片 -->
    <div class="welcome-card glass-card">
      <div class="welcome-avatar">
        <n-avatar round :size="56" color="#18a058">{{ userInitial }}</n-avatar>
      </div>
      <div class="welcome-text">
        <div class="welcome-greeting">{{ greeting }}，{{ userName }}</div>
        <div class="welcome-status">今日已通行 <strong>{{ todayPass }}</strong> 次</div>
      </div>
    </div>

    <!-- 快捷操作 -->
    <div class="quick-actions">
      <n-button block strong secondary type="primary" @click="$router.push('/employee/booking')">
        <template #icon><n-icon :component="CalendarOutline" /></template>
        预约会议室
      </n-button>
    </div>

    <!-- 最近通行 -->
    <n-card title="最近通行" :bordered="false" class="glass-card" size="small">
      <n-data-table :columns="passColumns" :data="recentPass" :bordered="false" size="small" :max-height="300" />
      <template #footer>
        <n-button text type="primary" @click="$router.push('/employee/identity')">查看全部 →</n-button>
      </template>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { NCard, NButton, NIcon, NAvatar, NDataTable, useThemeVars } from 'naive-ui'
import { CalendarOutline } from '@vicons/ionicons5'
import { getMyRecognitions } from '@/api'
import { useAppStore } from '@/stores/app'
import StatusTag from '@/components/common/StatusTag.vue'

const appStore = useAppStore()
const userName = computed(() => appStore.user?.display_name || '张三')
const userInitial = computed(() => userName.value.charAt(0))
const todayPass = ref(12)

const hours = new Date().getHours()
const greeting = hours < 6 ? '凌晨好' : hours < 9 ? '早上好' : hours < 12 ? '上午好' : hours < 14 ? '中午好' : hours < 18 ? '下午好' : '晚上好'

const recentPass = ref<any[]>([])

const passColumns = [
  { title: '位置', key: 'node_id', width: 100 },
  { title: '时间', key: 'created_at', width: 80, render: (r: any) => new Date(r.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) },
  { title: '结果', key: 'decision', width: 70, render: (r: any) => r.decision === 'granted' ? '✅' : '❌' },
]

onMounted(async () => {
  const res = await getMyRecognitions(1, 5)
  recentPass.value = res.data.items
})
</script>

<style scoped>
.emp-home { padding-bottom: 20px; }
.welcome-card { display: flex; align-items: center; gap: 16px; padding: 20px; border-radius: 16px; margin-bottom: 16px; }
.welcome-greeting { font-size: 18px; font-weight: 600; }
.welcome-status { font-size: 13px; color: var(--text-secondary); margin-top: 4px; }
.quick-actions { margin-bottom: 16px; }
</style>
