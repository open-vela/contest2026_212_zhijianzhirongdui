<template>
  <div class="topo-page">
    <!-- 顶部状态条 -->
    <div class="topo-toolbar glass-card">
      <div class="toolbar-title">
        <span class="title-text">中枢-边缘拓扑</span>
        <span class="ws-chip" :class="store.wsConnected ? 'on' : 'off'">
          <i class="dot"></i>{{ store.wsConnected ? 'WS 已连接' : 'WS 断开' }}
        </span>
      </div>
      <div class="toolbar-stats">
        <div class="stat"><label>中枢</label><b>{{ store.hubs.length }}</b></div>
        <div class="stat"><label>边缘在线</label><b>{{ store.onlineEdgeCount }}/{{ store.edgeCount }}</b></div>
        <div class="stat"><label>MQTT</label><b class="mono">{{ store.mqttInfo.mode }}</b></div>
        <div class="stat"><label>离线队列</label><b>{{ store.offlineQueueDepth }}</b></div>
        <n-button size="small" quaternary @click="store.loadTopology()">
          <template #icon><n-icon :component="RefreshOutline" /></template>
          刷新
        </n-button>
      </div>
    </div>

    <!-- 拓扑画布 -->
    <div class="topo-canvas glass-card">
      <svg class="links" viewBox="0 0 100 100" preserveAspectRatio="none">
        <defs>
          <linearGradient id="linkGlow" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stop-color="#2f6fed" />
            <stop offset="100%" stop-color="#58a6ff" />
          </linearGradient>
        </defs>
        <template v-for="(e, i) in edgeLayout" :key="`l-${e.id}`">
          <line
            x1="50" y1="50" :x2="e.x" :y2="e.y"
            :class="['link-base', { offline: !e.is_online }]"
            vector-effect="non-scaling-stroke"
          />
          <line
            v-if="e.is_online"
            x1="50" y1="50" :x2="e.x" :y2="e.y"
            class="link-flow"
            :style="{ animationDelay: `${(i % 5) * 0.4}s` }"
            vector-effect="non-scaling-stroke"
          />
        </template>
        <circle cx="50" cy="50" r="1.4" class="hub-halo" vector-effect="non-scaling-stroke" />
      </svg>

      <!-- Hub 卡片 -->
      <div class="hub-anchor">
        <div v-for="hub in store.hubs" :key="hub.id" class="hub-card">
          <div class="corner-badge">软件栈 · 目标硬件</div>
          <div class="card-head">
            <div class="hub-icon">
              <n-icon :component="HardwareChipOutline" :size="26" />
            </div>
            <div>
              <div class="card-title">{{ hub.name }}</div>
              <div class="card-sub mono">{{ hub.id }}</div>
            </div>
            <span class="state-chip" :class="hub.is_online ? 'on' : 'off'">
              <i class="dot"></i>{{ hub.is_online ? '在线' : '离线' }}
            </span>
          </div>
          <div class="hub-meta">
            <div><label>型号</label><span>{{ hub.model }}</span></div>
            <div><label>openvela</label><span class="mono">{{ hub.vela_version || '—' }}</span></div>
            <div><label>固件</label><span class="mono">{{ hub.firmware_ver || '—' }}</span></div>
            <div><label>云端链路</label><span>{{ cloudText(hub.cloud_link) }}</span></div>
          </div>
          <div class="skill-row">
            <label>运行 Skill</label>
            <div class="chips">
              <span v-for="s in hubSkills(hub)" :key="s" class="skill-chip">
                <n-icon v-if="s === 'edge-node-provisioning'" :component="GitNetworkOutline" :size="13" />
                {{ s }}
              </span>
            </div>
          </div>
          <div class="card-foot">
            最后心跳 {{ timeAgo(hub.last_heartbeat, nowTick) }}
            <span v-if="hub.ip_address" class="mono foot-ip">{{ hub.ip_address }}</span>
          </div>
        </div>

        <div v-if="store.hubs.length === 0" class="hub-card placeholder">
          <n-icon :component="CloudOfflineOutline" :size="30" />
          <div class="ph-title">暂无中枢注册</div>
          <div class="ph-text">请先启动 server，再运行<br />
            <code>python scripts/simulate_edge.py --scenario allow --port 11883</code>
          </div>
          <n-button size="small" type="primary" ghost @click="store.loadTopology()">重新加载</n-button>
        </div>
      </div>

      <!-- Edge 卡片（辐射均布） -->
      <template v-for="(e, i) in edgeLayout" :key="e.id">
        <div
          class="edge-anchor"
          :style="{ left: `${e.x}%`, top: `${e.y}%` }"
        >
          <div class="edge-card" :class="{ off: !e.is_online }" @click="goNode(e.id)">
            <div class="card-head edge-head">
              <div class="edge-icon"><n-icon :component="PulseOutline" :size="18" /></div>
              <div class="edge-title-box">
                <div class="card-title">{{ e.name }}</div>
                <div class="card-sub mono">{{ e.id }}</div>
              </div>
              <span class="state-chip sm" :class="e.is_online ? 'on' : 'off'">
                <i class="dot"></i>{{ e.is_online ? '在线' : '离线' }}
              </span>
            </div>
            <div class="cap-row">
              <span v-for="c in e.capabilities.length ? e.capabilities : ['ble']" :key="c" class="cap-chip">
                <n-icon :component="capIcon(c)" :size="12" /> {{ capText(c) }}
              </span>
            </div>
            <div class="edge-metrics">
              <div class="metric">
                <label>RSSI</label>
                <b>{{ fmtNum(e.telemetry.rssi) }}</b>
                <span class="unit">dBm</span>
              </div>
              <div class="metric">
                <label>帧率</label>
                <b>{{ fmtNum(e.telemetry.fps) }}</b>
                <span class="unit">fps</span>
              </div>
              <div class="metric">
                <label>空闲堆</label>
                <b>{{ heapKb(e.telemetry.free_heap) }}</b>
                <span class="unit">KB</span>
              </div>
            </div>
            <Sparkline
              :values="rssiHistory(e.id)"
              color="#58a6ff"
              :width="210" :height="26"
              :min="-100" :max="-30"
            />
            <div class="card-foot sm">
              心跳 {{ timeAgo(e.last_heartbeat, nowTick) }}
              <span class="go-detail">详情 →</span>
            </div>
          </div>
        </div>
      </template>

      <div v-if="store.edgeCount === 0" class="empty-edge-hint">
        等待边缘节点接入…
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NIcon } from 'naive-ui'
import {
  RefreshOutline, HardwareChipOutline, GitNetworkOutline, CloudOfflineOutline,
  PulseOutline, BluetoothOutline, VideocamOutline, WalkOutline, ScanOutline,
} from '@vicons/ionicons5'
import { useVelameshStore } from '@/stores/velamesh'
import { useNowTick, timeAgo } from '@/composables/useNowTick'
import Sparkline from '@/components/velamesh/Sparkline.vue'
import type { HubNode } from '@/types/topology'

const router = useRouter()
const store = useVelameshStore()
const nowTick = useNowTick()

// 边缘节点沿椭圆辐射均布；与 SVG 连线共用同一几何（viewBox 100x100）。
// RX/RY 预留卡片自身宽高的占位，避免卡片超出画布被裁切。
const RX = 35
const RY = 34

const edgeLayout = computed(() => {
  const list = store.edges
  const n = list.length
  return list.map((e, i) => {
    // 1 节点放右侧；2 节点左右对称；多节点从 -90° 起均分整圆
    let angle: number
    if (n === 1) angle = 0
    else if (n === 2) angle = i === 0 ? 0 : Math.PI
    else angle = -Math.PI / 2 + (i * 2 * Math.PI) / n
    return {
      ...e,
      x: Number((50 + RX * Math.cos(angle)).toFixed(2)),
      y: Number((50 + RY * Math.sin(angle)).toFixed(2)),
    }
  })
})

function hubSkills(hub: HubNode): string[] {
  const skills = ['edge-node-provisioning', ...hub.capabilities]
  return Array.from(new Set(skills))
}

function cloudText(v: string): string {
  if (v === 'online') return '在线'
  if (v === 'offline') return '离线（本地缓存）'
  return '未知'
}

function capText(c: string): string {
  return ({ face: '人脸', gait: '步态', ble: 'BLE', camera: '摄像头' } as Record<string, string>)[c] || c
}

function capIcon(c: string) {
  return ({
    face: ScanOutline, gait: WalkOutline, ble: BluetoothOutline, camera: VideocamOutline,
  } as Record<string, unknown>)[c] as typeof BluetoothOutline || BluetoothOutline
}

function fmtNum(v: number | string | undefined): string {
  if (typeof v !== 'number') return '—'
  return Number.isInteger(v) ? String(v) : v.toFixed(1)
}

function heapKb(v: number | undefined): string {
  if (typeof v !== 'number') return '—'
  return String(Math.round(v / 1024))
}

function rssiHistory(edgeId: string): number[] {
  return (store.telemetryHistory[edgeId] || [])
    .map((p) => p.rssi)
    .filter((v): v is number => typeof v === 'number')
}

function goNode(id: string) {
  router.push(`/admin/nodes/${encodeURIComponent(id)}`)
}
</script>

<style scoped>
.topo-page { display: flex; flex-direction: column; gap: 14px; height: 100%; }

.topo-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 18px; flex-wrap: wrap; gap: 10px;
}
.toolbar-title { display: flex; align-items: center; gap: 14px; }
.title-text { font-size: 17px; font-weight: 700; }
.ws-chip {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; padding: 3px 10px; border-radius: 999px;
  border: 1px solid var(--border-color); color: var(--text-secondary);
}
.ws-chip .dot { width: 7px; height: 7px; border-radius: 50%; background: #636366; }
.ws-chip.on { color: #6ee7a0; border-color: rgba(64, 220, 140, 0.35); }
.ws-chip.on .dot { background: #3ddc84; box-shadow: 0 0 8px #3ddc84; }
.ws-chip.off .dot { background: #ff6b6b; }

.toolbar-stats { display: flex; align-items: center; gap: 22px; }
.stat { display: flex; flex-direction: column; line-height: 1.3; }
.stat label { font-size: 11px; color: var(--text-secondary); }
.stat b { font-size: 16px; font-weight: 700; }
.mono { font-family: 'JetBrains Mono', Consolas, monospace; font-size: 12px; }

.topo-canvas {
  position: relative; flex: 1; min-height: 520px;
  overflow: hidden; border-radius: 20px;
  background:
    radial-gradient(900px 500px at 50% 50%, rgba(47, 111, 237, 0.08), transparent 70%),
    var(--card-bg);
}

/* SVG 链路层 */
.links { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
.link-base {
  stroke: rgba(120, 140, 180, 0.22); stroke-width: 1.4;
}
.link-base.offline { stroke: rgba(120, 120, 140, 0.14); stroke-dasharray: 3 5; }
.link-flow {
  stroke: url(#linkGlow); stroke-width: 1.8;
  stroke-dasharray: 7 9; filter: drop-shadow(0 0 3px rgba(88, 166, 255, 0.7));
  animation: dash-flow 1.1s linear infinite;
}
@keyframes dash-flow { to { stroke-dashoffset: -32; } }
.hub-halo { fill: rgba(47, 111, 237, 0.18); }

/* Hub 中心卡片 */
.hub-anchor {
  position: absolute; left: 50%; top: 50%;
  transform: translate(-50%, -50%); z-index: 5;
}
.hub-card {
  position: relative; width: 320px;
  padding: 18px 18px 12px;
  border-radius: 18px;
  background: linear-gradient(160deg, rgba(35, 55, 110, 0.92), rgba(20, 26, 50, 0.92));
  border: 1px solid rgba(96, 148, 255, 0.35);
  box-shadow: 0 0 42px rgba(47, 111, 237, 0.28), 0 12px 40px rgba(0, 0, 0, 0.45);
}
.corner-badge {
  position: absolute; top: -10px; left: 16px;
  font-size: 10.5px; letter-spacing: 0.5px;
  color: #9fc4ff; background: rgba(28, 44, 90, 0.95);
  border: 1px solid rgba(96, 148, 255, 0.4);
  padding: 2px 9px; border-radius: 999px;
}
.card-head { display: flex; align-items: center; gap: 10px; }
.hub-icon {
  width: 42px; height: 42px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  background: rgba(88, 166, 255, 0.14); color: #7dc4ff;
  border: 1px solid rgba(88, 166, 255, 0.25);
}
.card-title { font-size: 15px; font-weight: 700; line-height: 1.3; }
.card-sub { font-size: 11px; color: var(--text-secondary); }
.state-chip {
  margin-left: auto; display: inline-flex; align-items: center; gap: 5px;
  font-size: 11.5px; padding: 3px 9px; border-radius: 999px;
  border: 1px solid var(--border-color); color: var(--text-secondary); white-space: nowrap;
}
.state-chip .dot { width: 7px; height: 7px; border-radius: 50%; background: #636366; }
.state-chip.on { color: #6ee7a0; border-color: rgba(64, 220, 140, 0.35); }
.state-chip.on .dot { background: #3ddc84; box-shadow: 0 0 7px #3ddc84; }
.state-chip.off .dot { background: #ff6b6b; }
.state-chip.sm { font-size: 10.5px; padding: 2px 7px; }

.hub-meta {
  margin-top: 12px; display: grid; grid-template-columns: 1fr 1fr; gap: 7px 14px;
  font-size: 12px;
}
.hub-meta div { display: flex; justify-content: space-between; gap: 8px; }
.hub-meta label { color: var(--text-secondary); }
.hub-meta span { text-align: right; }

.skill-row { margin-top: 11px; }
.skill-row > label { font-size: 11px; color: var(--text-secondary); }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 5px; }
.skill-chip {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11px; padding: 2.5px 8px; border-radius: 7px;
  color: #a9d2ff; background: rgba(88, 166, 255, 0.1);
  border: 1px solid rgba(88, 166, 255, 0.22);
}
.card-foot {
  margin-top: 11px; padding-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.07);
  font-size: 11px; color: var(--text-secondary);
  display: flex; justify-content: space-between; align-items: center;
}
.card-foot.sm { margin-top: 6px; }

.hub-card.placeholder {
  width: 320px; text-align: center; color: var(--text-secondary);
  padding: 28px 20px; display: flex; flex-direction: column; align-items: center; gap: 8px;
}
.ph-title { font-size: 15px; font-weight: 700; color: var(--text-primary); }
.ph-text { font-size: 12px; line-height: 1.8; }
.ph-text code { font-size: 11px; color: #a9d2ff; }

/* Edge 辐射卡片 */
.edge-anchor {
  position: absolute; transform: translate(-50%, -50%); z-index: 4;
}
.edge-card {
  width: 236px; padding: 13px 14px 9px;
  border-radius: 15px; cursor: pointer;
  background: rgba(24, 28, 48, 0.92);
  border: 1px solid rgba(255, 255, 255, 0.09);
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.4);
  transition: transform 0.18s, border-color 0.18s, box-shadow 0.18s;
}
.edge-card:hover {
  transform: translateY(-2px);
  border-color: rgba(88, 166, 255, 0.5);
  box-shadow: 0 10px 32px rgba(47, 111, 237, 0.25);
}
.edge-card.off { opacity: 0.62; }
.edge-head { gap: 8px; }
.edge-icon {
  width: 30px; height: 30px; border-radius: 9px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  background: rgba(88, 166, 255, 0.12); color: #7dc4ff;
}
.edge-title-box { min-width: 0; }
.edge-title-box .card-title { font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.cap-row { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 9px; }
.cap-chip {
  display: inline-flex; align-items: center; gap: 3px;
  font-size: 10.5px; padding: 2px 7px; border-radius: 6px;
  color: #c9d6ea; background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
}
.edge-metrics {
  display: flex; gap: 8px; margin-top: 9px;
}
.metric { flex: 1; display: flex; align-items: baseline; gap: 3px; }
.metric label { font-size: 10px; color: var(--text-secondary); margin-right: auto; }
.metric b { font-size: 13.5px; font-weight: 700; }
.metric .unit { font-size: 9.5px; color: var(--text-tertiary); }
.go-detail { color: #7dc4ff; }

.empty-edge-hint {
  position: absolute; left: 50%; bottom: 26px; transform: translateX(-50%);
  font-size: 12px; color: var(--text-secondary);
  border: 1px dashed var(--border-color); border-radius: 10px;
  padding: 8px 18px;
}
</style>
