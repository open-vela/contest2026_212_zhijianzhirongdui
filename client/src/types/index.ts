// API 响应格式（对齐 A3 API-DESIGN.md）
export interface ApiResponse<T = any> {
  success: boolean
  data: T
  message?: string
}

export interface PaginatedResponse<T = any> {
  items: T[]
  total: number
  page: number
  page_size: number
}

// 人员 Person（对齐 persons 表）
export interface Person {
  id: number
  tenant_id: number
  name: string
  employee_id: string
  department: string
  person_type: PersonType
  phone: string
  email: string
  ble_mac: string
  access_level: number
  has_face: boolean
  is_active: boolean
  valid_from?: string
  valid_until?: string
  avatar_url?: string
  created_at: string
  updated_at: string
}

export type PersonType = 'employee' | 'visitor' | 'vip' | 'contractor'

// 访客 Visitor（扩展 Person）
export interface Visitor extends Person {
  person_type: 'visitor'
  host_person_id?: number
  host_name?: string
  purpose?: string
  status: VisitorStatus
  check_in_at?: string
  check_out_at?: string
}

export type VisitorStatus = 'pending' | 'approved' | 'rejected' | 'checked_in' | 'checked_out'

// 设备 Device（对齐 devices 表）
export interface Device {
  id: number
  tenant_id: number
  node_id: string
  name: string
  location: string
  device_type: DeviceType
  board_model: string
  firmware_ver: string
  ip_address: string
  is_online: boolean
  last_seen: string
  config_json: Record<string, any>
  created_at: string
}

export type DeviceType = 'camera' | 'gate' | 'sensor' | 'lock' | 'ble_scanner'

// 识别记录 Recognition（对齐 recognitions 表）
export interface Recognition {
  id: number
  person_id?: number
  person_name?: string
  device_id?: number
  node_id: string
  face_conf: number
  gait_conf: number
  ble_conf: number
  fusion_conf: number
  modality_count: number
  decision: 'granted' | 'denied' | 'pending' | 'unknown'
  explain_text: string
  created_at: string
}

// 告警 Alert（对齐 alerts 表）
export interface Alert {
  id: number
  level: AlertLevel
  title: string
  message: string
  source_type?: string
  source_id?: number
  is_resolved: boolean
  resolved_at?: string
  resolved_by?: string
  created_at: string
}

export type AlertLevel = 'info' | 'warning' | 'critical'

// 规则 Rule（对齐 rules 表）
export interface Rule {
  id: number
  name: string
  description: string
  trigger_type: RuleTriggerType
  condition_json: Record<string, any>
  action_type: RuleActionType
  action_config: Record<string, any>
  is_enabled: boolean
  created_at: string
  updated_at: string
}

export type RuleTriggerType = 'recognition' | 'device_status' | 'time_schedule' | 'alert'
export type RuleActionType = 'mqtt_publish' | 'create_alert' | 'webhook'

// 空间 Zone
export interface Zone {
  id: number
  name: string
  floor: number
  area: number
  capacity: number
  current_occupancy: number
  device_count: number
  zone_type: ZoneType
  status: 'normal' | 'crowded' | 'idle'
}

export type ZoneType = 'office' | 'meeting_room' | 'corridor' | 'entrance' | 'rest_area' | 'utility'

// 能源 Energy
export interface EnergyRecord {
  id: number
  zone_id?: number
  device_id?: number
  power_kw: number
  energy_kwh: number
  timestamp: string
}

// 用户 User
export interface User {
  id: number
  tenant_id: number
  username: string
  display_name: string
  email: string
  is_active: boolean
  role_ids: number[]
  role_names: string[]
  last_login?: string
  permissions: string[]
  created_at: string
}

// 角色 Role
export interface Role {
  id: number
  tenant_id: number
  name: string
  description: string
  is_system: boolean
  permission_ids: number[]
  created_at: string
}

// 仪表板概览
export interface DashboardOverview {
  total_persons: number
  total_devices: number
  today_pass_count: number
  active_visitors: number
  alert_count: number
  online_devices: number
  offline_devices: number
  device_online_rate: number
}

// 通行趋势数据点
export interface TrendDataPoint {
  time: string
  count: number
}

// 设备状态分布
export interface DeviceStatusDistribution {
  online: number
  offline: number
  alert: number
}

// 实时事件（WebSocket 推送格式）
export interface RealtimeEvent {
  id: string
  type: 'recognition' | 'device_status' | 'device_offline' | 'alert_new' | 'alert_resolved'
  data: any
  ts: number
}

// 健康数据
export interface HealthRecord {
  id: number
  person_id: number
  temperature: number
  heart_rate: number
  recorded_at: string
}

// 预约 Booking
export interface Booking {
  id: number
  person_id: number
  person_name: string
  zone_id: number
  zone_name: string
  date: string
  start_time: string
  end_time: string
  status: BookingStatus
  purpose: string
  created_at: string
}

export type BookingStatus = 'pending' | 'approved' | 'rejected' | 'cancelled' | 'completed'
