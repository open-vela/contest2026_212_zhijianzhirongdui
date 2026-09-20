<template>
  <n-config-provider :theme="naiveTheme" :theme-overrides="themeOverrides">
    <div :class="themeClass" :style="cssVars">
      <router-view />
    </div>
  </n-config-provider>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { NConfigProvider, zhCN, dateZhCN, darkTheme } from 'naive-ui'
import { useAppStore } from '@/stores/app'
import { useVelameshStore } from '@/stores/velamesh'

const appStore = useAppStore()
const velameshStore = useVelameshStore()

const themeClass = computed(() => `theme-${appStore.theme}`)
const isDark = computed(() => appStore.isDark)
const naiveTheme = computed(() => isDark.value ? darkTheme : undefined)

const themeOverrides = computed(() => ({
  common: {
    primaryColor: '#2080f0',
    primaryColorHover: '#4098fc',
    primaryColorPressed: '#1a6ad0',
    borderRadius: appStore.theme === 'glass' ? '24px' : '18px',
  },
}))

const cssVars = computed(() => {
  const glass = appStore.theme === 'glass'
  return {
    '--bg-primary': isDark.value ? '#0a0a0f' : (glass ? '#f5f5f7' : '#f5f0eb'),
    '--bg-secondary': isDark.value ? '#1a1a2e' : (glass ? '#ffffff' : '#ede8e3'),
    '--text-primary': isDark.value ? '#f5f5f7' : (glass ? '#1d1d1f' : '#3c3a38'),
    '--text-secondary': isDark.value ? '#98989d' : (glass ? '#6e6e73' : '#7a7672'),
    '--text-tertiary': isDark.value ? '#636366' : (glass ? '#aeaeb2' : '#a39f9b'),
    '--border-color': isDark.value ? '#2c2c3a' : (glass ? 'rgba(0,0,0,0.08)' : 'rgba(60,58,56,0.12)'),
    '--accent-color': glass ? '#2080f0' : '#d4783c',
    '--card-bg': isDark.value ? 'rgba(26,26,46,0.8)' : (glass ? 'rgba(255,255,255,0.75)' : '#ede8e3'),
    '--glass-bg': glass ? 'rgba(255,255,255,0.65)' : 'transparent',
    '--glass-border': glass ? 'rgba(255,255,255,0.3)' : 'none',
    '--glass-shadow': glass ? '0 8px 32px rgba(0,0,0,0.06)' : 'none',
  }
})

onMounted(() => {
  // 拓扑与决策流 WS：登录后连接、全局复用（未登录不发起，登录页成功后再连）
  if (localStorage.getItem('token')) velameshStore.connect()
})

onUnmounted(() => {
  velameshStore.disconnect()
})
</script>

<style>
/* 全局滚动条 */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--text-tertiary); border-radius: 3px; }

/* 毛玻璃卡片 */
.glass-card {
  background: var(--card-bg);
  border-radius: var(--border-radius);
  border: 1px solid var(--border-color);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  transition: background 0.3s, border-color 0.3s;
}

/* iOS26 Glass 主题 */
.theme-glass {
  --border-radius: 24px;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'PingFang SC', sans-serif;
}

/* HyperOS3 主题 */
.theme-hyperos {
  --border-radius: 18px;
  font-family: 'Misans', 'PingFang SC', 'MiSans', 'Noto Sans SC', sans-serif;
}

.theme-hyperos .glass-card {
  backdrop-filter: none;
  border: 1px solid var(--border-color);
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
</style>
