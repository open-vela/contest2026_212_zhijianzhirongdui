<template>
  <div class="node-page">
    <div class="page-head">
      <n-button quaternary size="small" @click="$router.push('/admin/topology')">
        <template #icon><n-icon :component="ArrowBackOutline" /></template>
        返回拓扑
      </n-button>
      <span class="head-title">节点详情</span>
    </div>

    <div v-if="!edge" class="not-found glass-card">
      <n-icon :component="HelpCircleOutline" :size="34" />
      <div class="nf-title">未找到节点 <span class="mono">{{ nodeId }}</span></div>
      <div class="nf-text">该边缘节点可能已注销，或尚未接入。</div>
      <n-button size="small" type="primary" ghost @click="store.loadTopology()">重新加载拓扑</n-button>
    </div>

    <template v-else>
      <!-- 节点信息卡 -->
      <div class="info-card glass-card">
        <div class="info-head">
          <div class="node-icon"><n-icon :component="PulseOutline" :size="24" /></div>
          <div>
            <div class="node-title">
              {{ edge.name }}
              <span class="state-chip" :class="edge.is_online ? 'on' : 'off'">
                <i class="dot"></i>{{ edge.is_online ? '在线' : '离线' }}
              </span>
            </div>
            <div class="node-sub mono">{{ edge.id }}</div>
          </div>
        </div>
        <div class="info-grid">
          <div><label>板型</label><span>{{ edge.board_model }}</span></div>
          <div><label>固件版本</label><span class="mono">{{ edge.firmware_ver || '—' }}</span></div>
          <div><label>所属中枢</label><span class="mono">{{ edge.hub_id || '—' }}</span></div>
          <div><label>注册时间</label><span>{{ fmtDate(edge.registered_at) }}</span></div>
          <div><label>最后心跳</label><span>{{ timeAgo(edge.last_heartbeat, nowTick) }}</span></div>
          <div>
            <label>能力</label>
            <span class="caps-inline">
              <span v-for="c in edge.capabilities" :key="c" class="cap-chip">
                <n-icon :component="capIcon(c)" :size="12" /> {{ capText(c) }}
              </span>
              <span v-if="edge.capabilities.length === 0">—</span>
            </span>
          </div>
        </div>
      </div>

      <!-- 遥测曲线 -->
      <div class="tel-card glass-card">
        <div class="card-title-bar">实时遥测（最近 {{ TELEMETRY_RING }} 条心跳）</div>
        <div class="spark-grid">
          <div class="spark-box">
            <div class="spark-head">
              <label>RSSI</label>
              <b>{{ latest.rssi ?? '—' }}<span class="unit" v-if="latest.rssi !== null"> dBm</span></b>
            </div>
            <Sparkline :values="series('rssi')" color="#58a6ff" :width="300" :height="56" :min="-100" :max="-30" />
          </div>
          <div class="spark-box">
            <div class="spark-head">
              <label>空闲堆内存</label>
              <b>{{ latest.heapKb }}<span class="unit" v-if="latest.heapKb !== null"> KB</span></b>
            </div>
            <Sparkline :values="series('heap')" color="#3ddc84" :width="300" :height="56" />
          </div>
          <div class="spark-box">
            <div class="spark-head">
              <label>帧率</label>
              <b>{{ latest.fps }}<span class="unit" v-if="latest.fps !== null"> fps</span></b>
            </div>
            <Sparkline :values="series('fps')" color="#d18cf5" :width="300" :height="56" :min="0" />
          </div>
        </div>
      </div>

      <!-- 指令下发面板 -->
      <div class="cmd-card glass-card">
        <div class="card-title-bar">指令下发<span class="title-note">经中枢 MQTT 主题 <code class="mono">hub/{{ edge.hub_id }}/cmd</code></span></div>
        <div class="cmd-grid">
          <div class="cmd-block">
            <div class="cmd-label">模态开关</div>
            <div class="switch-row">
              <span>在场/运动检测</span>
              <n-switch v-model:value="cfg.motionEnable" size="small" />
            </div>
            <div class="switch-row">
              <span>BLE 信标扫描</span>
              <n-switch v-model:value="cfg.bleEnable" size="small" />
            </div>
          </div>
          <div class="cmd-block">
            <div class="cmd-label">阈值</div>
            <div class="th-row">
              <span>BLE RSSI 门限</span>
              <n-input-number v-model:value="cfg.rssiThreshold" size="small" :min="-100" :max="-20" :step="2" />
              <span class="th-unit">dBm</span>
            </div>
            <div class="th-row">
              <span>运动置信门限</span>
              <n-input-number v-model:value="cfg.motionThreshold" size="small" :min="0.1" :max="1" :step="0.05" />
            </div>
          </div>
          <div class="cmd-block btns">
            <n-button type="primary" size="small" :loading="sending === 'cfg'" @click="sendConfig">
              下发配置
            </n-button>
            <n-button type="warning" ghost size="small" :loading="sending === 'reboot'" @click="sendReboot">
              <template #icon><n-icon :component="PowerOutline" /></template>
              重启边缘节点
            </n-button>
          </div>
        </div>
        <div v-if="lastResult" class="cmd-result" :class="lastResult.ok ? 'ok' : 'err'">
          {{ lastResult.text }}
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  NButton, NIcon, NSwitch, NInputNumber, useMessage,
} from 'naive-ui'
import {
  ArrowBackOutline, PulseOutline, HelpCircleOutline, PowerOutline,
  BluetoothOutline, VideocamOutline, WalkOutline, ScanOutline,
} from '@vicons/ionicons5'
import { useVelameshStore } from '@/stores/velamesh'
import { sendHubCommand } from '@/api/topology'
import { useNowTick, timeAgo } from '@/composables/useNowTick'
import Sparkline from '@/components/velamesh/Sparkline.vue'
import type { TelemetryPoint } from '@/types/topology'

const TELEMETRY_RING = 80

const route = useRoute()
const message = useMessage()
const store = useVelameshStore()
const nowTick = useNowTick()

const nodeId = computed(() => String(route.params.id))
const edge = computed(() => store.findEdge(nodeId.value))

const cfg = reactive({
  motionEnable: true,
  bleEnable: true,
  rssiThreshold: -70,
  motionThreshold: 0.6,
})

const sending = ref<null | 'cfg' | 'reboot'>(null)
const lastResult = ref<{ ok: boolean; text: string } | null>(null)

// ── 遥测历史 ────────────────────────────────────────────────────────
const history = computed<TelemetryPoint[]>(() => store.telemetryHistory[nodeId.value] || [])

function series(key: 'rssi' | 'heap' | 'fps'): number[] {
  return history.value
    .map((p) => p[key])
    .filter((v): v is number => typeof v === 'number')
    .map((v) => (key === 'heap' ? Math.round(v / 1024) : v))
}

const latest = computed(() => {
  const last = history.value[history.value.length - 1]
  return {
    rssi: typeof last?.rssi === 'number' ? last.rssi : null,
    heapKb: typeof last?.heap === 'number' ? Math.round(last.heap / 1024) : null,
    fps: typeof last?.fps === 'number' ? Number(last.fps.toFixed(1)) : null,
  }
})

// ── 指令下发 ────────────────────────────────────────────────────────
async function publishCmd(cmd: string, params: Record<string, unknown>, kind: 'cfg' | 'reboot') {
  const hubId = edge.value?.hub_id
  if (!hubId) {
    message.error('节点未绑定中枢，无法下发指令')
    return
  }
  sending.value = kind
  try {
    const res = await sendHubCommand(hubId, cmd, params)
    if (!res.success) {
      lastResult.value = { ok: false, text: `下发失败：${res.message}` }
      message.error(lastResult.value.text)
      return
    }
    lastResult.value = {
      ok: true,
      text: `指令已发布至 ${res.data.mqtt_topic}（cmd=${cmd}）`,
    }
    message.success('指令已下发')
  } finally {
    sending.value = null
  }
}

function sendConfig() {
  publishCmd('edge_config', {
    edge_id: nodeId.value,
    motion_enable: cfg.motionEnable,
    ble_enable: cfg.bleEnable,
    rssi_threshold: cfg.rssiThreshold,
    motion_threshold: cfg.motionThreshold,
  }, 'cfg')
}

function sendReboot() {
  publishCmd('edge_reboot', { edge_id: nodeId.value }, 'reboot')
}

// ── 展示工具 ────────────────────────────────────────────────────────
function capText(c: string): string {
  return ({ face: '人脸', gait: '步态', ble: 'BLE', camera: '摄像头' } as Record<string, string>)[c] || c
}

function capIcon(c: string) {
  return ({
    face: ScanOutline, gait: WalkOutline, ble: BluetoothOutline, camera: VideocamOutline,
  } as Record<string, unknown>)[c] as typeof BluetoothOutline || BluetoothOutline
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
</script>

<style scoped>
.node-page { display: flex; flex-direction: column; gap: 14px; }
.page-head { display: flex; align-items: center; gap: 12px; }
.head-title { font-size: 17px; font-weight: 700; }

.not-found {
  display: flex; flex-direction: column; align-items: center; gap: 10px;
  padding: 50px 20px; color: var(--text-secondary);
}
.nf-title { font-size: 15px; font-weight: 700; color: var(--text-primary); }
.nf-text { font-size: 12px; }

.info-card { padding: 16px 18px; }
.info-head { display: flex; gap: 12px; align-items: center; }
.node-icon {
  width: 44px; height: 44px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  background: rgba(88, 166, 255, 0.13); color: #7dc4ff;
  border: 1px solid rgba(88, 166, 255, 0.25);
}
.node-title { font-size: 16px; font-weight: 700; display: flex; align-items: center; gap: 10px; }
.node-sub { font-size: 11.5px; color: var(--text-secondary); margin-top: 2px; }

.state-chip {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 11px; padding: 2px 9px; border-radius: 999px;
  border: 1px solid var(--border-color); color: var(--text-secondary);
}
.state-chip .dot { width: 6px; height: 6px; border-radius: 50%; background: #636366; }
.state-chip.on { color: #6ee7a0; border-color: rgba(64, 220, 140, 0.35); }
.state-chip.on .dot { background: #3ddc84; box-shadow: 0 0 7px #3ddc84; }
.state-chip.off .dot { background: #ff6b6b; }

.info-grid {
  margin-top: 14px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px 20px;
}
.info-grid > div { display: flex; flex-direction: column; gap: 3px; font-size: 13px; }
.info-grid label { font-size: 11px; color: var(--text-secondary); }
.mono { font-family: 'JetBrains Mono', Consolas, monospace; font-size: 12px; }
.caps-inline { display: inline-flex; flex-wrap: wrap; gap: 5px; }
.cap-chip {
  display: inline-flex; align-items: center; gap: 3px;
  font-size: 10.5px; padding: 2px 7px; border-radius: 6px;
  color: #c9d6ea; background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.tel-card, .cmd-card { padding: 16px 18px; }
.card-title-bar { font-size: 14.5px; font-weight: 700; margin-bottom: 14px; }
.title-note { font-size: 11px; font-weight: 400; color: var(--text-secondary); margin-left: 10px; }
.title-note code { color: #a9d2ff; }

.spark-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.spark-box {
  border: 1px solid var(--border-color); border-radius: 12px; padding: 11px 13px;
  background: rgba(255, 255, 255, 0.02);
}
.spark-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 7px; }
.spark-head label { font-size: 11.5px; color: var(--text-secondary); }
.spark-head b { font-size: 17px; font-weight: 800; }
.spark-head .unit { font-size: 10.5px; color: var(--text-tertiary); font-weight: 400; }

.cmd-grid { display: grid; grid-template-columns: 1fr 1fr auto; gap: 22px; align-items: start; }
.cmd-label { font-size: 11.5px; color: var(--text-secondary); margin-bottom: 9px; }
.switch-row, .th-row {
  display: flex; align-items: center; gap: 9px;
  font-size: 12.5px; margin-bottom: 9px;
}
.th-unit { font-size: 10.5px; color: var(--text-tertiary); }
.cmd-block.btns { display: flex; flex-direction: column; gap: 10px; padding-top: 22px; }

.cmd-result { margin-top: 12px; font-size: 12px; border-radius: 8px; padding: 7px 11px; }
.cmd-result.ok { color: #6ee7a0; background: rgba(61, 220, 132, 0.08); border: 1px solid rgba(61, 220, 132, 0.25); }
.cmd-result.err { color: #ff7b7b; background: rgba(255, 107, 107, 0.08); border: 1px solid rgba(255, 107, 107, 0.25); }
</style>
