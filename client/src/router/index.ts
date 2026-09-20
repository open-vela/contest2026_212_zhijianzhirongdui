import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  // 登录（独立于 Admin/Employee 布局）
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
  },
  // 管理端 — 枢络 VelaMesh 控制台
  {
    path: '/admin',
    component: () => import('@/components/layout/AdminLayout.vue'),
    children: [
      { path: 'topology', name: 'Topology', component: () => import('@/views/admin/topology/Index.vue') },
      { path: 'decisions', name: 'Decisions', component: () => import('@/views/admin/decisions/Index.vue') },
      { path: 'nodes/:id', name: 'NodeDetail', component: () => import('@/views/admin/nodes/Detail.vue') },
      { path: 'queue', name: 'OfflineQueue', component: () => import('@/views/admin/queue/Index.vue') },
      { path: 'dashboard', name: 'Dashboard', component: () => import('@/views/admin/dashboard/Index.vue') },
      { path: 'demo', name: 'CompetitionDemo', component: () => import('@/views/admin/demo/Index.vue') },
      { path: 'persons', name: 'Persons', component: () => import('@/views/admin/persons/Index.vue') },
      { path: 'persons/:id', name: 'PersonDetail', component: () => import('@/views/admin/persons/Detail.vue') },
      { path: 'visitors', name: 'Visitors', component: () => import('@/views/admin/visitors/Index.vue') },
      { path: 'audit', name: 'Audit', component: () => import('@/views/admin/audit/Index.vue') },
      { path: 'devices', name: 'Devices', component: () => import('@/views/admin/devices/Index.vue') },
      { path: 'space', name: 'Space', component: () => import('@/views/admin/space/Index.vue') },
      { path: 'energy', name: 'Energy', component: () => import('@/views/admin/energy/Index.vue') },
      { path: 'settings', name: 'Settings', component: () => import('@/views/admin/settings/Index.vue') },
      { path: '', redirect: '/admin/topology' },
    ],
  },
  // 员工端
  {
    path: '/employee',
    component: () => import('@/components/layout/EmployeeLayout.vue'),
    children: [
      { path: 'home', name: 'EmpHome', component: () => import('@/views/employee/home/Index.vue') },
      { path: 'identity', name: 'EmpIdentity', component: () => import('@/views/employee/identity/Index.vue') },
      { path: 'booking', name: 'EmpBooking', component: () => import('@/views/employee/booking/Index.vue') },
      { path: 'space', name: 'EmpSpace', component: () => import('@/views/employee/space/Index.vue') },
      { path: 'health', name: 'EmpHealth', component: () => import('@/views/employee/health/Index.vue') },
      { path: 'data', name: 'EmpData', component: () => import('@/views/employee/data/Index.vue') },
      { path: '', redirect: '/employee/home' },
    ],
  },
  // 默认重定向到拓扑总览
  { path: '/', redirect: '/admin/topology' },
  { path: '/:pathMatch(.*)*', redirect: '/admin/topology' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫 — 后端有 JWT 认证；仅检查本地 token 存在
router.beforeEach((to) => {
  if (to.path === '/login') return true
  const token = localStorage.getItem('token')
  if (!token && !to.path.startsWith('/employee')) {
    return '/login'
  }
  return true
})

export default router
