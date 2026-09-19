<template>
  <div class="persons-page">
    <div class="page-header">
      <h2 class="page-title">👤 人员管理</h2>
      <n-space>
        <n-input v-model:value="searchKeyword" placeholder="搜索姓名/工号/部门/电话" clearable style="width: 280px" @keyup.enter="onSearch" />
        <n-button type="primary" @click="showAddModal = true">
          <template #icon><n-icon :component="PersonAddOutline" /></template>
          新增人员
        </n-button>
      </n-space>
    </div>

    <n-card :bordered="false" class="glass-card">
      <n-data-table
        :columns="columns"
        :data="persons"
        :bordered="false"
        :loading="loading"
        size="small"
        :pagination="pagination"
        @update:page="onPageChange"
        @update:page-size="onPageSizeChange"
      />
    </n-card>

    <!-- 新增/编辑弹窗 -->
    <n-modal v-model:show="showAddModal" :title="editingId ? '编辑人员' : '新增人员'" preset="card" style="width: 640px" :bordered="false" :segmented="{ content: true }">
      <n-form ref="formRef" :model="formData" :rules="rules" label-placement="left" label-width="100" require-mark-placement="right-hanging">
        <n-grid :cols="2" :x-gap="16">
          <n-grid-item><n-form-item label="姓名" path="name"><n-input v-model:value="formData.name" placeholder="请输入姓名" /></n-form-item></n-grid-item>
          <n-grid-item><n-form-item label="工号" path="employee_id"><n-input v-model:value="formData.employee_id" placeholder="请输入工号" /></n-form-item></n-grid-item>
          <n-grid-item><n-form-item label="部门"><n-input v-model:value="formData.department" placeholder="所属部门" /></n-form-item></n-grid-item>
          <n-grid-item><n-form-item label="人员类型"><n-select v-model:value="formData.person_type" :options="typeOptions" /></n-form-item></n-grid-item>
          <n-grid-item><n-form-item label="电话"><n-input v-model:value="formData.phone" placeholder="手机号" /></n-form-item></n-grid-item>
          <n-grid-item><n-form-item label="邮箱"><n-input v-model:value="formData.email" placeholder="邮箱地址" /></n-form-item></n-grid-item>
          <n-grid-item><n-form-item label="通行级别"><n-input-number v-model:value="formData.access_level" :min="1" :max="3" /></n-form-item></n-grid-item>
          <n-grid-item><n-form-item label="BLE MAC"><n-input v-model:value="formData.ble_mac" placeholder="AA:BB:CC:00:00:01" /></n-form-item></n-grid-item>
        </n-grid>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showAddModal = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="onSave">保存</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 删除确认 -->
    <n-modal v-model:show="showDeleteModal" :title="'确认删除'" preset="dialog" type="warning" positive-text="确认删除" negative-text="取消" @positive-click="onDeleteConfirm" @negative-click="showDeleteModal = false">
      <p>确定要删除人员 <strong>{{ deleteTarget?.name }}</strong> 吗？此操作不可恢复。</p>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
import { NCard, NDataTable, NButton, NInput, NModal, NForm, NFormItem, NGrid, NGridItem, NSelect, NInputNumber, NSpace, NIcon, useMessage, NTag } from 'naive-ui'
import { PersonAddOutline, CreateOutline, TrashOutline, SearchOutline, EyeOutline } from '@vicons/ionicons5'
import { useRouter } from 'vue-router'
import type { Person } from '@/types'
import { getPersons, createPerson, updatePerson, deletePerson, searchPersons } from '@/api'

const router = useRouter()
const message = useMessage()

const persons = ref<Person[]>([])
const loading = ref(false)
const searchKeyword = ref('')
const showAddModal = ref(false)
const showDeleteModal = ref(false)
const editingId = ref<number | null>(null)
const saving = ref(false)
const deleteTarget = ref<Person | null>(null)
const pagination = ref({ page: 1, pageSize: 10, total: 0 })

const typeOptions = [
  { label: '员工', value: 'employee' },
  { label: 'VIP', value: 'vip' },
  { label: '访客', value: 'visitor' },
  { label: '承包商', value: 'contractor' },
]

const formData = ref<Partial<Person>>({ name: '', employee_id: '', department: '', person_type: 'employee', phone: '', email: '', access_level: 1, ble_mac: '' })
const rules = { name: { required: true, message: '请输入姓名', trigger: 'blur' }, employee_id: { required: true, message: '请输入工号', trigger: 'blur' } }

const typeStyles: Record<string, string> = { employee: '#2080f0', visitor: '#8050e0', vip: '#f0a020', contractor: '#8050e0' }
const typeLabels: Record<string, string> = { employee: '员工', visitor: '访客', vip: 'VIP', contractor: '承包商' }
const levelLabels: Record<number, string> = { 1: '普通', 2: '敏感区', 3: '全区域' }

function renderActions(r: Person) {
  return h('span', [h('a', { style: 'color:#2080f0;cursor:pointer;margin-right:8px', onClick: () => router.push(`/admin/persons/${r.id}`) }, '详情'),
    h('a', { style: 'margin-right:8px;cursor:pointer', onClick: () => onEdit(r) }, '编辑'),
    h('a', { style: 'color:#d03050;cursor:pointer', onClick: () => onDelete(r) }, '删除')])
}

const columns = [
  { title: '姓名', key: 'name', width: 80, render: (r: Person) => h('a', { style: 'color:#2080f0;cursor:pointer', onClick: () => router.push(`/admin/persons/${r.id}`) }, r.name) },
  { title: '工号', key: 'employee_id', width: 90 },
  { title: '部门', key: 'department', width: 100 },
  { title: '类型', key: 'person_type', width: 80, render: (r: Person) => h('span', { style: `color:${typeStyles[r.person_type] || '#666'}` }, typeLabels[r.person_type] || r.person_type) },
  { title: '电话', key: 'phone', width: 120 },
  { title: '邮箱', key: 'email', width: 160, ellipsis: { tooltip: true } },
  { title: '人脸', key: 'has_face', width: 60, render: (r: Person) => h(NTag, { type: r.has_face ? 'success' : 'default', size: 'tiny', bordered: false }, { default: () => r.has_face ? '已注册' : '未注册' }) },
  { title: '通行级别', key: 'access_level', width: 80, render: (r: Person) => levelLabels[r.access_level] || String(r.access_level) },
  { title: '状态', key: 'is_active', width: 60, render: (r: Person) => h('span', { style: `color:${r.is_active ? '#18a058' : '#d03050'}` }, r.is_active ? '正常' : '停用') },
  { title: '操作', key: 'actions', width: 140, render: renderActions },
]

async function loadData() {
  loading.value = true
  try {
    const res = await getPersons(pagination.value.page, pagination.value.pageSize)
    persons.value = res.data.items
    pagination.value.total = res.data.total
  } finally { loading.value = false }
}

function onPageChange(page: number) { pagination.value.page = page; loadData() }
function onPageSizeChange(pageSize: number) { pagination.value.pageSize = pageSize; loadData() }

async function onSearch() {
  if (!searchKeyword.value.trim()) { loadData(); return }
  const res = await searchPersons(searchKeyword.value)
  persons.value = res.data
  pagination.value.total = res.data.length
}

function onEdit(person: Person) {
  editingId.value = person.id
  formData.value = { ...person }
  showAddModal.value = true
}

function onDelete(person: Person) {
  deleteTarget.value = person
  showDeleteModal.value = true
}

async function onDeleteConfirm() {
  if (!deleteTarget.value) return
  await deletePerson(deleteTarget.value.id)
  message.success('删除成功')
  showDeleteModal.value = false
  loadData()
}

async function onSave() {
  saving.value = true
  try {
    if (editingId.value) {
      await updatePerson(editingId.value, formData.value)
      message.success('更新成功')
    } else {
      await createPerson(formData.value)
      message.success('创建成功')
    }
    showAddModal.value = false
    editingId.value = null
    formData.value = { name: '', employee_id: '', department: '', person_type: 'employee', phone: '', email: '', access_level: 1, ble_mac: '' }
    loadData()
  } finally { saving.value = false }
}

onMounted(loadData)
</script>

<style scoped>
.persons-page { max-width: 1400px; }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
.page-title { font-size: 22px; }
</style>
