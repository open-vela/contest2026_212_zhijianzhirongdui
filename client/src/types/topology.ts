// 枢络 VelaMesh — 中枢-边缘拓扑类型（对齐 OPE-100 服务端契约）

export interface EdgeTelemetry {
  rssi?: number
  wifi_rssi?: number
  free_heap?: number
  mem_free?: number
  fps?: number
  light?: number
  temperature?: number
  ip?: string
  battery?: number
  [key: string]: number | string | undefined
}

export interface EdgeNode {
  id: string
  hub_id: string | null
  name: string
  board_model: string
  firmware_ver: string
  is_online: boolean
  last_heartbeat: string | null
  capabilities: string[]
  telemetry: EdgeTelemetry
  registered_at?: string | null
}

export interface HubNode {
  id: string
  name: string
  model: string
  vela_version: string
  firmware_ver: string
  ip_address: string
  is_online: boolean
  cloud_link: 'online' | 'offline' | 'unknown' | string
  last_heartbeat: string | null
  capabilities: string[]
  edges: EdgeNode[]
}

export interface TopologyGraph {
  hubs: HubNode[]
  hub_count: number
  edge_count: number
  offline_queue_depth: number
  mqtt: { mode: string; broker: string }
}

export interface OfflineQueueItem {
  id: number
  hub_id: string
  edge_id: string
  channel: string
  topic: string
  status: string
  created_at: string
  delivered_at: string | null
}

export interface OfflineQueue {
  queued_depth: number
  items: OfflineQueueItem[]
}

// 融合决策（WS type=recognition 的 data 负载）
export interface DecisionWeights {
  ble?: number
  motion?: number
  face?: number
  gait?: number
}

export type DecisionAction = 'allow' | 'deny' | 'alert' | 'degrade'

export interface DecisionItem {
  key: string
  id?: number
  person_id?: number | null
  person_name: string
  node_id: string
  hub_id?: string
  action: DecisionAction | string
  policy_id: string
  scenario?: string
  evidence_mode?: 'delivery' | 'research' | string
  explanation: string
  confidence: number
  fusion_conf?: number
  weights_used: DecisionWeights
  contributions?: Record<string, number>
  receivedAt: number
}

// 节点遥测历史环（sparkline 用）
export interface TelemetryPoint {
  t: number
  rssi?: number
  heap?: number
  fps?: number
}
