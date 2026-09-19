<template>
  <n-data-table
    :columns="columns"
    :data="data"
    :bordered="bordered"
    :single-line="false"
    :size="size"
    :pagination="pagination ? paginationConfig : undefined"
    :loading="loading"
    :row-key="rowKeyFn"
    @update:page="onPageChange"
    @update:page-size="onPageSizeChange"
  />
</template>

<script setup lang="ts">
import { computed, h } from 'vue'
import { NDataTable, NButton, NSpace, NIcon, useThemeVars } from 'naive-ui'
import { AddOutline, RefreshOutline } from '@vicons/ionicons5'

const themeVars = useThemeVars()

const props = withDefaults(defineProps<{
  columns: any[]
  data: any[]
  loading?: boolean
  bordered?: boolean
  size?: 'small' | 'medium' | 'large'
  pagination?: boolean | { page: number; pageSize: number; total: number; pageSizes?: number[] }
  rowKey?: string | ((row: any) => any)
  showToolbar?: boolean
  toolbarTitle?: string
  onAdd?: () => void
  onRefresh?: () => void
}>(), {
  loading: false,
  bordered: false,
  size: 'small',
  pagination: false,
  showToolbar: false,
})

const emit = defineEmits<{
  'update:page': [page: number]
  'update:page-size': [pageSize: number]
}>()

const paginationConfig = computed(() => {
  if (!props.pagination) return false
  if (typeof props.pagination === 'boolean') return { page: 1, pageSize: 10 }
  return {
    page: props.pagination.page,
    pageSize: props.pagination.pageSize,
    total: props.pagination.total,
    pageSizes: props.pagination.pageSizes || [10, 20, 50, 100],
    showSizePicker: true,
    prefix: ({ itemCount }: { itemCount: number | undefined }) => `共 ${itemCount ?? 0} 条`,
  }
})

// NDataTable 要求 rowKey 为 (row) => RowKey 函数；允许调用方传字符串字段名
const rowKeyFn = computed(() => {
  const rk = props.rowKey
  if (!rk) return undefined
  if (typeof rk === 'string') return (row: any) => row[rk]
  return rk
})

function onPageChange(page: number) {
  emit('update:page', page)
}

function onPageSizeChange(pageSize: number) {
  emit('update:page-size', pageSize)
}
</script>
