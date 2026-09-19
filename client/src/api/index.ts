// API 服务层 — A3 真实后端集成
// 对齐 A3 FastAPI 响应格式：
//   ResponseWrapper:  { data: T, message: "ok" }
//   PaginatedResponse: { data: list, pagination: { page, page_size, total, total_pages } }
//   Login 等少数端点返回裸对象（无 wrapper）

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

// 通用请求封装 — 自动解包 FastAPI wrapper 格式
async function request<T>(path: string, options?: RequestInit): Promise<{ success: boolean; data: T; message?: string }> {
  const url = `${API_BASE}${path}`
  const headers: Record<string, string> = { 'Content-Type': 'application/json', ...(options?.headers as Record<string, string> || {}) }
  const token = localStorage.getItem('token')
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(url, { ...options, headers })
  const json = await res.json()
  if (!res.ok) {
    const detail = json?.detail
    const msg = typeof detail === 'object' && detail !== null ? (detail.message || JSON.stringify(detail)) : (detail || json?.message || `HTTP ${res.status}`)
    return { success: false, data: json as any, message: msg }
  }
  if (json && typeof json === 'object') {
    // FastAPI PaginatedResponse: { data: [...], pagination: {...} }
    if ('data' in json && 'pagination' in json) {
      const items = Array.isArray(json.data) ? json.data : []
      return { success: true, data: { items, ...json.pagination } as any, message: 'ok' }
    }
    // FastAPI ResponseWrapper: { data: T, message: "ok" }
    if ('data' in json && 'message' in json) {
      return { success: true, data: json.data as T, message: json.message }
    }
  }
  // Raw response (e.g. login: { access_token, refresh_token, user })
  return { success: true, data: json as T }
}

// ---- 辅助: 类型转换 ----
function toBool(v: number | boolean | undefined | null): boolean {
  if (v === undefined || v === null) return false
  return typeof v === 'boolean' ? v : v === 1
}

function toDateStr(v: string | null | undefined): string {
  if (!v) return ''
  if (v.includes('T')) return v
  return v.replace(' ', 'T') + 'Z'
}

function parseConfig(v: string | object | null | undefined): Record<string, any> {
  if (!v) return {}
  if (typeof v === 'object') return v as Record<string, any>
  try { return JSON.parse(v) } catch { return {} }
}

// ---- Auth ----
export async function login(username: string, password: string, tenantCode = 'default'): Promise<{ success: boolean; data: any; message?: string }> {
  const res = await request<any>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password, tenant_code: tenantCode }),
  })
  if (!res.success) return res
  const d = res.data
  const user = d.user || {}
  return {
    success: true,
    data: {
      token: d.access_token,
      refresh_token: d.refresh_token,
      expires_in: d.expires_in || 3600,
      user: {
        id: user.id,
        tenant_id: user.tenant_id,
        username: user.username,
        display_name: user.display_name || user.username,
        email: user.email || '',
        is_active: true,
        role_ids: [],
        role_names: user.roles || [],
        permissions: user.permissions || [],
        created_at: '',
      },
    },
    message: '登录成功',
  }
}

export async function refreshToken(refreshToken: string): Promise<{ success: boolean; data: any; message?: string }> {
  const res = await request<any>('/auth/refresh', { method: 'POST', body: JSON.stringify({ refresh_token: refreshToken }) })
  if (!res.success) return res
  return { success: true, data: { token: res.data.access_token, expires_in: res.data.expires_in || 3600 }, message: 'ok' }
}

export async function getMe(): Promise<{ success: boolean; data: any }> {
  const res = await request<any>('/auth/me')
  if (!res.success) return res
  const u = res.data
  return {
    success: true,
    data: {
      id: u.id, username: u.username, display_name: u.display_name || u.username,
      email: u.email || '', is_active: true,
      role_ids: [], role_names: u.roles || [], permissions: u.permissions || [],
      tenant_id: u.tenant_id, created_at: '',
    },
  }
}

// ---- Dashboard ----
export async function getDashboardOverview(): Promise<{ success: boolean; data: any }> {
  const res = await request<any>('/dashboard/summary')
  if (!res.success) return res
  const d = res.data
  return {
    success: true,
    data: {
      total_persons: d.today_person_count || 0,
      today_pass_count: d.today_pass_count || 0,
      alert_count: d.alert_count || 0,
      total_devices: d.total_devices || 0,
      online_devices: d.online_devices || 0,
      offline_devices: d.offline_devices || 0,
      device_online_rate: d.device_online_rate || 0,
      active_visitors: d.today_visitor_count || 0,
    },
  }
}

export async function getPassTrend(): Promise<{ success: boolean; data: any[] }> {
  const res = await request<any[]>('/dashboard/trend')
  if (!res.success) return res
  return {
    success: true,
    data: (res.data || []).map((d: any) => ({ time: d.date, count: d.pass_count || 0 })),
  }
}

export async function getDeviceDistribution(): Promise<{ success: boolean; data: any }> {
  const res = await request<any>('/dashboard/device-status')
  if (!res.success) return res
  const d = res.data
  return {
    success: true,
    data: { online: d.online_count || 0, offline: d.offline_count || 0, alert: d.alert_count || 0 },
  }
}

export async function getRecentEvents(): Promise<{ success: boolean; data: any[] }> {
  const res = await request<any[]>('/events/recent?limit=10')
  if (!res.success) return { success: true, data: [] }
  return { success: true, data: Array.isArray(res.data) ? res.data : [] }
}

// ---- Persons ----
export async function getPersons(page = 1, pageSize = 10): Promise<{ success: boolean; data: any }> {
  const res = await request<any>(`/persons?page=${page}&page_size=${pageSize}`)
  if (!res.success) return res
  const d = res.data
  return {
    success: true,
    data: {
      items: (d.items || []).map(adaptPerson),
      total: d.total || 0,
      page: d.page || page,
      page_size: d.page_size || pageSize,
    },
  }
}

export async function getPersonById(id: number): Promise<{ success: boolean; data: any }> {
  const res = await request<any>(`/persons/${id}`)
  if (!res.success) return res
  return { success: true, data: adaptPerson(res.data) }
}

export async function createPerson(data: any): Promise<{ success: boolean; data: any; message?: string }> {
  const res = await request<any>('/persons', { method: 'POST', body: JSON.stringify(data) })
  if (!res.success) return res
  return { success: true, data: adaptPerson(res.data), message: res.message }
}

export async function updatePerson(id: number, data: any): Promise<{ success: boolean; data: any; message?: string }> {
  const res = await request<any>(`/persons/${id}`, { method: 'PUT', body: JSON.stringify(data) })
  if (!res.success) return res
  return { success: true, data: adaptPerson(res.data), message: res.message }
}

export async function deletePerson(id: number): Promise<{ success: boolean; data: any }> {
  return request(`/persons/${id}`, { method: 'DELETE' })
}

export async function searchPersons(keyword: string): Promise<{ success: boolean; data: any[] }> {
  const res = await request<any>(`/persons?search=${encodeURIComponent(keyword)}&page_size=50`)
  if (!res.success) return res
  return { success: true, data: (res.data.items || []).map(adaptPerson) }
}

function adaptPerson(p: any): any {
  return {
    ...p,
    has_face: toBool(p.has_face_registered) || (p.face_count > 0) || false,
    is_active: toBool(p.is_active),
    access_level: p.access_level || 1,
    created_at: toDateStr(p.created_at),
    updated_at: toDateStr(p.updated_at),
  }
}

// ---- Visitors ----
export async function getVisitors(page = 1, pageSize = 10): Promise<{ success: boolean; data: any }> {
  const res = await request<any>(`/visitors?page=${page}&page_size=${pageSize}`)
  if (!res.success) return res
  const d = res.data
  return {
    success: true,
    data: {
      items: (d.items || []).map(adaptVisitor),
      total: d.total || 0,
      page: d.page || page,
      page_size: d.page_size || pageSize,
    },
  }
}

export async function createVisitor(data: any): Promise<{ success: boolean; data: any; message?: string }> {
  // Backend expects: { name, phone, host_person_id, purpose, expected_at, valid_from, valid_until }
  const body = {
    name: data.name,
    phone: data.phone || '',
    host_person_id: data.host_person_id || 1,
    purpose: data.purpose || '',
    expected_at: data.expected_at || new Date().toISOString(),
    valid_from: data.valid_from || data.expected_at || new Date().toISOString(),
    valid_until: data.valid_until || new Date(Date.now() + 86400000).toISOString(),
  }
  const res = await request<any>('/visitors', { method: 'POST', body: JSON.stringify(body) })
  if (!res.success) return res
  return { success: true, data: adaptVisitor(res.data), message: res.message }
}

export async function updateVisitorStatus(id: number, status: string): Promise<{ success: boolean; data: any }> {
  // Map status to appropriate endpoint
  if (status === 'approved') {
    return request(`/visitors/${id}/approve`, { method: 'POST', body: JSON.stringify({ approved_by: 1 }) })
  }
  if (status === 'denied') {
    return request(`/visitors/${id}/deny`, { method: 'POST', body: JSON.stringify({ reason: '' }) })
  }
  if (status === 'checked_in') {
    return request(`/visitors/${id}/check-in`, { method: 'POST' })
  }
  if (status === 'checked_out') {
    return request(`/visitors/${id}/check-out`, { method: 'POST' })
  }
  return request(`/visitors/${id}`, { method: 'PUT', body: JSON.stringify({ status }) })
}

export async function getVisitorStats(): Promise<{ success: boolean; data: any }> {
  // Fetch all visitors in one large page and count locally
  const res = await request<any>('/visitors?page=1&page_size=100')
  if (!res.success) return { success: true, data: { pending: 0, approved: 0, checked_in: 0, checked_out: 0, rejected: 0, total: 0 } }
  const items = res.data.items || []
  return {
    success: true,
    data: {
      pending: items.filter((v: any) => v.status === 'pending').length,
      approved: items.filter((v: any) => v.status === 'approved').length,
      checked_in: items.filter((v: any) => v.status === 'checked_in').length,
      checked_out: items.filter((v: any) => v.status === 'checked_out').length,
      rejected: items.filter((v: any) => v.status === 'denied' || v.status === 'rejected').length,
      total: items.length,
    },
  }
}

function adaptVisitor(v: any): any {
  return {
    id: v.id,
    name: v.name,
    phone: v.phone || '',
    host_name: v.host_name || '',
    purpose: v.purpose || '',
    status: v.status || 'pending',
    person_type: 'visitor',
    access_level: 1,
    employee_id: '',
    department: '',
    email: v.id_card || '',
    tenant_id: 1,
    has_face: false,
    is_active: true,
    check_in_at: v.checked_in_at ? toDateStr(v.checked_in_at) : undefined,
    check_out_at: v.checked_out_at ? toDateStr(v.checked_out_at) : undefined,
    created_at: toDateStr(v.created_at),
    updated_at: toDateStr(v.created_at),
  }
}

// ---- Audit / Alerts ----
export async function getAlerts(page = 1, pageSize = 10, filter?: any): Promise<{ success: boolean; data: any }> {
  let path = `/audit/alerts?page=${page}&page_size=${pageSize}`
  if (filter?.level) path += `&level=${filter.level}`
  if (filter?.resolved !== undefined) path += `&is_resolved=${filter.resolved ? 'true' : 'false'}`
  const res = await request<any>(path)
  if (!res.success) return res
  const d = res.data
  return {
    success: true,
    data: {
      items: (d.items || []).map(adaptAlert),
      total: d.total || 0,
      page: d.page || page,
      page_size: d.page_size || pageSize,
    },
  }
}

export async function resolveAlert(id: number): Promise<{ success: boolean; data: any; message?: string }> {
  const res = await request<any>(`/audit/alerts/${id}/resolve`, { method: 'PATCH', body: JSON.stringify({ resolved_by: 1 }) })
  if (!res.success) return res
  return { success: true, data: adaptAlert(res.data), message: res.message || '告警已处理' }
}

export async function getAlertStats(): Promise<{ success: boolean; data: any }> {
  const res = await request<any>('/audit/alerts?page=1&page_size=100')
  if (!res.success) return res
  const items = res.data.items || []
  return {
    success: true,
    data: {
      total: res.data.total || items.length,
      unresolved: items.filter((a: any) => !a.is_resolved || a.is_resolved === false).length,
      resolved: items.filter((a: any) => a.is_resolved === true).length,
      critical: items.filter((a: any) => a.level === 'critical').length,
      warning: items.filter((a: any) => a.level === 'warning').length,
      info: items.filter((a: any) => a.level === 'info').length,
    },
  }
}

function adaptAlert(a: any): any {
  return {
    ...a,
    is_resolved: toBool(a.is_resolved),
    source_type: a.type || a.source || '',
    created_at: toDateStr(a.created_at),
    resolved_at: a.resolved_at ? toDateStr(a.resolved_at) : undefined,
  }
}

// ---- Audit Logs ----
export async function getAuditLogs(page = 1, pageSize = 10, filter?: any): Promise<{ success: boolean; data: any }> {
  let path = `/audit/logs?page=${page}&page_size=${pageSize}`
  if (filter?.action) path += `&action=${filter.action}`
  if (filter?.user_id) path += `&user_id=${filter.user_id}`
  const res = await request<any>(path)
  if (!res.success) return res
  const d = res.data
  return {
    success: true,
    data: {
      items: (d.items || []).map((l: any) => ({ ...l, created_at: toDateStr(l.created_at) })),
      total: d.total || 0,
      page: d.page || page,
      page_size: d.page_size || pageSize,
    },
  }
}

// ---- Devices ----
export async function getDevices(page = 1, pageSize = 10): Promise<{ success: boolean; data: any }> {
  const res = await request<any>(`/devices?page=${page}&page_size=${pageSize}`)
  if (!res.success) return res
  const d = res.data
  return {
    success: true,
    data: {
      items: (d.items || []).map(adaptDevice),
      total: d.total || 0,
      page: d.page || page,
      page_size: d.page_size || pageSize,
    },
  }
}

export async function getDeviceById(id: number): Promise<{ success: boolean; data: any }> {
  const res = await request<any>(`/devices/${id}`)
  if (!res.success) return res
  return { success: true, data: adaptDevice(res.data) }
}

export async function registerDevice(data: any): Promise<{ success: boolean; data: any }> {
  return request('/devices', { method: 'POST', body: JSON.stringify(data) })
}

export async function sendDeviceCommand(deviceId: number, command: string): Promise<{ success: boolean; data: any }> {
  return request(`/devices/${deviceId}/command`, { method: 'POST', body: JSON.stringify({ command }) })
}

export async function getDeviceStatusHistory(deviceId: number): Promise<{ success: boolean; data: any[] }> {
  const res = await request<any[]>(`/devices/${deviceId}/status/history`)
  if (!res.success) return res
  return { success: true, data: (res.data || []).map((h: any) => ({ ...h, ts: toDateStr(h.ts || h.created_at) })) }
}

function adaptDevice(d: any): any {
  return {
    ...d,
    is_online: toBool(d.is_online),
    config_json: parseConfig(d.config_json),
    last_seen: d.last_seen ? toDateStr(d.last_seen) : '',
    created_at: toDateStr(d.created_at),
  }
}

// ---- Spaces ----
export async function getZones(): Promise<{ success: boolean; data: any[] }> {
  const res = await request<any>('/spaces')
  if (!res.success) return res
  const items = res.data || []
  // Flatten hierarchical spaces to flat zone list for UI
  const zones = items.flatMap((s: any) => {
    if (s.type === 'area' || s.type === 'building') return [adaptZone(s, s.type)]
    if (s.type === 'floor') {
      const children = s.children || []
      return [adaptZone(s, 'floor'), ...children.map((c: any) => adaptZone(c, c.type || 'zone'))]
    }
    return [adaptZone(s, s.type || 'zone')]
  })
  return { success: true, data: zones }
}

export async function getZoneById(id: number): Promise<{ success: boolean; data: any }> {
  const res = await request<any>(`/spaces/${id}`)
  if (!res.success) return res
  return { success: true, data: adaptZone(res.data, res.data.type || 'zone') }
}

function adaptZone(s: any, fallbackType: string): any {
  return {
    id: s.id,
    name: s.name,
    floor: parseInt((s.floor || '0').replace(/\D/g, '') || '0') || 0,
    area: s.area || 0,
    capacity: s.capacity || 0,
    current_occupancy: s.occupancy || 0,
    device_count: 0,
    zone_type: s.type || fallbackType || 'zone',
    status: 'normal',
  }
}

// ---- Energy ----
export async function getEnergyOverview(): Promise<{ success: boolean; data: any }> {
  const res = await request<any>('/energy/summary')
  if (!res.success) return res
  const d = res.data
  return {
    success: true,
    data: {
      total_kwh: d.total_kwh || 0,
      today_kwh: d.total_kwh || 0,
      peak_power_kw: (d.peak_power_w || 0) / 1000,
      avg_power_kw: (d.avg_power_w || 0) / 1000,
    },
  }
}

export async function getEnergyTrend(days = 7): Promise<{ success: boolean; data: any[] }> {
  const res = await request<any[]>(`/energy/trend?days=${days}`)
  if (!res.success) return res
  const data = res.data || []
  return {
    success: true,
    data: data.map((d: any) => ({
      id: 0,
      power_kw: d.avg_power_kw || 0,
      energy_kwh: d.energy_kwh || 0,
      timestamp: d.date,
    })),
  }
}

export async function getEnergyByZone(): Promise<{ success: boolean; data: any[] }> {
  const res = await request<any[]>('/energy/by-area')
  if (!res.success) return res
  return {
    success: true,
    data: (res.data || []).map((item: any) => ({
      zone_name: item.space_name,
      energy_kwh: item.energy_kwh || 0,
      percentage: item.percentage || 0,
    })),
  }
}

// ---- Settings ----
export async function getUsers(page = 1, pageSize = 20): Promise<{ success: boolean; data: any }> {
  const res = await request<any>(`/users?page=${page}&page_size=${pageSize}`)
  if (!res.success) return { success: true, data: { items: [], total: 0, page, page_size: pageSize } }
  const d = res.data
  return {
    success: true,
    data: {
      items: (d.items || []).map((u: any) => ({
        id: u.id, tenant_id: 1,
        username: u.username,
        display_name: u.display_name || u.username,
        email: u.email || '',
        is_active: u.is_active !== false,
        role_ids: [],
        role_names: u.roles || [],
        last_login: u.last_login ? toDateStr(u.last_login) : '',
        permissions: u.permissions || [],
        created_at: toDateStr(u.created_at),
      })),
      total: d.total || 0,
      page: d.page || page,
      page_size: d.page_size || pageSize,
    },
  }
}

export async function createUser(data: any): Promise<{ success: boolean; data: any; message?: string }> {
  return request('/users', { method: 'POST', body: JSON.stringify(data) })
}

export async function updateUser(id: number, data: any): Promise<{ success: boolean; data: any; message?: string }> {
  return request(`/users/${id}`, { method: 'PUT', body: JSON.stringify(data) })
}

export async function deleteUser(id: number): Promise<{ success: boolean; data: any }> {
  return request(`/users/${id}`, { method: 'DELETE' })
}

export async function getRoles(): Promise<{ success: boolean; data: any[] }> {
  const res = await request<any[]>('/roles')
  if (!res.success) return { success: true, data: [] }
  return {
    success: true,
    data: (res.data || []).map((r: any) => ({
      id: r.id, tenant_id: 1,
      name: r.name,
      description: r.description || '',
      is_system: r.is_system || false,
      permission_ids: (r.permissions || []),
      created_at: toDateStr(r.created_at),
    })),
  }
}

export async function createRole(data: any): Promise<{ success: boolean; data: any; message?: string }> {
  return request('/roles', { method: 'POST', body: JSON.stringify(data) })
}

export async function updateRole(id: number, data: any): Promise<{ success: boolean; data: any; message?: string }> {
  return request(`/roles/${id}`, { method: 'PUT', body: JSON.stringify(data) })
}

export async function deleteRole(id: number): Promise<{ success: boolean; data: any }> {
  return request(`/roles/${id}`, { method: 'DELETE' })
}

// ---- Rules ----
export async function getRules(page = 1, pageSize = 10): Promise<{ success: boolean; data: any }> {
  const res = await request<any>(`/rules?page=${page}&page_size=${pageSize}`)
  if (!res.success) return res
  const d = res.data
  return {
    success: true,
    data: {
      items: (d.items || []).map((r: any) => ({ ...r, created_at: toDateStr(r.created_at), trigger_config: parseConfig(r.trigger_config), action_config: parseConfig(r.action_config) })),
      total: d.total || 0,
      page: d.page || page,
      page_size: d.page_size || pageSize,
    },
  }
}

export async function toggleRule(id: number, enabled: boolean): Promise<{ success: boolean; data: any }> {
  return request(`/rules/${id}/toggle`, { method: 'POST', body: JSON.stringify({ is_enabled: enabled }) })
}

// ---- Employee ----
export async function getMyRecognitions(page = 1, pageSize = 20): Promise<{ success: boolean; data: any }> {
  const res = await request<any>(`/recognitions?page=${page}&page_size=${pageSize}`)
  if (!res.success) return { success: true, data: { items: [], total: 0, page, page_size: pageSize } }
  const d = res.data
  return {
    success: true,
    data: {
      items: (d.items || []).map((r: any) => ({
        ...r,
        created_at: toDateStr(r.created_at),
        face_conf: r.face_conf || 0,
        fusion_conf: r.fusion_conf || 0,
      })),
      total: d.total || 0,
      page: d.page || page,
      page_size: d.page_size || pageSize,
    },
  }
}

export async function getMyBookings(): Promise<{ success: boolean; data: any[] }> {
  const res = await request<any>('/visitors?page=1&page_size=100')
  if (!res.success) return { success: true, data: [] }
  return {
    success: true,
    data: (res.data.items || []).filter((v: any) => v.status !== 'checked_out' && v.status !== 'expired'),
  }
}

export async function createBooking(data: any): Promise<{ success: boolean; data: any; message?: string }> {
  return createVisitor(data)
}

export async function getSpaceOccupancy(): Promise<{ success: boolean; data: any[] }> {
  const res = await getZones()
  if (!res.success) return res
  return {
    success: true,
    data: (res.data || [])
      .filter((z) => z.zone_type === 'floor' || z.zone_type === 'room' || z.zone_type === 'area')
      .map((z) => ({
        zone_name: z.name,
        capacity: z.capacity || 50,
        current: z.current_occupancy || 0,
        rate: z.capacity ? (z.current_occupancy || 0) / z.capacity : 0,
      })),
  }
}

export async function getMyHealth(): Promise<{ success: boolean; data: any[] }> {
  // Backend doesn't have a health/wearable endpoint yet — return placeholder
  return { success: true, data: [] }
}

// ---- Token helpers ----
export function getToken(): string | null { return localStorage.getItem('token') }
export function setToken(token: string) { localStorage.setItem('token', token) }
export function clearToken() { localStorage.removeItem('token'); localStorage.removeItem('user') }
