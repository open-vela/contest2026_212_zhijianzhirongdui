<template>
  <div class="employee-layout" :class="themeClass">
    <!-- 顶部导航 -->
    <div class="emp-header" :class="{ 'ios-glass': theme === 'glass' }">
      <div class="emp-header-inner">
        <div class="emp-brand">🏢 枢络 · 员工端</div>
        <div class="emp-header-right">
          <n-button quaternary circle size="small" @click="toggleTheme">
            <template #icon>
              <n-icon :component="themeIcon" />
            </template>
          </n-button>
          <n-avatar round :size="32" color="#18a058">
            {{ userInitial }}
          </n-avatar>
        </div>
      </div>
    </div>

    <!-- 内容区 -->
    <div class="emp-content">
      <router-view />
    </div>

    <!-- 底部 Tab 导航 -->
    <div class="emp-tabbar" :class="{ 'ios-glass': theme === 'glass' }">
      <div
        v-for="tab in tabs"
        :key="tab.key"
        class="tab-item"
        :class="{ active: activeKey === tab.key }"
        @click="router.push(tab.key)"
      >
        <n-icon :size="22"><component :is="tab.icon" /></n-icon>
        <span class="tab-label">{{ tab.label }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { NButton, NIcon, NAvatar } from 'naive-ui'
import { HomeOutline, FingerPrintOutline, CalendarOutline, GridOutline, PulseOutline, BarChartOutline, SunnyOutline, MoonOutline } from '@vicons/ionicons5'
import { useAppStore } from '@/stores/app'

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()

const theme = computed(() => appStore.theme)
const themeClass = computed(() => `theme-${appStore.theme}`)
const colorMode = computed(() => appStore.colorMode)
const themeIcon = computed(() => (colorMode.value === 'dark' ? MoonOutline : SunnyOutline))
const userInitial = computed(() => (appStore.user?.display_name?.charAt(0) || '用'))

function toggleTheme() {
  appStore.toggleColorMode()
}

const tabs = [
  { label: '首页', key: '/employee/home', icon: HomeOutline },
  { label: '身份', key: '/employee/identity', icon: FingerPrintOutline },
  { label: '预约', key: '/employee/booking', icon: CalendarOutline },
  { label: '空间', key: '/employee/space', icon: GridOutline },
  { label: '健康', key: '/employee/health', icon: PulseOutline },
  { label: '数据', key: '/employee/data', icon: BarChartOutline },
]

const activeKey = computed(() => route.path)
</script>

<style scoped>
.employee-layout { min-height: 100vh; padding-bottom: 64px; }
.emp-header { position: sticky; top: 0; z-index: 100; border-bottom: 1px solid var(--border-color); }
.emp-header-inner { max-width: 480px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; height: 52px; padding: 0 16px; }
.emp-brand { font-size: 18px; font-weight: 700; }
.emp-header-right { display: flex; align-items: center; gap: 8px; }
.emp-content { max-width: 480px; margin: 0 auto; padding: 16px; }
.emp-tabbar { position: fixed; bottom: 0; left: 0; right: 0; z-index: 100; display: flex; border-top: 1px solid var(--border-color); background: var(--bg-primary); padding: 4px 0; padding-bottom: max(4px, env(safe-area-inset-bottom)); }
.tab-item { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 6px 0; cursor: pointer; color: var(--text-tertiary); transition: color 0.2s; }
.tab-item.active { color: var(--accent-color); }
.tab-item.active .tab-label { font-weight: 600; }
.tab-label { font-size: 10px; }
.ios-glass { background: rgba(255,255,255,0.9); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); }
</style>
