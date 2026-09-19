<template>
  <main class="demo-page" aria-labelledby="demo-title">
    <header class="demo-header">
      <div>
        <p class="eyebrow">OPE-86 · 小米 + Seeed 统一演示</p>
        <h1 id="demo-title">竞赛演示控制台</h1>
        <p class="subtitle">一条链路展示发现连接、协同感知、身份融合、小型化与云接口；每项证据均标注来源。</p>
      </div>
      <div class="demo-controls">
        <n-select
          v-model:value="mode"
          aria-label="选择演示数据源"
          :options="modeOptions"
          class="mode-select"
          @update:value="changeMode"
        />
        <n-button :loading="loading" type="primary" @click="loadAll(true)">刷新证据</n-button>
      </div>
    </header>

    <n-alert v-if="mode === 'mock'" type="info" :bordered="false" class="notice">
      当前为离线演练模式。所有样例均带「演练 Mock」标签，不参与达标判断；现场请切换到「现场真实链路」。
    </n-alert>
    <n-alert
      v-else-if="mode === 'cloud_api'"
      type="info"
      :bordered="false"
      class="notice"
    >
      当前聚焦云 API/outbox 链路；节点与指标仍来自后端的持久化证据，不会用 Mock 补齐缺失实测值。
    </n-alert>
    <n-alert v-else-if="mode === 'mixed'" type="info" :bordered="false" class="notice">
      当前为混合展示：本地 MQTT 感知链路与可配置云 transport 同时展示，每条记录仍保留独立来源标识。
    </n-alert>
    <n-alert
      v-if="mode !== 'mock' && mode !== 'cloud_api' && overview && overview.services.mqtt?.status !== 'connected'"
      type="warning"
      :bordered="false"
      class="notice"
    >
      FastAPI 与 SQLite 可用，但服务器尚未连上 MQTT broker。页面会保持“待实机”，请检查 broker 地址、账号和现场局域网。
    </n-alert>
    <n-alert v-if="errorMessage" type="error" closable class="notice" @close="errorMessage = ''">
      {{ errorMessage }}
    </n-alert>

    <div class="status-strip" aria-live="polite">
      <span>页面更新：{{ formatTime(overview?.updated_at) }}</span>
      <span>实时通道：{{ streamStateLabel }}</span>
      <EvidenceBadge :provenance="overview?.provenance || 'pending_real'" size="tiny" />
    </div>

    <section class="judge-grid" aria-label="评委首屏核心状态">
      <article>
        <span>节点</span><strong>{{ overview?.online_node_count ?? 0 }} / {{ overview?.node_count ?? 0 }}</strong>
        <small>实时在线 / 已发现</small>
        <EvidenceBadge :provenance="overview?.provenance || 'pending_real'" size="tiny" />
      </article>
      <article>
        <span>本地链路</span><strong>{{ connectivity?.mqtt.server_connected ? 'MQTT 已连' : 'MQTT 待连' }}</strong>
        <small>{{ connectivity?.wifi.ip || '等待 WiFi / DHCP' }}</small>
        <EvidenceBadge :provenance="connectivity?.provenance || 'pending_real'" size="tiny" />
      </article>
      <article>
        <span>剪影</span><strong>Frame {{ display(silhouette?.frame_seq) }}</strong>
        <small>{{ display(silhouette?.foreground_pixels) }} foreground pixels</small>
        <EvidenceBadge :provenance="silhouette?.provenance || 'pending_real'" size="tiny" />
      </article>
      <article>
        <span>BLE</span><strong>{{ connectivity?.ble_devices.length ?? 0 }} devices</strong>
        <small>{{ connectivity?.ble_devices[0]?.device_id || '等待扫描上报' }}</small>
        <EvidenceBadge :provenance="connectivity?.ble_devices[0]?.provenance || 'pending_real'" size="tiny" />
      </article>
    </section>

    <n-spin :show="loading && !overview">
      <section aria-labelledby="overview-heading" class="demo-section">
        <div class="section-heading">
          <div><span class="step">01</span><h2 id="overview-heading">Demo Overview</h2></div>
          <p>双赛道共享入口 · 服务健康 · 节点在线证据</p>
        </div>

        <n-grid cols="1 s:2 m:4" responsive="screen" :x-gap="14" :y-gap="14">
          <n-grid-item><n-card class="glass-card stat-card" :bordered="false"><n-statistic label="节点数" :value="overview?.node_count ?? 0" /></n-card></n-grid-item>
          <n-grid-item><n-card class="glass-card stat-card" :bordered="false"><n-statistic label="实时在线" :value="overview?.online_node_count ?? 0" /></n-card></n-grid-item>
          <n-grid-item><n-card class="glass-card stat-card" :bordered="false"><n-statistic label="SQLite 证据" :value="overview?.telemetry_count ?? 0" /></n-card></n-grid-item>
          <n-grid-item><n-card class="glass-card stat-card" :bordered="false"><n-statistic label="云发送队列" :value="cloud?.queue_depth ?? 0" /></n-card></n-grid-item>
        </n-grid>

        <div class="two-column top-gap">
          <n-card title="软件服务" class="glass-card" :bordered="false">
            <ul class="evidence-list" aria-label="软件服务状态">
              <li v-for="item in serviceEntries" :key="item.key">
                <div>
                  <strong>{{ serviceLabel(item.key) }}</strong>
                  <small>{{ item.value.broker || item.value.engine || '' }}</small>
                </div>
                <div class="row-end">
                  <n-tag :type="serviceTagType(item.value.status)" size="small" :bordered="false">{{ item.value.status }}</n-tag>
                  <EvidenceBadge :provenance="item.value.provenance" size="tiny" />
                </div>
              </li>
            </ul>
          </n-card>

          <n-card title="赛题覆盖" class="glass-card" :bordered="false">
            <ul class="evidence-list" aria-label="赛题覆盖状态">
              <li v-for="(provenance, key) in overview?.coverage || {}" :key="key">
                <strong>{{ coverageLabel(String(key)) }}</strong>
                <EvidenceBadge :provenance="provenance" size="tiny" />
              </li>
            </ul>
          </n-card>
        </div>

        <n-card title="现场节点" class="glass-card top-gap" :bordered="false">
          <div class="table-scroll">
            <table class="evidence-table">
              <thead><tr><th>节点</th><th>角色</th><th>能力</th><th>IP / Broker</th><th>心跳</th><th>证据</th></tr></thead>
              <tbody>
                <tr v-for="node in nodes" :key="node.node_id">
                  <td><strong>{{ node.name }}</strong><small>{{ node.node_id }}</small></td>
                  <td>{{ node.role }}</td>
                  <td><span class="chip-list"><span v-for="capability in node.capabilities" :key="capability">{{ capability }}</span></span></td>
                  <td>{{ node.ip || '待 DHCP' }}<small>{{ node.broker }}</small></td>
                  <td><n-tag :type="node.online ? 'success' : 'warning'" size="small" :bordered="false">{{ node.online ? '在线' : '待心跳' }}</n-tag><small>{{ formatAge(node.age_seconds) }}</small></td>
                  <td><EvidenceBadge :provenance="node.provenance" size="tiny" /></td>
                </tr>
                <tr v-if="!nodes.length"><td colspan="6"><n-empty description="等待节点注册或 MQTT 心跳" size="small" /></td></tr>
              </tbody>
            </table>
          </div>
        </n-card>
      </section>

      <section aria-labelledby="silhouette-heading" class="demo-section">
        <div class="section-heading">
          <div><span class="step">02</span><h2 id="silhouette-heading">OPE-73 剪影 / 步态</h2></div>
          <p>小米协同感知 · Seeed 端侧 AI</p>
        </div>
        <n-card class="glass-card" :bordered="false">
          <template #header-extra><EvidenceBadge :provenance="silhouette?.provenance || 'pending_real'" /></template>
          <n-grid cols="2 s:3 m:6" responsive="screen" :x-gap="12" :y-gap="16">
            <n-grid-item><n-statistic label="节点" :value="silhouette?.node_id || '待上报'" /></n-grid-item>
            <n-grid-item><n-statistic label="帧序号" :value="display(silhouette?.frame_seq)" /></n-grid-item>
            <n-grid-item><n-statistic label="前景像素" :value="display(silhouette?.foreground_pixels)" /></n-grid-item>
            <n-grid-item><n-statistic label="已上传" :value="display(silhouette?.upload_stats.uploaded)" /></n-grid-item>
            <n-grid-item><n-statistic label="空帧跳过" :value="display(silhouette?.upload_stats.skipped_empty)" /></n-grid-item>
            <n-grid-item><n-statistic label="窗口范围" :value="windowLabel" /></n-grid-item>
          </n-grid>
          <n-divider />
          <dl class="evidence-details">
            <div><dt>服务器收包 topic</dt><dd><code>{{ silhouette?.server_receive.last_topic || 'vela/node/&lt;node_id&gt;/silhouette' }}</code><EvidenceBadge :provenance="silhouette?.server_receive.provenance || 'pending_real'" size="tiny" /></dd></div>
            <div><dt>最后收包</dt><dd>{{ formatTime(silhouette?.server_receive.received_at) }}</dd></div>
            <div><dt>设备日志留证</dt><dd>{{ silhouette?.device_log_evidence.note || '等待实机' }} <EvidenceBadge :provenance="silhouette?.device_log_evidence.provenance || 'pending_real'" size="tiny" /></dd></div>
          </dl>
        </n-card>

        <n-card class="glass-card top-gap" :bordered="false">
          <template #header>
            <span>步态识别结果（gait/result）</span>
          </template>
          <template #header-extra><EvidenceBadge :provenance="gait?.provenance || 'pending_real'" /></template>
          <n-grid cols="2 s:3 m:6" responsive="screen" :x-gap="12" :y-gap="16">
            <n-grid-item><n-statistic label="识别身份" :value="gait?.identity || '待上报'" /></n-grid-item>
            <n-grid-item><n-statistic label="置信度" :value="gaitScoreLabel" /></n-grid-item>
            <n-grid-item><n-statistic label="方向" :value="gait?.direction || '待上报'" /></n-grid-item>
            <n-grid-item><n-statistic label="推理耗时" :value="display(gait?.latency, ' ms')" /></n-grid-item>
            <n-grid-item><n-statistic label="margin" :value="display(gait?.margin)" /></n-grid-item>
            <n-grid-item><n-statistic label="session" :value="gait?.session_id ? gait.session_id.slice(0, 8) : '待上报'" /></n-grid-item>
          </n-grid>
          <n-divider />
          <div v-if="gait?.top3.length" class="top3-list" aria-label="步态 top3 候选">
            <span class="top3-title">Top-3 候选</span>
            <ol>
              <li v-for="(item, index) in gait.top3" :key="`${item.identity}-${index}`">
                <strong>{{ item.identity }}</strong>
                <span>{{ item.score == null ? '待实机' : Number(item.score).toFixed(4) }}</span>
                <n-tag v-if="index === 0" size="tiny" type="success" :bordered="false">最佳匹配</n-tag>
              </li>
            </ol>
          </div>
          <dl class="evidence-details top-gap">
            <div><dt>服务器收包 topic</dt><dd><code>{{ gait?.server_receive.last_topic || 'dominiscius/&lt;node_id&gt;/gait/result' }}</code><EvidenceBadge :provenance="gait?.server_receive.provenance || 'pending_real'" size="tiny" /></dd></div>
            <div><dt>最后收包</dt><dd>{{ formatTime(gait?.server_receive.received_at) }}</dd></div>
            <div><dt>来源协议</dt><dd>{{ gait?.source || 'gait' }} · ESP32 → MQTT → Backend → WebSocket</dd></div>
          </dl>
        </n-card>
      </section>

      <section aria-labelledby="connectivity-heading" class="demo-section">
        <div class="section-heading">
          <div><span class="step">03</span><h2 id="connectivity-heading">OPE-75 WiFi / MQTT / BLE</h2></div>
          <p>发现连接 · 多协议互联 · 断线重连证据</p>
        </div>
        <div class="two-column">
          <n-card title="连接链路" class="glass-card" :bordered="false">
            <template #header-extra><EvidenceBadge :provenance="connectivity?.provenance || 'pending_real'" /></template>
            <ul class="evidence-list">
              <li><strong>WiFi / DHCP</strong><span>{{ connectionState(connectivity?.wifi.connected) }} · {{ connectivity?.wifi.ip || '待分配' }} · {{ display(connectivity?.wifi.rssi, ' dBm') }}</span><EvidenceBadge :provenance="connectivity?.wifi.provenance || 'pending_real'" size="tiny" /></li>
              <li><strong>MQTT 服务端</strong><span>{{ connectivity?.mqtt.server_connected ? '已连接' : '未连接' }} · {{ connectivity?.mqtt.broker || '待配置' }}</span><EvidenceBadge :provenance="connectivity?.mqtt.provenance || 'pending_real'" size="tiny" /></li>
              <li><strong>节点 MQTT</strong><span>{{ connectionState(connectivity?.mqtt.node_connected) }}</span><EvidenceBadge :provenance="connectivity?.mqtt.node_connected == null ? 'pending_real' : connectivity.mqtt.provenance" size="tiny" /></li>
              <li><strong>重连</strong><span>{{ display(connectivity?.reconnect_evidence.count, ' 次') }} · {{ display(connectivity?.reconnect_evidence.last_reconnect_ms, ' ms') }}</span><EvidenceBadge :provenance="connectivity?.reconnect_evidence.provenance || 'pending_real'" size="tiny" /></li>
            </ul>
          </n-card>

          <n-card title="BLE 扫描证据" class="glass-card" :bordered="false">
            <ul v-if="connectivity?.ble_devices.length" class="evidence-list">
              <li v-for="device in connectivity.ble_devices" :key="`${device.device_id}-${device.scan_seq}`">
                <div><strong>{{ device.device_id }}</strong><small>scan #{{ display(device.scan_seq) }} · {{ device.publish_status }}</small></div>
                <div class="row-end"><span>{{ display(device.rssi, ' dBm') }}</span><EvidenceBadge :provenance="device.provenance" size="tiny" /></div>
              </li>
            </ul>
            <n-empty v-else description="等待 BLE 扫描上报" size="small" />
          </n-card>
        </div>
        <n-card title="统一 MQTT Topic" class="glass-card top-gap" :bordered="false">
          <div class="topic-grid">
            <code v-for="(topic, key) in connectivity?.topics || {}" :key="key"><b>{{ key }}</b>{{ topic }}</code>
          </div>
        </n-card>
      </section>

      <section aria-labelledby="xiaomi-heading" class="demo-section">
        <div class="section-heading">
          <div><span class="step">04</span><h2 id="xiaomi-heading">小米赛道评分证据</h2></div>
          <p>只有 provenance=real 的实测值才判定达标</p>
        </div>
        <n-card class="glass-card" :bordered="false">
          <div class="table-scroll">
            <table class="evidence-table score-table">
              <thead><tr><th>评分点</th><th>实测值</th><th>目标</th><th>判定</th><th>证据来源</th></tr></thead>
              <tbody>
                <tr v-for="metric in metrics" :key="metric.key">
                  <td><strong>{{ metric.name }}</strong></td>
                  <td>{{ metricValue(metric) }}</td>
                  <td>{{ metric.target_note }}</td>
                  <td><n-tag :type="metricState(metric).type" size="small" :bordered="false">{{ metricState(metric).label }}</n-tag></td>
                  <td><EvidenceBadge :provenance="metric.provenance" size="tiny" /><small>{{ metric.source_node || '等待节点' }} · {{ metric.source_topic || '等待 metrics topic' }}</small><small>{{ formatTime(metric.updated_at) }}</small></td>
                </tr>
              </tbody>
            </table>
          </div>
        </n-card>
      </section>

      <section aria-labelledby="seeed-heading" class="demo-section">
        <div class="section-heading">
          <div><span class="step">05</span><h2 id="seeed-heading">Seeed 小型化展示</h2></div>
          <p>复用同一套感知链路，单独突出体积、功耗、端侧 AI 与复现性</p>
        </div>
        <n-card class="glass-card" :bordered="false">
          <template #header-extra><EvidenceBadge :provenance="seeed?.provenance || 'pending_real'" /></template>
          <n-grid cols="2 s:4" responsive="screen" :x-gap="12" :y-gap="16">
            <n-grid-item><n-statistic label="申报尺寸" :value="seeed?.claimed_dimensions_mm?.join(' × ') || '待录入'"><template #suffix>mm</template></n-statistic></n-grid-item>
            <n-grid-item><n-statistic label="申报体积" :value="seeed?.claimed_volume_cm3 ?? 0"><template #suffix>cm³</template></n-statistic></n-grid-item>
            <n-grid-item><n-statistic label="申报重量" :value="seeed?.claimed_weight_g ?? 0"><template #suffix>g</template></n-statistic></n-grid-item>
            <n-grid-item><n-statistic label="功耗比" :value="seeed?.power_ratio ?? 0"><template #suffix>: 1</template></n-statistic></n-grid-item>
          </n-grid>
          <n-alert type="warning" :bordered="false" class="measurement-note">{{ seeed?.physical_verification || '等待现场实物测量' }}</n-alert>
          <div class="evidence-cards">
            <article v-for="item in seeed?.evidence || []" :key="item.name">
              <div><strong>{{ item.name }}</strong><EvidenceBadge :provenance="item.provenance" size="tiny" /></div>
              <span>{{ item.status }}</span><p>{{ item.note }}</p>
            </article>
          </div>
        </n-card>
      </section>

      <section aria-labelledby="cloud-heading" class="demo-section">
        <div class="section-heading">
          <div><span class="step">06</span><h2 id="cloud-heading">云端收发接口</h2></div>
          <p>SQLite outbox · 自动 worker · 幂等、超时、退避与重启恢复</p>
        </div>
        <div class="two-column">
          <n-card title="上传状态" class="glass-card" :bordered="false">
            <template #header-extra><EvidenceBadge :provenance="cloud?.provenance || 'reserved'" /></template>
            <ul class="evidence-list">
              <li><strong>传输模式</strong><span>{{ cloud?.mode || 'disabled' }} · {{ cloud?.provider || 'disabled' }}</span></li>
              <li><strong>云 ingest</strong><span>{{ cloud?.ingest || 'disabled' }}</span></li>
              <li><strong>Worker</strong><span>{{ cloud?.delivery_worker || 'disabled' }}</span></li>
              <li><strong>端点配置</strong><span>{{ cloud?.endpoint_configured ? 'HTTP endpoint 已配置' : cloud?.mode === 'mock' ? '本地 Mock（非公网）' : '未配置' }}</span></li>
              <li><strong>本地队列</strong><span>{{ cloud?.queue_depth ?? 0 }} 条</span></li>
              <li><strong>重试次数</strong><span>{{ cloud?.retry_count ?? 0 }}</span></li>
              <li><strong>最近上传</strong><span>{{ formatTime(cloud?.last_upload_at) }} · {{ cloud?.last_upload_status || '无' }}</span></li>
              <li><strong>最近接收</strong><span>{{ formatTime(cloud?.last_receive_at) }}</span></li>
            </ul>
            <n-alert v-if="cloud?.error_code" type="warning" :bordered="false" class="cloud-error">
              {{ cloud.error_code }}：{{ cloud.error_message || '等待下次自动重试' }}
            </n-alert>
            <n-space vertical class="top-gap">
              <n-button type="primary" :loading="uploading" @click="uploadSnapshot">写入一条 Demo 快照</n-button>
              <small aria-live="polite">{{ uploadMessage }}</small>
            </n-space>
          </n-card>
          <n-card title="最近云发送队列" class="glass-card" :bordered="false">
            <ul v-if="cloudEvents.length" class="evidence-list compact-events">
              <li v-for="event in cloudEvents" :key="event.request_id">
                <div><strong>{{ event.direction === 'receive' ? '接收' : '上传' }} · {{ event.event_type }}</strong><small>{{ event.request_id.slice(0, 12) }} · {{ formatTime(event.updated_at) }}</small><small v-if="event.error_code">{{ event.error_code }} · {{ event.error_message }}</small></div>
                <div class="row-end"><n-tag size="small" :type="cloudEventTagType(event.status)" :bordered="false">{{ event.status }}<template v-if="event.retry_count"> · retry {{ event.retry_count }}/{{ event.max_retries }}</template></n-tag><EvidenceBadge :provenance="event.provenance" size="tiny" /></div>
              </li>
            </ul>
            <n-empty v-else description="尚无队列记录" size="small" />
          </n-card>
        </div>
      </section>
    </n-spin>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  NAlert, NButton, NCard, NDivider, NEmpty, NGrid, NGridItem, NSelect,
  NSpace, NSpin, NStatistic, NTag,
} from 'naive-ui'
import EvidenceBadge from '@/components/common/EvidenceBadge.vue'
import { connectDemoEvents, demoApi, getDemoMode, setDemoMode } from '@/api/demo'
import type {
  CloudEvent, CloudStatus, ConnectivityEvidence, DemoMode, DemoNode, DemoOverview,
  GaitEvidence, ScoringMetric, SeeedMiniaturization, ServiceEvidence, SilhouetteEvidence,
} from '@/types/demo'

const mode = ref<DemoMode>(getDemoMode())
const overview = ref<DemoOverview | null>(null)
const nodes = ref<DemoNode[]>([])
const silhouette = ref<SilhouetteEvidence | null>(null)
const gait = ref<GaitEvidence | null>(null)
const connectivity = ref<ConnectivityEvidence | null>(null)
const metrics = ref<ScoringMetric[]>([])
const seeed = ref<SeeedMiniaturization | null>(null)
const cloud = ref<CloudStatus | null>(null)
const cloudEvents = ref<CloudEvent[]>([])
const loading = ref(false)
const uploading = ref(false)
const errorMessage = ref('')
const uploadMessage = ref('')
const streamState = ref('connecting')

const modeOptions = [
  { label: '现场真实链路', value: 'local_mqtt' },
  { label: '云 API / Outbox', value: 'cloud_api' },
  { label: '本地 + 云混合', value: 'mixed' },
  { label: '离线演练（Mock）', value: 'mock' },
]

const serviceLabels: Record<string, string> = {
  api: 'FastAPI', database: 'SQLite 数据库', mqtt: '本地 MQTT', cloud: '云端接口',
}
const coverageLabels: Record<string, string> = {
  ope73_silhouette: 'OPE-73 剪影 / 步态',
  ope75_connectivity: 'OPE-75 WiFi / MQTT / BLE',
  xiaomi_metrics: '小米赛道实测指标',
  seeed_evidence: 'Seeed 小型化证据',
  cloud_roundtrip: '云端收发闭环',
}

const serviceEntries = computed(() => Object.entries(overview.value?.services || {}).map(([key, value]) => ({ key, value })))
const windowLabel = computed(() => {
  const start = silhouette.value?.window.seq_start
  const end = silhouette.value?.window.seq_end
  return start == null || end == null ? '待上报' : `${start}–${end}`
})
const gaitScoreLabel = computed(() => {
  const score = gait.value?.score
  return score == null ? '待实机' : Number(score).toFixed(4)
})
const streamStateLabel = computed(() => ({
  connected: 'WebSocket 已连接', connecting: '连接中', disconnected: '已断开（轮询保底）',
  reconnecting: '退避重连中（轮询保底）', error: '异常（轮询保底）',
  mock: 'Mock 定时演练', unauthorized: '登录失效',
}[streamState.value] || streamState.value))

let pollTimer: number | undefined
let streamRefreshTimer: number | undefined
let disconnectStream: (() => void) | undefined
let disposed = false
let loadInFlight: Promise<void> | undefined

function loadAll(showSpinner = false): Promise<void> {
  if (loadInFlight) return loadInFlight
  if (showSpinner) loading.value = true
  loadInFlight = (async () => {
    const labels = ['总览', '节点', '剪影', '步态', '连接', '指标', 'Seeed', '云状态', '云事件']
    const results = await Promise.allSettled([
      demoApi.overview(), demoApi.nodes(), demoApi.silhouette(), demoApi.gait(),
      demoApi.connectivity(), demoApi.metrics(), demoApi.seeed(), demoApi.cloudStatus(), demoApi.cloudEvents(),
    ])
    if (disposed) return
    const setters: Array<(value: unknown) => void> = [
      value => {
        const next = value as DemoOverview
        overview.value = { ...next, updated_at: next.updated_at || new Date().toISOString() }
      },
      value => { nodes.value = value as DemoNode[] },
      value => { silhouette.value = value as SilhouetteEvidence },
      value => { gait.value = value as GaitEvidence },
      value => { connectivity.value = value as ConnectivityEvidence },
      value => { metrics.value = value as ScoringMetric[] },
      value => { seeed.value = value as SeeedMiniaturization },
      value => { cloud.value = value as CloudStatus },
      value => { cloudEvents.value = value as CloudEvent[] },
    ]
    const failures: string[] = []
    results.forEach((result, index) => {
      if (result.status === 'fulfilled') setters[index](result.value)
      else failures.push(`${labels[index]}：${result.reason instanceof Error ? result.reason.message : String(result.reason)}`)
    })
    errorMessage.value = failures.length ? `部分数据加载失败（已保留上次成功结果）：${failures.join('；')}` : ''
  })().catch((error) => {
    if (!disposed) errorMessage.value = `Demo 数据加载失败：${error instanceof Error ? error.message : String(error)}`
  }).finally(() => {
    if (!disposed) loading.value = false
    loadInFlight = undefined
  })
  return loadInFlight
}

function scheduleStreamRefresh() {
  if (streamRefreshTimer) return
  streamRefreshTimer = window.setTimeout(() => {
    streamRefreshTimer = undefined
    void loadAll(false)
  }, 500)
}

function openStream() {
  disconnectStream?.()
  streamState.value = 'connecting'
  disconnectStream = connectDemoEvents(scheduleStreamRefresh, (state) => { streamState.value = state })
}

function changeMode(nextMode: DemoMode) {
  mode.value = nextMode
  setDemoMode(nextMode)
  uploadMessage.value = ''
  openStream()
  void loadAll(true)
}

async function uploadSnapshot() {
  uploading.value = true
  try {
    const result = await demoApi.uploadCloud({
      captured_at: new Date().toISOString(),
      node_count: overview.value?.node_count || 0,
      online_node_count: overview.value?.online_node_count || 0,
      telemetry_count: overview.value?.telemetry_count || 0,
    })
    uploadMessage.value = result.provenance === 'mock' && mode.value === 'mock'
      ? `Mock 请求 ${result.request_id}：未写数据库、未发送云端。`
      : `请求 ${result.request_id.slice(0, 12)} ${result.duplicate ? '已存在' : '已写入 SQLite'}；状态 ${result.status}，transport=${result.provenance}。`
    const [nextCloud, nextEvents] = await Promise.all([demoApi.cloudStatus(), demoApi.cloudEvents()])
    if (!disposed) {
      cloud.value = nextCloud
      cloudEvents.value = nextEvents
    }
  } catch (error) {
    uploadMessage.value = `写入失败：${error instanceof Error ? error.message : String(error)}`
  } finally {
    uploading.value = false
  }
}

function display(value: unknown, suffix = ''): string {
  return value === null || value === undefined || value === '' ? '待实机' : `${value}${suffix}`
}

function formatTime(value: string | null | undefined): string {
  if (!value) return '等待数据'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { hour12: false })
}

function formatAge(value: number | null): string {
  return value == null ? '无真实心跳' : `${value.toFixed(1)} 秒前`
}

function serviceLabel(key: string): string { return serviceLabels[key] || key }
function coverageLabel(key: string): string { return coverageLabels[key] || key }
function serviceTagType(value: string): 'success' | 'warning' | 'error' | 'info' | 'default' {
  if (value.includes('disconnected') || value.includes('未')) return 'error'
  if (value.includes('connected') || value.includes('在线')) return 'success'
  return 'warning'
}
function connectionState(value: boolean | string | null | undefined): string {
  if (value === true || value === 'connected') return '已连接'
  if (value === false || value === 'disconnected') return '未连接'
  return '待节点上报'
}
function metricValue(metric: ScoringMetric): string {
  if (metric.value == null) return '待实机验证'
  if (typeof metric.value === 'boolean') return metric.value ? '支持' : '不支持'
  return metric.unit ? `${metric.value} ${metric.unit}` : String(metric.value)
}
function metricState(metric: ScoringMetric): { label: string; type: 'success' | 'warning' | 'error' | 'info' } {
  if (metric.value == null) return { label: '待实机验证', type: 'warning' }
  if (metric.provenance !== 'real') return { label: '演练样例（不计分）', type: 'info' }
  if (metric.passed == null) return { label: '已采集', type: 'success' }
  return metric.passed
    ? { label: '实测达标', type: 'success' }
    : { label: '实测未达标', type: 'error' }
}

function cloudEventTagType(status: string): 'success' | 'warning' | 'error' | 'info' | 'default' {
  if (status === 'delivered') return 'success'
  if (status === 'failed') return 'error'
  if (status === 'sending') return 'info'
  return 'warning'
}

onMounted(() => {
  disposed = false
  void loadAll(true)
  openStream()
  pollTimer = window.setInterval(() => { void loadAll(false) }, 5000)
})

onUnmounted(() => {
  disposed = true
  disconnectStream?.()
  if (pollTimer) window.clearInterval(pollTimer)
  if (streamRefreshTimer) window.clearTimeout(streamRefreshTimer)
})
</script>

<style scoped>
.demo-page { max-width: 1480px; margin: 0 auto; padding-bottom: 48px; }
.demo-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; margin-bottom: 18px; }
.eyebrow { margin: 0 0 5px; color: var(--accent-color); font-size: 12px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
h1 { margin: 0; font-size: clamp(26px, 4vw, 42px); letter-spacing: -.04em; }
.subtitle { max-width: 780px; margin: 8px 0 0; color: var(--text-secondary); line-height: 1.65; }
.demo-controls { display: flex; gap: 10px; align-items: center; flex-shrink: 0; }
.mode-select { width: 190px; }
.notice { margin-bottom: 14px; }
.status-strip { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-bottom: 18px; color: var(--text-secondary); font-size: 12px; }
.judge-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 20px; }
.judge-grid article { position: relative; min-height: 118px; padding: 15px; border: 1px solid var(--border-color); border-radius: 16px; background: var(--card-bg, rgba(255,255,255,.65)); }
.judge-grid article > span, .judge-grid article > small { display: block; color: var(--text-secondary); font-size: 11px; }
.judge-grid article > strong { display: block; margin: 9px 0 4px; overflow: hidden; font-size: 18px; text-overflow: ellipsis; white-space: nowrap; }
.judge-grid article :deep(.n-tag) { margin-top: 9px; }
.demo-section { margin-top: 26px; scroll-margin-top: 16px; }
.section-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; margin-bottom: 12px; }
.section-heading > div { display: flex; align-items: center; gap: 10px; }
.section-heading h2 { margin: 0; font-size: 21px; }
.section-heading p { margin: 0; color: var(--text-secondary); text-align: right; }
.step { display: inline-flex; width: 32px; height: 32px; align-items: center; justify-content: center; border-radius: 10px; background: color-mix(in srgb, var(--accent-color) 15%, transparent); color: var(--accent-color); font-weight: 800; }
.stat-card { min-height: 104px; }
.two-column { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.top-gap { margin-top: 14px; }
.evidence-list { display: flex; flex-direction: column; gap: 0; margin: 0; padding: 0; list-style: none; }
.evidence-list li { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 50px; padding: 9px 0; border-bottom: 1px solid var(--border-color); }
.evidence-list li:last-child { border-bottom: 0; }
.evidence-list strong, .evidence-list small { display: block; }
.evidence-list small, td small { margin-top: 4px; color: var(--text-secondary); font-size: 11px; }
.row-end { display: flex; align-items: center; justify-content: flex-end; gap: 8px; text-align: right; }
.table-scroll { width: 100%; overflow-x: auto; }
.evidence-table { width: 100%; min-width: 760px; border-collapse: collapse; font-size: 13px; }
.evidence-table th { color: var(--text-secondary); font-size: 12px; font-weight: 600; text-align: left; }
.evidence-table th, .evidence-table td { padding: 12px 10px; border-bottom: 1px solid var(--border-color); vertical-align: middle; }
.evidence-table tbody tr:last-child td { border-bottom: 0; }
.chip-list { display: flex; flex-wrap: wrap; gap: 5px; }
.chip-list span { padding: 3px 7px; border-radius: 999px; background: color-mix(in srgb, var(--accent-color) 10%, transparent); font-size: 11px; }
.evidence-details { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; margin: 0; }
.evidence-details dt { margin-bottom: 6px; color: var(--text-secondary); font-size: 12px; }
.evidence-details dd { margin: 0; word-break: break-word; }
code { padding: 3px 6px; border-radius: 6px; background: color-mix(in srgb, var(--text-secondary) 10%, transparent); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; }
.topic-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(270px, 1fr)); gap: 9px; }
.topic-grid code { display: flex; gap: 8px; padding: 10px; }
.topic-grid b { min-width: 72px; color: var(--accent-color); }
.score-table td:last-child small { display: block; max-width: 260px; word-break: break-all; }
.measurement-note { margin-top: 18px; }
.evidence-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; margin-top: 14px; }
.evidence-cards article { min-height: 116px; padding: 14px; border: 1px solid var(--border-color); border-radius: 14px; }
.evidence-cards article > div { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.evidence-cards article > span { display: block; margin-top: 12px; font-weight: 600; }
.evidence-cards article p { margin: 5px 0 0; color: var(--text-secondary); font-size: 12px; line-height: 1.55; }
.compact-events li { min-height: 58px; }
.cloud-error { margin-top: 12px; overflow-wrap: anywhere; }
.top3-list { display: flex; flex-direction: column; gap: 6px; }
.top3-title { color: var(--text-secondary); font-size: 12px; }
.top3-list ol { margin: 4px 0 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 6px; }
.top3-list li { display: flex; align-items: center; gap: 10px; padding: 7px 10px; border: 1px solid var(--border-color); border-radius: 10px; }
.top3-list li strong { flex: 1; }
.top3-list li span { color: var(--text-secondary); font-variant-numeric: tabular-nums; font-size: 13px; }

@media (max-width: 1200px) {
  .judge-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 900px) {
  .demo-header, .section-heading { align-items: flex-start; flex-direction: column; }
  .section-heading p { text-align: left; }
  .two-column, .evidence-details { grid-template-columns: 1fr; }
}
@media (max-width: 560px) {
  .judge-grid { grid-template-columns: 1fr; }
  .demo-controls { width: 100%; flex-direction: column; align-items: stretch; }
  .mode-select { width: 100%; }
}
</style>
