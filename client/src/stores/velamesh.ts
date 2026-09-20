// 枢络 VelaMesh — 实时拓扑 + 决策流 store
// WS /ws/events：type=topology（节点状态）与 type=recognition（融合决策）

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  fetchTopology,
  wsEventsUrl,
} from '@/api/topology'
import type {
  DecisionItem,
  HubNode,
  EdgeNode,
  TelemetryPoint,
  TopologyGraph,
} from '@/types/topology'

const MAX_DECISIONS = 200
const TELEMETRY_RING = 80

export const useVelameshStore = defineStore('velamesh', () => {
  // ── 拓扑 ─────────────────────────────────────────────────────────
  const hubs = ref<HubNode[]>([])
  const mqttInfo = ref<{ mode: string; broker: string }>({ mode: 'unknown', broker: '' })
  const offlineQueueDepth = ref(0)
  const wsConnected = ref(false)
  const lastUpdatedAt = ref<number | null>(null)

  const edges = computed<EdgeNode[]>(() => hubs.value.flatMap((h) => h.edges))
  const edgeCount = computed(() => edges.value.length)
  const onlineEdgeCount = computed(() => edges.value.filter((e) => e.is_online).length)

  function findEdge(id: string): EdgeNode | undefined {
    return edges.value.find((e) => e.id === id)
  }

  // ── 决策流 ───────────────────────────────────────────────────────
  const decisions = ref<DecisionItem[]>([])
  const paused = ref(false)

  // ── 遥测历史环（节点详情 sparkline）────────────────────────────
  const telemetryHistory = ref<Record<string, TelemetryPoint[]>>({})

  async function loadTopology() {
    const res = await fetchTopology()
    if (res.success) applyGraph(res.data)
    return res.success
  }

  function applyGraph(g: TopologyGraph) {
    hubs.value = g.hubs || []
    mqttInfo.value = g.mqtt || mqttInfo.value
    offlineQueueDepth.value = g.offline_queue_depth || 0
    lastUpdatedAt.value = Date.now()
  }

  // ── WS 生命周期 ─────────────────────────────────────────────────
  let socket: WebSocket | null = null
  let reconnectTimer: number | null = null
  let reconnectDelay = 1000
  let closedByUs = false
  let seq = 0
  let pingTimer: number | null = null

  function connect() {
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return
    closedByUs = false
    const ws = new WebSocket(wsEventsUrl())
    socket = ws

    ws.onopen = () => {
      wsConnected.value = true
      reconnectDelay = 1000
      loadTopology().then((ok) => { if (ok) seedTelemetryFromSnapshot() })
      pingTimer = window.setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }))
      }, 25000)
    }

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string)
        if (msg.type === 'pong') return
        if (msg.type === 'topology') onTopologyEvent(msg.data)
        else if (msg.type === 'recognition') onRecognition(msg.data, msg.ts)
      } catch {
        /* ignore malformed frames */
      }
    }

    ws.onclose = () => {
      wsConnected.value = false
      if (pingTimer) { clearInterval(pingTimer); pingTimer = null }
      if (!closedByUs) scheduleReconnect()
    }

    ws.onerror = () => {
      // onclose handles reconnection
      ws.close()
    }
  }

  function scheduleReconnect() {
    if (reconnectTimer !== null) return
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null
      reconnectDelay = Math.min(reconnectDelay * 2, 15000)
      connect()
    }, reconnectDelay)
  }

  function disconnect() {
    closedByUs = true
    if (reconnectTimer !== null) { clearTimeout(reconnectTimer); reconnectTimer = null }
    if (pingTimer) { clearInterval(pingTimer); pingTimer = null }
    socket?.close()
    socket = null
    wsConnected.value = false
  }

  // ── topology 事件增量打补丁 ─────────────────────────────────────
  function onTopologyEvent(data: any) {
    lastUpdatedAt.value = Date.now()
    const event = data?.event
    const hubList = hubs.value

    if (event === 'hub_registered') {
      if (!hubList.some((h) => h.id === data.id)) { loadTopology(); return }
      Object.assign(hubList.find((h) => h.id === data.id)!, data)
    } else if (event === 'hub_deregistered') {
      hubs.value = hubList.filter((h) => h.id !== data.id)
    } else if (event === 'hub_heartbeat') {
      const hub = hubList.find((h) => h.id === data.id)
      if (hub) { hub.is_online = data.is_online ?? true }
      else loadTopology()
    } else if (event === 'cloud_link') {
      const hub = hubList.find((h) => h.id === data.hub_id)
      if (hub) hub.cloud_link = data.cloud_link
    } else if (event === 'offline_replay') {
      offlineQueueDepth.value = 0
      loadTopology()
    } else if (event === 'edge_registered') {
      attachEdge(data, true)
    } else if (event === 'edge_deregistered') {
      detachEdge(data.id)
    } else if (event === 'edge_heartbeat') {
      patchEdgeHeartbeat(data)
    }
  }

  function attachEdge(edge: EdgeNode, _registered: boolean) {
    const hubId = edge.hub_id || hubs.value[0]?.id
    let hub = hubs.value.find((h) => h.id === hubId)
    if (!hub) { loadTopology(); return }
    if (!hub.edges.some((e) => e.id === edge.id)) hub.edges.push(edge)
    else Object.assign(hub.edges.find((e) => e.id === edge.id)!, edge)
  }

  function detachEdge(edgeId: string) {
    for (const hub of hubs.value) {
      if (hub.edges.some((e) => e.id === edgeId)) {
        hub.edges = hub.edges.filter((e) => e.id !== edgeId)
      }
    }
  }

  function patchEdgeHeartbeat(data: any) {
    const edge = findEdge(data.id)
    if (!edge) {
      // 未知节点（可能刚注册）：下一次心跳再打补丁
      loadTopology()
      return
    }
    edge.is_online = data.is_online ?? true
    if (data.telemetry && typeof data.telemetry === 'object') {
      Object.assign(edge.telemetry, data.telemetry)
      pushTelemetry(edge.id, data.telemetry)
    }
  }

  function pushTelemetry(edgeId: string, tel: Record<string, number | undefined>) {
    const ring = telemetryHistory.value[edgeId] || []
    ring.push({
      t: Date.now(),
      rssi: typeof tel.rssi === 'number' ? tel.rssi : undefined,
      heap: typeof tel.free_heap === 'number' ? (tel.free_heap as number) : undefined,
      fps: typeof tel.fps === 'number' ? tel.fps : undefined,
    })
    if (ring.length > TELEMETRY_RING) ring.shift()
    telemetryHistory.value[edgeId] = ring
  }

  function seedTelemetryFromSnapshot() {
    // 首屏全量数据也作为历史的第一个点，sparkline 不至于长时间空白
    for (const edge of edges.value) {
      const tel = edge.telemetry
      if (tel && (tel.rssi !== undefined || tel.free_heap !== undefined || tel.fps !== undefined)) {
        pushTelemetry(edge.id, tel as Record<string, number | undefined>)
      }
    }
  }

  // ── recognition 事件 ────────────────────────────────────────────
  function onRecognition(data: any, ts: number) {
    if (paused.value) return
    const item: DecisionItem = {
      key: `${data.id ?? 'x'}-${seq++}`,
      id: data.id,
      person_id: data.person_id ?? null,
      person_name: data.person_name || '未知人员',
      node_id: data.node_id || '未知节点',
      hub_id: data.hub_id,
      action: data.action || 'deny',
      policy_id: data.policy_id || '',
      scenario: data.scenario,
      evidence_mode: data.evidence_mode,
      explanation: data.explanation || data.explain_text || '',
      confidence: data.confidence ?? data.fusion_conf ?? 0,
      fusion_conf: data.fusion_conf,
      weights_used: data.weights_used || {},
      contributions: data.contributions,
      receivedAt: typeof ts === 'number' ? ts * 1000 : Date.now(),
    }
    decisions.value.unshift(item)
    if (decisions.value.length > MAX_DECISIONS) decisions.value.length = MAX_DECISIONS
  }

  function setPaused(v: boolean) { paused.value = v }
  function clearDecisions() { decisions.value = [] }

  return {
    // state
    hubs, mqttInfo, offlineQueueDepth, wsConnected, lastUpdatedAt,
    edges, edgeCount, onlineEdgeCount,
    decisions, paused, telemetryHistory,
    // actions
    loadTopology, seedTelemetryFromSnapshot,
    connect, disconnect, findEdge,
    setPaused, clearDecisions,
  }
})
