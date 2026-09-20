<template>
  <n-layout class="admin-layout" has-sider>
    <!-- 侧边栏 -->
    <n-layout-sider
      :collapsed="collapsed"
      collapse-mode="width"
      :collapsed-width="64"
      :width="220"
      :native-scrollbar="false"
      :class="{ 'ios-glass': theme === 'glass' && !isDark, 'hyperos': theme === 'hyperos' }"
      bordered
    >
      <div class="sidebar-header" @click="collapsed = !collapsed">
        <div v-if="!collapsed" class="logo-text">枢络 <span class="logo-en">VelaMesh</span></div>
        <div v-else class="logo-icon">枢</div>
      </div>
      <n-menu
        :collapsed="collapsed"
        :collapsed-width="64"
        :collapsed-icon-size="22"
        :options="menuOptions"
        :value="activeKey"
        @update:value="onMenuSelect"
      />
    </n-layout-sider>

    <n-layout>
      <!-- 顶部导航 -->
      <n-layout-header class="admin-header" :class="{ 'ios-glass': theme === 'glass' && !isDark }" bordered>
        <div class="header-left">
          <n-button quaternary circle @click="collapsed = !collapsed">
            <template #icon>
              <n-icon :component="collapsed ? MenuOutline : MenuOutline" />
            </template>
          </n-button>
          <n-breadcrumb>
            <n-breadcrumb-item>{{ currentTitle }}</n-breadcrumb-item>
          </n-breadcrumb>
        </div>
        <div class="header-right">
          <n-button quaternary circle @click="toggleTheme">
            <template #icon>
              <n-icon :component="themeIcon" />
            </template>
          </n-button>
          <n-badge :value="alertCount" :max="99">
            <n-button quaternary circle @click="$router.push('/admin/audit')">
              <template #icon>
                <n-icon :component="NotificationsOutline" />
              </template>
            </n-button>
          </n-badge>
          <n-dropdown trigger="click" :options="userMenuOptions" @select="onUserMenuSelect">
            <n-button quaternary>
              <template #icon>
                <n-icon :component="PersonCircleOutline" />
              </template>
              {{ username }}
            </n-button>
          </n-dropdown>
        </div>
      </n-layout-header>

      <!-- 内容区 -->
      <n-layout-content class="admin-content">
        <router-view />
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<script setup lang="ts">
import { ref, computed, h, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { NLayout, NLayoutSider, NLayoutHeader, NLayoutContent, NMenu, NButton, NIcon, NBreadcrumb, NBreadcrumbItem, NBadge, NDropdown, useThemeVars } from 'naive-ui'
import { MenuOutline, MoonOutline, SunnyOutline, NotificationsOutline, PersonCircleOutline, LogOutOutline, SettingsOutline } from '@vicons/ionicons5'
import { useAppStore } from '@/stores/app'
import { getAlertStats } from '@/api'

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()
const collapsed = ref(false)

const theme = computed(() => appStore.theme)
const isDark = computed(() => appStore.isDark)
const username = computed(() => appStore.user?.display_name || '管理员')
const alertCount = computed(() => appStore.alertCount)

const themeIcon = computed(() => (appStore.colorMode === 'dark' ? MoonOutline : SunnyOutline))

function toggleTheme() {
  appStore.toggleColorMode()
}

// 菜单定义 — VelaMesh 控制台：拓扑/决策流为核心镜头，其余管理模块沿用
const menuOptions = computed(() => [
  { label: '拓扑总览', key: '/admin/topology', icon: () => h(NIcon, null, { default: () => h('span', '🛰️') }) },
  { label: '实时决策流', key: '/admin/decisions', icon: () => h(NIcon, null, { default: () => h('span', '📡') }) },
  { label: '离线队列', key: '/admin/queue', icon: () => h(NIcon, null, { default: () => h('span', '🗂️') }) },
  { type: 'divider', key: 'd1' },
  { label: '人员管理', key: '/admin/persons', icon: () => h(NIcon, null, { default: () => h('span', '👤') }) },
  { label: '访客管理', key: '/admin/visitors', icon: () => h(NIcon, null, { default: () => h('span', '🎫') }) },
  { label: '安全审计', key: '/admin/audit', icon: () => h(NIcon, null, { default: () => h('span', '🔍') }) },
  { label: '设备管理', key: '/admin/devices', icon: () => h(NIcon, null, { default: () => h('span', '📟') }) },
  { type: 'divider', key: 'd2' },
  { label: '仪表板', key: '/admin/dashboard', icon: () => h(NIcon, null, { default: () => h('span', '📊') }) },
  { label: '空间管理', key: '/admin/space', icon: () => h(NIcon, null, { default: () => h('span', '🏗️') }) },
  { label: '能源管理', key: '/admin/energy', icon: () => h(NIcon, null, { default: () => h('span', '⚡') }) },
  { label: '竞赛演示', key: '/admin/demo', icon: () => h(NIcon, null, { default: () => h('span', '🏆') }) },
  { label: '系统设置', key: '/admin/settings', icon: () => h(NIcon, null, { default: () => h('span', '⚙️') }) },
])

const activeKey = computed(() => route.path)

const currentTitle = computed(() => {
  const m = menuOptions.value.find((o) => o.key === route.path)
  return m?.label || '枢络管理端'
})

const userMenuOptions = [
  { label: '系统设置', key: 'settings', icon: () => h(SettingsOutline) },
  { label: '退出登录', key: 'logout', icon: () => h(LogOutOutline) },
]

function onMenuSelect(key: string) {
  router.push(key)
}

async function onUserMenuSelect(key: string) {
  if (key === 'logout') {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    router.push('/login')
  } else if (key === 'settings') {
    router.push('/admin/settings')
  }
}

onMounted(async () => {
  try {
    const res = await getAlertStats()
    if (res.success) appStore.alertCount = res.data.unresolved || 0
  } catch { /* ignore */ }
})
</script>

<style scoped>
.admin-layout { height: 100vh; }
.sidebar-header { height: 56px; display: flex; align-items: center; justify-content: center; cursor: pointer; border-bottom: 1px solid var(--border-color); }
.logo-text { font-size: 19px; font-weight: 700; letter-spacing: 1px; }
.logo-en { font-size: 13px; font-weight: 600; color: var(--accent-color); margin-left: 4px; letter-spacing: 0.5px; }
.logo-icon { font-size: 24px; }
.admin-header { height: 56px; display: flex; align-items: center; justify-content: space-between; padding: 0 20px; border-bottom: 1px solid var(--border-color); }
.header-left, .header-right { display: flex; align-items: center; gap: 12px; }
.admin-content { padding: 24px; height: calc(100vh - 56px); overflow-y: auto; }
.ios-glass { background: rgba(255,255,255,0.85); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); }
</style>
