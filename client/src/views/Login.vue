<template>
  <div class="login-page" :class="themeClass">
    <div class="login-bg-grid"></div>
    <div class="login-card glass-card">
      <div class="login-logo">枢络 <span class="login-logo-en">VelaMesh</span></div>
      <div class="login-subtitle">中枢-边缘 · 分布式无感感知与可解释访问控制</div>

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
            登录控制台
          </n-button>
        </n-space>
      </n-form>

      <div class="login-hint">演示账号 admin / admin123 · R528 中枢 + ESP32-S3 边缘节点</div>
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
import { useVelameshStore } from '@/stores/velamesh'

const router = useRouter()
const message = useMessage()
const appStore = useAppStore()
const velameshStore = useVelameshStore()

const form = ref({ username: 'admin', password: 'admin123' })
const loading = ref(false)

const themeClass = computed(() => `theme-${appStore.theme}`)

async function onLogin() {
  loading.value = true
  try {
    const res = await login(form.value.username, form.value.password)
    if (!res.success) {
      message.error(res.message || '登录失败')
      return
    }
    setToken(res.data.token)
    appStore.setUser(res.data.user)
    velameshStore.connect()
    message.success('登录成功')
    router.push('/admin/topology')
  } catch (e: any) {
    message.error('登录失败: ' + (e?.message || '未知错误'))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  overflow: hidden;
  background: radial-gradient(1200px 600px at 70% -10%, rgba(32, 128, 240, 0.18), transparent 60%),
    radial-gradient(900px 500px at 10% 110%, rgba(88, 166, 255, 0.10), transparent 60%), #0a0a0f;
}
.login-bg-grid {
  position: absolute;
  inset: 0;
  background-image: linear-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.04) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: radial-gradient(circle at 50% 40%, black, transparent 75%);
}
.login-card {
  position: relative;
  width: 420px;
  padding: 44px 40px;
  border-radius: 24px;
  text-align: center;
  background: rgba(22, 24, 38, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.5);
}
.login-logo { font-size: 34px; font-weight: 700; letter-spacing: 2px; color: #f5f5f7; }
.login-logo-en { font-size: 22px; font-weight: 600; color: #7dc4ff; letter-spacing: 1px; margin-left: 6px; }
.login-subtitle { font-size: 13px; color: #98989d; margin-top: 10px; line-height: 1.6; }
.login-hint { font-size: 12px; color: #636366; margin-top: 22px; }
</style>
