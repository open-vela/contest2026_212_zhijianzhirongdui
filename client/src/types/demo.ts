export type DataProvenance = 'mock' | 'reserved' | 'pending_real' | 'real'
export type DemoMode = 'mock' | 'local_mqtt' | 'cloud_api' | 'mixed'

export interface EvidenceRef {
  provenance: DataProvenance
}

export interface ServiceEvidence extends EvidenceRef {
  status: string
  broker?: string
  engine?: string
  queue_depth?: number
}

export interface DemoOverview extends EvidenceRef {
  mode: DemoMode
  updated_at: string
  node_count: number
  online_node_count: number
  telemetry_count: number
  topic_root: string
  services: Record<string, ServiceEvidence>
  coverage: Record<string, DataProvenance>
}

export interface DemoNode extends EvidenceRef {
  node_id: string
  name: string
  role: string
  capabilities: string[]
  ip: string
  broker: string
  online: boolean
  last_heartbeat: string | null
  age_seconds: number | null
  channels: string[]
}

export interface SilhouetteEvidence extends EvidenceRef {
  node_id: string | null
  frame_seq: number | null
  foreground_pixels: number | null
  width?: number | null
  height?: number | null
  window: { seq_start: number | null; seq_end: number | null }
  upload_stats: {
    uploaded: number | null
    skipped_empty: number | null
    suppressed_empty: number | null
  }
  server_receive: {
    last_topic: string
    received_at: string | null
    provenance: DataProvenance
  }
  device_log_evidence: { note: string; provenance: DataProvenance }
}

export interface GaitMatch {
  identity: string
  score: number | null
}

export interface GaitEvidence extends EvidenceRef {
  node_id: string | null
  identity: string | null
  score: number | null
  direction: string | null
  source: 'gait'
  session_id: string | null
  latency: number | null
  cosine: number | null
  margin: number | null
  top3: GaitMatch[]
  server_receive: {
    last_topic: string
    received_at: string | null
    provenance: DataProvenance
  }
}

export interface BleEvidence extends EvidenceRef {
  device_id: string
  rssi: number | null
  seen: boolean
  last_seen: string | number | null
  scan_seq: number | null
  publish_status: string
}

export interface ConnectivityEvidence extends EvidenceRef {
  node_id: string | null
  wifi: {
    connected: boolean | string | null
    ip: string | null
    rssi: number | null
    provenance: DataProvenance
  }
  mqtt: {
    server_connected: boolean
    node_connected: boolean | null
    broker: string
    provenance: DataProvenance
  }
  ble_devices: BleEvidence[]
  topics: Record<string, string>
  reconnect_evidence: {
    count: number | null
    last_reconnect_ms: number | null
    provenance: DataProvenance
  }
  last_received_at: string | null
}

export interface ScoringMetric extends EvidenceRef {
  key: string
  name: string
  value: number | boolean | string | null
  unit: string
  target: number | boolean | null
  target_note: string
  passed: boolean | null
  source_topic: string | null
  source_node?: string | null
  updated_at: string | null
}

export interface SeeedEvidenceItem extends EvidenceRef {
  name: string
  status: string
  note: string
}

export interface SeeedMiniaturization extends EvidenceRef {
  claimed_dimensions_mm: number[]
  claimed_volume_cm3: number
  claimed_weight_g: number
  power_ratio: number
  physical_verification: string
  evidence: SeeedEvidenceItem[]
}

export interface CloudStatus extends EvidenceRef {
  ingest: string
  mode: 'disabled' | 'mock' | 'http'
  provider: string
  endpoint_configured: boolean
  delivery_worker: string
  error_code: string | null
  error_message: string | null
  retry_count: number
  queue_depth: number
  last_upload_at: string | null
  last_receive_at: string | null
  last_upload_status: string | null
}

export interface CloudEvent extends EvidenceRef {
  request_id: string
  direction: string
  event_type: string
  status: string
  idempotency_key: string | null
  provider: string
  transport: string
  error_code: string | null
  error_message: string | null
  response_status: number | null
  retry_count: number
  max_retries: number
  next_attempt_at: string | null
  last_attempt_at: string | null
  delivered_at: string | null
  created_at: string
  updated_at: string
}

export interface CloudUploadResult extends EvidenceRef {
  request_id: string
  status: string
  cloud_delivered: boolean
  endpoint_configured: boolean
  idempotency_key: string
  duplicate: boolean
}
