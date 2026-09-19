import type {
  CloudEvent,
  CloudStatus,
  CloudUploadResult,
  ConnectivityEvidence,
  DemoMode,
  DemoNode,
  DemoOverview,
  GaitEvidence,
  ScoringMetric,
  SeeedMiniaturization,
  SilhouetteEvidence,
} from '@/types/demo'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

const now = () => new Date().toISOString()

const mockOverview: DemoOverview = {
  mode: 'mock',
  updated_at: now(),
  node_count: 3,
  online_node_count: 3,
  telemetry_count: 128,
  topic_root: 'vela/node/+/+',
  services: {
    api: { status: '演练在线', provenance: 'mock' },
    database: { status: '演练在线', engine: 'sqlite', provenance: 'mock' },
    mqtt: { status: '演练在线', broker: '192.168.4.1:1883', provenance: 'mock' },
    cloud: { status: '接口预留', queue_depth: 0, provenance: 'reserved' },
  },
  coverage: {
    ope73_silhouette: 'mock',
    ope75_connectivity: 'mock',
    xiaomi_metrics: 'mock',
    seeed_evidence: 'mock',
    cloud_roundtrip: 'reserved',
  },
  provenance: 'mock',
}

const mockNodes: DemoNode[] = [
  {
    node_id: 'vela-gateway-01', name: 'openvela 网关', role: 'gateway',
    capabilities: ['wifi', 'mqtt', 'ble'], ip: '192.168.4.2', broker: '192.168.4.1:1883',
    online: true, last_heartbeat: now(), age_seconds: 1.2, channels: ['status', 'ble'], provenance: 'mock',
  },
  {
    node_id: 'arduino-face-01', name: '人脸识别节点', role: 'edge_ai',
    capabilities: ['face'], ip: '192.168.4.3', broker: '192.168.4.1:1883',
    online: true, last_heartbeat: now(), age_seconds: 2.1, channels: ['status', 'face'], provenance: 'mock',
  },
  {
    node_id: 'idf-gait-01', name: '剪影步态节点', role: 'edge_ai',
    capabilities: ['silhouette', 'gait'], ip: '192.168.4.4', broker: '192.168.4.1:1883',
    online: true, last_heartbeat: now(), age_seconds: 0.8, channels: ['status', 'silhouette'], provenance: 'mock',
  },
]

const mockSilhouette: SilhouetteEvidence = {
  node_id: 'idf-gait-01', frame_seq: 318, foreground_pixels: 1248,
  width: 80, height: 60, window: { seq_start: 287, seq_end: 318 },
  upload_stats: { uploaded: 24, skipped_empty: 7, suppressed_empty: 3 },
  server_receive: { last_topic: 'vela/node/idf-gait-01/silhouette', received_at: now(), provenance: 'mock' },
  device_log_evidence: { note: '离线演练样例；现场需以串口与 broker 收包为准', provenance: 'mock' },
  provenance: 'mock',
}

const mockGait: GaitEvidence = {
  node_id: 'idf-gait-01',
  identity: '张三',
  score: 0.8721,
  direction: 'forward',
  source: 'gait',
  session_id: 'sess-mock-001',
  latency: 128,
  cosine: 0.8721,
  margin: 0.1432,
  top3: [
    { identity: '张三', score: 0.8721 },
    { identity: '李四', score: 0.7289 },
    { identity: '王五', score: 0.641 },
  ],
  server_receive: { last_topic: 'dominiscius/idf-gait-01/gait/result', received_at: now(), provenance: 'mock' },
  provenance: 'mock',
}

const mockConnectivity: ConnectivityEvidence = {
  node_id: 'vela-gateway-01',
  wifi: { connected: true, ip: '192.168.4.2', rssi: -48, provenance: 'mock' },
  mqtt: { server_connected: true, node_connected: true, broker: '192.168.4.1:1883', provenance: 'mock' },
  ble_devices: [
    { device_id: 'C8:2B:96:AA:01:01', rssi: -57, seen: true, last_seen: now(), scan_seq: 92, publish_status: 'received', provenance: 'mock' },
  ],
  topics: {
    status: 'vela/node/<node_id>/status', ble: 'vela/node/<node_id>/ble',
    silhouette: 'vela/node/<node_id>/silhouette', face: 'vela/node/<node_id>/face', metrics: 'vela/node/<node_id>/metrics',
  },
  reconnect_evidence: { count: 1, last_reconnect_ms: 860, provenance: 'mock' },
  last_received_at: now(), provenance: 'mock',
}

const mockMetrics: ScoringMetric[] = [
  ['discovery', '发现时延', 820, 'ms', 1000, '≤ 1000 ms'],
  ['connection', '连接时延', 1460, 'ms', 3000, '≤ 3000 ms'],
  ['reconnect', '断线重连', 860, 'ms', 5000, '≤ 5000 ms'],
  ['end_to_end', '端到端时延', 138, 'ms', 500, 'P95 ≤ 500 ms'],
  ['reliability', '消息可靠性', 99.4, '%', 99, '≥ 99%'],
  ['multi_device_sync', '多设备同步偏差', 42, 'ms', 100, '≤ 100 ms'],
  ['messages_sent', '消息发送数', 1000, '条', null, '设备累计发送'],
  ['messages_received', '消息接收数', 994, '条', null, '服务端累计接收'],
  ['packet_loss', '丢包率', 0.6, '%', 1, '≤ 1%'],
  ['service_owner', 'Service owner', 'vela-gateway-01', '', null, '设备状态上报'],
  ['active_node', 'Active 节点', 'vela-gateway-01', '', null, '设备状态上报'],
  ['backup_node', 'Backup 节点', 'idf-gait-01', '', null, '设备状态上报'],
  ['service_switch', '服务切换耗时', 540, 'ms', 3000, '≤ 3000 ms'],
  ['interruption', '业务中断时长', 120, 'ms', 1000, '≤ 1000 ms'],
  ['service_migration', '服务流转', true, 'bool', true, '支持跨节点流转'],
  ['cooperative_modalities', '协同感知复杂度', 3, '种', 3, '≥ 3 种模态'],
].map(([key, name, value, unit, target, target_note]) => ({
  key: String(key), name: String(name), value: value as number | boolean | string,
  unit: String(unit), target: target as number | boolean | null, target_note: String(target_note),
  passed: null, source_topic: null, updated_at: now(), provenance: 'mock',
}))

const mockSeeed: SeeedMiniaturization = {
  claimed_dimensions_mm: [45, 22, 8], claimed_volume_cm3: 7.9, claimed_weight_g: 5.3, power_ratio: 15.5,
  physical_verification: 'Mock 申报样例；现场仍需卡尺、电子秤与功耗计复核',
  evidence: [
    { name: '端侧 AI', status: '演练完成', note: '剪影/人脸模块展示样例', provenance: 'mock' },
    { name: '多协议融合', status: '演练完成', note: 'WiFi + MQTT + BLE', provenance: 'mock' },
    { name: '小型化实物', status: '待测量', note: '现场测量前不判定达标', provenance: 'pending_real' },
    { name: '复现文档', status: '接口预留', note: '最终硬件接线后固化', provenance: 'reserved' },
    { name: '演示视频', status: '待录制', note: '硬件闭环后录制', provenance: 'pending_real' },
  ],
  provenance: 'mock',
}

const mockCloudStatus: CloudStatus = {
  ingest: 'local_mock', mode: 'mock', provider: 'local_mock', endpoint_configured: false,
  delivery_worker: 'mock_browser', error_code: null, error_message: null,
  retry_count: 0, queue_depth: 0, last_upload_at: null, last_receive_at: null,
  last_upload_status: null, provenance: 'mock',
}

function modeFromStorage(): DemoMode {
  const requested = localStorage.getItem('demo_mode') || import.meta.env.VITE_DEMO_MODE
  return ['mock', 'local_mqtt', 'cloud_api', 'mixed'].includes(requested)
    ? requested as DemoMode
    : 'local_mqtt'
}

export function getDemoMode(): DemoMode {
  return modeFromStorage()
}

export function setDemoMode(mode: DemoMode): void {
  localStorage.setItem('demo_mode', mode)
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options?.headers as Record<string, string> | undefined) || {}),
  }
  const token = localStorage.getItem('token')
  if (token) headers.Authorization = `Bearer ${token}`
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  const json = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = json?.detail
    throw new Error(typeof detail === 'string' ? detail : detail?.message || `HTTP ${response.status}`)
  }
  return (json?.data ?? json) as T
}

function useMock<T>(mockValue: T, realRequest: () => Promise<T>): Promise<T> {
  return getDemoMode() === 'mock' ? Promise.resolve(structuredClone(mockValue)) : realRequest()
}

export const demoApi = {
  overview: async () => {
    const value = await useMock(mockOverview, () => request<DemoOverview>('/demo/overview'))
    return getDemoMode() === 'mock' ? { ...value, updated_at: now() } : value
  },
  nodes: () => useMock(mockNodes, () => request<DemoNode[]>('/demo/nodes')),
  silhouette: () => useMock(mockSilhouette, () => request<SilhouetteEvidence>('/demo/ope73/silhouette')),
  gait: () => useMock(mockGait, () => request<GaitEvidence>('/demo/ope73/gait')),
  connectivity: () => useMock(mockConnectivity, () => request<ConnectivityEvidence>('/demo/ope75/connectivity')),
  metrics: () => useMock(mockMetrics, () => request<ScoringMetric[]>('/demo/metrics')),
  seeed: () => useMock(mockSeeed, () => request<SeeedMiniaturization>('/demo/seeed-miniaturization')),
  cloudStatus: () => useMock(mockCloudStatus, () => request<CloudStatus>('/cloud/status')),
  cloudEvents: () => getDemoMode() === 'mock' ? Promise.resolve([] as CloudEvent[]) : request<CloudEvent[]>('/cloud/events'),
  uploadCloud: (payload: Record<string, unknown>) => {
    if (getDemoMode() === 'mock') {
      return Promise.resolve<CloudUploadResult>({
        request_id: `mock-${Date.now()}`, status: 'mock_only', cloud_delivered: false,
        endpoint_configured: false, idempotency_key: `browser-mock-${Date.now()}`,
        duplicate: false, provenance: 'mock',
      })
    }
    const idempotencyKey = globalThis.crypto?.randomUUID?.() || `demo-${Date.now()}-${Math.random().toString(16).slice(2)}`
    return request<CloudUploadResult>('/cloud/upload', {
      method: 'POST', body: JSON.stringify({ event_type: 'demo_snapshot', payload, idempotency_key: idempotencyKey }),
    })
  },
}

export function connectDemoEvents(
  onEvent: () => void,
  onState?: (state: string) => void,
  options: { minDelayMs?: number; maxDelayMs?: number } = {},
): () => void {
  if (getDemoMode() === 'mock') {
    onState?.('mock')
    const timer = window.setInterval(onEvent, 8000)
    return () => window.clearInterval(timer)
  }
  const token = localStorage.getItem('token')
  if (!token) {
    onState?.('unauthorized')
    return () => undefined
  }
  const minDelay = Math.max(250, options.minDelayMs ?? 1000)
  const maxDelay = Math.max(minDelay, options.maxDelayMs ?? 30000)
  let stopped = false
  let attempt = 0
  let socket: WebSocket | undefined
  let reconnectTimer: number | undefined
  let stableTimer: number | undefined

  const scheduleReconnect = () => {
    if (stopped || reconnectTimer !== undefined) return
    const exponential = Math.min(maxDelay, minDelay * (2 ** Math.min(attempt, 6)))
    const delay = Math.round(exponential * (0.85 + Math.random() * 0.3))
    attempt += 1
    onState?.('reconnecting')
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = undefined
      connect()
    }, delay)
  }

  const connect = () => {
    if (stopped) return
    onState?.(attempt ? 'reconnecting' : 'connecting')
    const apiUrl = new URL(API_BASE, window.location.origin)
    apiUrl.protocol = apiUrl.protocol === 'https:' ? 'wss:' : 'ws:'
    apiUrl.pathname = '/ws/demo-events'
    apiUrl.search = `token=${encodeURIComponent(token)}`
    socket = new WebSocket(apiUrl)
    socket.onopen = () => {
      onState?.('connected')
      // Reset the backoff only after a genuinely stable connection. A server
      // that repeatedly accepts and immediately closes must not create a
      // one-second reconnect loop.
      if (stableTimer !== undefined) window.clearTimeout(stableTimer)
      stableTimer = window.setTimeout(() => {
        stableTimer = undefined
        attempt = 0
      }, 10000)
    }
    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)
        if (message.type !== 'heartbeat') onEvent()
      } catch { /* malformed transport messages never trigger request loops */ }
    }
    socket.onerror = () => onState?.('error')
    socket.onclose = () => {
      if (stableTimer !== undefined) window.clearTimeout(stableTimer)
      stableTimer = undefined
      socket = undefined
      if (!stopped) {
        onState?.('disconnected')
        scheduleReconnect()
      }
    }
  }

  connect()
  return () => {
    stopped = true
    if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer)
    reconnectTimer = undefined
    if (stableTimer !== undefined) window.clearTimeout(stableTimer)
    stableTimer = undefined
    if (socket) {
      socket.onopen = null
      socket.onmessage = null
      socket.onerror = null
      socket.onclose = null
      socket.close()
      socket = undefined
    }
  }
}
