// 枢络 VelaMesh — 拓扑/决策 API（OPE-100 真实后端端点）
// 复用 src/api/index.ts 的请求约定：自动解包 { data, message } wrapper

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

export interface ApiResult<T> {
  success: boolean
  data: T
  message?: string
}

async function request<T>(path: string, options?: RequestInit): Promise<ApiResult<T>> {
  const url = `${API_BASE}${path}`
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string> | undefined),
  }
  const token = localStorage.getItem('token')
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(url, { ...options, headers })
  if (res.status === 204) return { success: res.ok, data: undefined as T }
  const json = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = json?.detail
    const msg =
      typeof detail === 'object' && detail !== null
        ? detail.message || JSON.stringify(detail)
        : detail || json?.message || `HTTP ${res.status}`
    return { success: false, data: json as T, message: msg }
  }
  // FastAPI ResponseWrapper: { data: T, message }
  if (json && typeof json === 'object' && 'data' in json) {
    return { success: true, data: json.data as T, message: json.message }
  }
  return { success: true, data: json as T }
}

// ── 拓扑全图 ─────────────────────────────────────────────────────────
export function fetchTopology() {
  return request<import('@/types/topology').TopologyGraph>('/topology')
}

// ── Hub ──────────────────────────────────────────────────────────────
export function fetchHubs() {
  return request<import('@/types/topology').HubNode[]>('/hubs')
}

export function fetchHub(hubId: string) {
  return request<import('@/types/topology').HubNode>(`/hubs/${encodeURIComponent(hubId)}`)
}

export function sendHubCommand(hubId: string, cmd: string, params: Record<string, unknown> = {}) {
  return request<{ status: string; mqtt_topic: string }>(
    `/hubs/${encodeURIComponent(hubId)}/command`,
    { method: 'POST', body: JSON.stringify({ cmd, params }) },
  )
}

// ── Edge ─────────────────────────────────────────────────────────────
export function fetchEdges(hubId?: string) {
  const qs = hubId ? `?hub_id=${encodeURIComponent(hubId)}` : ''
  return request<import('@/types/topology').EdgeNode[]>(`/edges${qs}`)
}

export function fetchEdge(edgeId: string) {
  return fetchEdges().then((r) => {
    if (!r.success) return r
    const edge = r.data.find((e) => e.id === edgeId)
    return edge
      ? { success: true, data: edge }
      : { success: false, data: undefined as unknown as import('@/types/topology').EdgeNode, message: '边缘节点不存在' }
  })
}

// ── 离线队列 ─────────────────────────────────────────────────────────
export function fetchOfflineQueue(limit = 50) {
  return request<import('@/types/topology').OfflineQueue>(`/offline-queue?limit=${limit}`)
}

export function replayOfflineQueue() {
  return request<{ replayed: number }>('/offline-queue/replay', { method: 'POST' })
}

// ── WebSocket 地址 ───────────────────────────────────────────────────
export function wsEventsUrl(): string {
  const token = localStorage.getItem('token') || ''
  // dev 下经 vite 代理到 8000；生产同源
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}/ws/events?token=${encodeURIComponent(token)}`
}
