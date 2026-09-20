import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import type { User } from '@/types'

export type ThemeId = 'glass' | 'hyperos'
export type ColorMode = 'light' | 'dark' | 'auto'

export const useAppStore = defineStore('app', () => {
  // 主题
  const theme = ref<ThemeId>((localStorage.getItem('theme') as ThemeId) || 'glass')
  // 暗色为默认（演示录屏），首次访问即暗色；auto 仍可日落后切换
  const colorMode = ref<ColorMode>((localStorage.getItem('colorMode') as ColorMode) || 'dark')

  const isDark = computed(() => {
    if (colorMode.value === 'auto') {
      const hour = new Date().getHours()
      // 日落模拟: 18:30 ~ 06:30 为暗色
      return hour < 6 || hour >= 18
    }
    return colorMode.value === 'dark'
  })

  // 用户
  const storedUser = (() => {
    try { return JSON.parse(localStorage.getItem('user') || 'null') } catch { return null }
  })()
  const user = ref<User | null>(storedUser)

  // 告警数
  const alertCount = ref(3)

  function toggleTheme() {
    theme.value = theme.value === 'glass' ? 'hyperos' : 'glass'
    localStorage.setItem('theme', theme.value)
  }

  function toggleColorMode() {
    if (colorMode.value === 'auto') colorMode.value = 'light'
    else if (colorMode.value === 'light') colorMode.value = 'dark'
    else colorMode.value = 'auto'
    localStorage.setItem('colorMode', colorMode.value)
  }

  function setUser(u: User | null) {
    user.value = u
    if (u) localStorage.setItem('user', JSON.stringify(u))
    else localStorage.removeItem('user')
  }

  return { theme, colorMode, isDark, user, alertCount, toggleTheme, toggleColorMode, setUser }
})
