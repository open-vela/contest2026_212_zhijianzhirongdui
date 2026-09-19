<template>
  <div class="settings-page">
    <div class="page-header">
      <h2 class="page-title">⚙️ 系统设置</h2>
    </div>

    <n-tabs type="line" default-value="users">
      <!-- 用户管理 -->
      <n-tab-pane name="users" tab="用户管理">
        <n-card :bordered="false" class="glass-card">
          <n-data-table :columns="userColumns" :data="users" :bordered="false" size="small" :max-height="500" />
        </n-card>
      </n-tab-pane>

      <!-- 角色管理 -->
      <n-tab-pane name="roles" tab="角色管理">
        <n-card :bordered="false" class="glass-card">
          <n-data-table :columns="roleColumns" :data="roles" :bordered="false" size="small" :max-height="500" />
        </n-card>
      </n-tab-pane>

      <!-- 权限矩阵 -->
      <n-tab-pane name="permissions" tab="权限矩阵">
        <n-card :bordered="false" class="glass-card">
          <n-table :bordered="false" :single-line="false" size="small">
            <thead>
              <tr>
                <th>权限</th>
                <th v-for="r in roles" :key="r.id">{{ r.name }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in allPermissions" :key="p.code">
                <td><code>{{ p.code }}</code><br><small>{{ p.name }}</small></td>
                <td v-for="r in roles" :key="r.id" style="text-align: center;">
                  <n-icon v-if="r.permission_ids.includes(p.id)" color="#18a058" :component="CheckmarkCircleOutline" size="18" />
                  <span v-else style="color: #ddd">—</span>
                </td>
              </tr>
            </tbody>
          </n-table>
        </n-card>
      </n-tab-pane>

      <!-- 租户配置 -->
      <n-tab-pane name="tenant" tab="租户配置">
        <n-card :bordered="false" class="glass-card">
          <n-descriptions label-placement="left" :column="1" bordered size="small">
            <n-descriptions-item label="租户名称">默认组织</n-descriptions-item>
            <n-descriptions-item label="租户代码">default</n-descriptions-item>
            <n-descriptions-item label="套餐">Enterprise</n-descriptions-item>
            <n-descriptions-item label="最大设备数">100</n-descriptions-item>
            <n-descriptions-item label="最大人员数">500</n-descriptions-item>
            <n-descriptions-item label="人脸匹配阈值">0.55</n-descriptions-item>
            <n-descriptions-item label="心跳超时(秒)">30</n-descriptions-item>
            <n-descriptions-item label="告警保留天数">90</n-descriptions-item>
            <n-descriptions-item label="识别记录保留天数">30</n-descriptions-item>
          </n-descriptions>
        </n-card>
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
import { NCard, NDataTable, NTabs, NTabPane, NTable, NIcon, NTag, NDescriptions, NDescriptionsItem } from 'naive-ui'
import { CheckmarkCircleOutline } from '@vicons/ionicons5'
import type { User, Role } from '@/types'
import { getUsers, getRoles } from '@/api'

const users = ref<User[]>([])
const roles = ref<Role[]>([])

const allPermissions = [
  { id: 1, code: 'person:read', name: '查看人员' },
  { id: 2, code: 'person:write', name: '管理人员' },
  { id: 3, code: 'device:read', name: '查看设备' },
  { id: 4, code: 'device:write', name: '管理设备' },
  { id: 5, code: 'recognition:read', name: '查看通行记录' },
  { id: 6, code: 'alert:read', name: '查看告警' },
  { id: 7, code: 'alert:resolve', name: '处理告警' },
  { id: 8, code: 'rule:write', name: '管理规则' },
  { id: 9, code: 'tenant:admin', name: '租户管理' },
  { id: 10, code: 'dashboard:view', name: '查看大屏' },
  { id: 11, code: 'inference:use', name: '使用推理' },
]

const userColumns = [
  { title: '用户名', key: 'username', width: 100 },
  { title: '显示名', key: 'display_name', width: 100 },
  { title: '邮箱', key: 'email', width: 180 },
  { title: '角色', key: 'role_names', width: 160, render: (r: User) => h('span', r.role_names.join(', ')) },
  { title: '状态', key: 'is_active', width: 60, render: (r: User) => h(NTag, { type: r.is_active ? 'success' : 'default', size: 'tiny', bordered: false }, { default: () => r.is_active ? '正常' : '停用' }) },
  { title: '最后登录', key: 'last_login', width: 140, render: (r: User) => r.last_login ? new Date(r.last_login).toLocaleString('zh-CN') : '-' },
]

const roleColumns = [
  { title: '角色名', key: 'name', width: 120 },
  { title: '描述', key: 'description', width: 200 },
  { title: '系统内置', key: 'is_system', width: 80, render: (r: Role) => h(NTag, { type: r.is_system ? 'info' : 'default', size: 'tiny', bordered: false }, { default: () => r.is_system ? '是' : '否' }) },
  { title: '权限数', key: 'permission_ids', width: 80, render: (r: Role) => r.permission_ids.length },
]

onMounted(async () => {
  const [uRes, rRes] = await Promise.all([getUsers(), getRoles()])
  users.value = uRes.data
  roles.value = rRes.data
})
</script>

<style scoped>
.settings-page { max-width: 1400px; }
.page-header { margin-bottom: 20px; }
.page-title { font-size: 22px; }
</style>
