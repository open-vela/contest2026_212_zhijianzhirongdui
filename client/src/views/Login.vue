<template>
  <div class="login-page" :class="themeClass">
    <div class="login-card glass-card">
      <div class="login-logo">🏢 枢络</div>
      <div class="login-subtitle">智能建筑管理系统</div>

      <n-form :model="form" label-placement="top" style="margin-top: 32px">
        <n-form-item label="用户名">
          <n-input v-model:value="form.username" placeholder="admin" size="large">
            <template #prefix><n-icon :component="PersonOutline" /></template>
          </n-input>
        </n-form-item>
        <n-form-item label="密码">
          <n-input v-model:value="form.password" type="password" show-password-on="click" placeholder="admin123" size="large" @keyup.enter="onLogin">
            <template #prefix><n-icon :component="LockClosedOutline" /></template>
          </n-input>
        </n-form-item>

        <n-space style="display: flex; gap: 12px; margin-top: 24px;">
          <n-button type="primary" size="large" :loading="loading" style="flex: 1" @click="onLogin">
            登录管理端
          </n-button>
          <n-button size="large" style="flex: 1" @click="loginAsEmployee">
            进入员工端
          </n-button>
        </n-space>
      </n-form>

      <div class="login-hint">演示账号: admin / admin123</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { NForm, NFormItem, NInput, NButton, NSpace, NIcon, useMessage } from 'naive-ui'
import { PersonOutline, LockClosedOutline } from '@vicons/ionicons5'
import { login, setToken } from '@/api'
import { useAppStore } from '@/stores/app'

const router = useRouter()
const message = useMessage()
const appStore = useAppStore()

const form = ref({ username: 'admin', password: 'admin123' })
const loading = ref(false)

const themeClass = computed(() => `theme-${appStore.theme}`)

async function onLogin() {
  loading.value = true
  try {
    const res = await login(form.value.username, form.value.password)
    setToken(res.data.token)
    appStore.setUser(res.data.user)
    message.success('登录成功')
    router.push('/admin/dashboard')
  } catch (e: any) {
    message.error('登录失败: ' + (e.message || '未知错误'))
  } finally { loading.value = false }
}

function loginAsEmployee() {
  // 员工端自动登录（演示模式）
  setToken('mock-token-employee')
  appStore.setUser({ id: 1, tenant_id: 1, username: 'zhangsan', display_name: '张三', email: '', is_active: true, role_ids: [3], role_names: ['普通员工'], permissions: ['dashboard:view'], created_at: '' })
  router.push('/employee/home')
}
</script>

<style scoped>
.login-page { display: flex; align-items: center; justify-content: center; min-height: 100vh; background: var(--bg-primary); }
.login-card { width: 400px; padding: 40px; border-radius: 20px; text-align: center; }
.login-logo { font-size: 36px; font-weight: 700; }
.login-subtitle { font-size: 14px; color: var(--text-secondary); margin-top: 8px; }
.login-hint { font-size: 12px; color: var(--text-tertiary); margin-top: 20px; }
</style>
