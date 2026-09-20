<template>
  <div class="dec-page">
    <div class="dec-toolbar glass-card">
      <div class="toolbar-title">
        <span class="title-text">实时融合决策流</span>
        <span class="ws-chip" :class="store.wsConnected ? 'on' : 'off'">
          <i class="dot"></i>{{ store.wsConnected ? 'WS 已连接' : 'WS 断开' }}
        </span>
      </div>
      <div class="toolbar-actions">
        <n-button
          size="small" :type="store.paused ? 'warning' : 'default'"
          @click="store.setPaused(!store.paused)"
        >
          <template #icon>
            <n-icon :component="store.paused ? PlayOutline : PauseOutline" />
          </template>
          {{ store.paused ? '继续' : '暂停' }}
        </n-button>
        <n-button size="small" @click="store.clearDecisions()">
          <template #icon><n-icon :component="TrashOutline" /></template>
          清屏
        </n-button>
      </div>
    </div>

    <div class="timeline glass-card">
      <div v-if="store.decisions.length === 0" class="empty">
        <n-icon :component="RadioOutline" :size="34" />
        <div class="empty-title">等待决策事件…</div>
        <div class="empty-text">运行 <code>python scripts/simulate_edge.py --scenario allow --port 11883</code></div>
      </div>

      <div
        v-for="d in store.decisions" :key="d.key"
        class="tl-item"
      >
        <div class="tl-axis">
          <span class="tl-dot" :class="actionMeta(d.action).cls"></span>
          <span class="tl-line"></span>
        </div>

        <div class="tl-card">
          <div class="tl-head">
            <span class="action-tag" :class="actionMeta(d.action).cls">
              <n-icon :component="actionMeta(d.action).icon" :size="13" />
              {{ actionMeta(d.action).text }}
            </span>
            <span class="person">{{ d.person_name }}</span>
            <span v-if="d.evidence_mode === 'research'" class="research-badge">研究模式</span>
            <span class="spacer"></span>
            <span class="policy mono">{{ d.policy_id }}</span>
            <span class="time">{{ fmtTime(d.receivedAt) }}</span>
          </div>

          <div class="tl-explain">{{ d.explanation || '（无解释文本）' }}</div>

          <div class="tl-bottom">
            <div class="weights">
              <div v-for="w in weightBars(d)" :key="w.key" class="w-row">
                <span class="w-label">{{ w.label }}</span>
                <div class="w-bar">
                  <div class="w-fill" :class="w.key" :style="{ width: `${w.pct}%` }"></div>
                </div>
                <span class="w-pct mono">{{ w.pct }}%</span>
              </div>
            </div>
            <div class="meta-side">
              <div class="conf">
                <label>融合置信</label>
                <b>{{ pct(d.confidence) }}</b><span class="conf-pct">%</span>
              </div>
              <div class="node-id">
                <label>边缘节点</label>
                <router-link class="mono" :to="`/admin/nodes/${encodeURIComponent(d.node_id)}`">
                  {{ d.node_id }}
                </router-link>
              </div>
            </div>
          </div>

          <!-- 研究模式 face/gait 数据折叠 -->
          <n-collapse v-if="hasResearch(d)" :default-expanded-keys="[]" ghost>
            <n-collapse-item title="研究模式证据（face/gait 离线数据，非交付路径）" name="r">
              <div class="research-grid">
                <div v-if="num(d.weights_used.face) !== null" class="r-item">
                  <label>人脸权重</label><span class="mono">{{ num(d.weights_used.face) }}</span>
                </div>
                <div v-if="num(d.weights_used.gait) !== null" class="r-item">
                  <label>步态权重</label><span class="mono">{{ num(d.weights_used.gait) }}</span>
                </div>
                <div v-if="d.scenario" class="r-item">
                  <label>场景</label><span class="mono">{{ d.scenario }}</span>
                </div>
              </div>
            </n-collapse-item>
          </n-collapse>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { NButton, NIcon, NCollapse, NCollapseItem } from 'naive-ui'
import {
  PauseOutline, PlayOutline, TrashOutline, RadioOutline,
  CheckmarkCircleOutline, CloseCircleOutline, WarningOutline, AlertCircleOutline,
} from '@vicons/ionicons5'
import { useVelameshStore } from '@/stores/velamesh'
import type { DecisionItem } from '@/types/topology'

const store = useVelameshStore()

function actionMeta(action: string): { text: string; cls: string; icon: typeof CheckmarkCircleOutline } {
  switch (action) {
    case 'allow':
      return { text: '允许通行', cls: 'allow', icon: CheckmarkCircleOutline }
    case 'deny':
      return { text: '拒绝通行', cls: 'deny', icon: CloseCircleOutline }
    case 'alert':
      return { text: '告警 · 人工复核', cls: 'alert', icon: WarningOutline }
    case 'degrade':
      return { text: '降级运行', cls: 'degrade', icon: AlertCircleOutline }
    default:
      return { text: action || '未知', cls: 'unknown', icon: AlertCircleOutline }
  }
}

function pct(v: number): string {
  return Math.round(Math.min(1, Math.max(0, v)) * 100).toString()
}

function num(v: number | undefined): number | null {
  return typeof v === 'number' ? v : null
}

// 交付路径只展示 ble / motion 两条权重
function weightBars(d: DecisionItem) {
  const w = d.weights_used || {}
  return ([
    { key: 'ble', label: 'BLE 信标' },
    { key: 'motion', label: '在场 / 运动' },
  ] as const).map((x) => ({
    key: x.key,
    label: x.label,
    pct: Math.round((w[x.key] || 0) * 100),
  }))
}

function hasResearch(d: DecisionItem): boolean {
  return d.evidence_mode === 'research'
    || typeof d.weights_used.face === 'number'
    || typeof d.weights_used.gait === 'number'
}

function fmtTime(ts: number): string {
  const d = new Date(ts)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}
</script>

<style scoped>
.dec-page { display: flex; flex-direction: column; gap: 14px; height: 100%; }

.dec-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 18px;
}
.toolbar-title { display: flex; align-items: center; gap: 14px; }
.title-text { font-size: 17px; font-weight: 700; }
.toolbar-actions { display: flex; gap: 10px; }

.ws-chip {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; padding: 3px 10px; border-radius: 999px;
  border: 1px solid var(--border-color); color: var(--text-secondary);
}
.ws-chip .dot { width: 7px; height: 7px; border-radius: 50%; background: #636366; }
.ws-chip.on { color: #6ee7a0; border-color: rgba(64, 220, 140, 0.35); }
.ws-chip.on .dot { background: #3ddc84; box-shadow: 0 0 8px #3ddc84; }
.ws-chip.off .dot { background: #ff6b6b; }

.timeline {
  flex: 1; overflow-y: auto; padding: 20px 22px; min-height: 0;
}

.empty {
  height: 100%; min-height: 320px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 10px; color: var(--text-secondary);
}
.empty-title { font-size: 15px; font-weight: 700; color: var(--text-primary); }
.empty-text { font-size: 12px; }
.empty-text code { color: #a9d2ff; }

.tl-item { display: flex; gap: 12px; }
.tl-axis { display: flex; flex-direction: column; align-items: center; width: 14px; }
.tl-dot {
  width: 12px; height: 12px; border-radius: 50%; margin-top: 14px;
  border: 2px solid; background: var(--bg-primary); flex-shrink: 0;
}
.tl-dot.allow { border-color: #3ddc84; box-shadow: 0 0 8px rgba(61, 220, 132, 0.6); }
.tl-dot.deny { border-color: #ff6b6b; box-shadow: 0 0 8px rgba(255, 107, 107, 0.6); }
.tl-dot.alert { border-color: #ffb020; box-shadow: 0 0 8px rgba(255, 176, 32, 0.6); }
.tl-dot.degrade { border-color: #ffe066; box-shadow: 0 0 8px rgba(255, 224, 102, 0.6); }
.tl-dot.unknown { border-color: #98989d; }
.tl-line { width: 2px; flex: 1; background: var(--border-color); margin: 3px 0; min-height: 22px; }

.tl-card {
  flex: 1; margin-bottom: 14px;
  border-radius: 14px; padding: 13px 16px 10px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border-color);
}
.tl-head { display: flex; align-items: center; gap: 10px; }

.action-tag {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 12px; font-weight: 700;
  padding: 3px 10px; border-radius: 8px;
}
.action-tag.allow { color: #3ddc84; background: rgba(61, 220, 132, 0.12); }
.action-tag.deny { color: #ff7b7b; background: rgba(255, 107, 107, 0.12); }
.action-tag.alert { color: #ffb020; background: rgba(255, 176, 32, 0.12); }
.action-tag.degrade { color: #ffe066; background: rgba(255, 224, 102, 0.12); }
.action-tag.unknown { color: var(--text-secondary); background: rgba(255, 255, 255, 0.05); }

.person { font-size: 13.5px; font-weight: 700; }
.research-badge {
  font-size: 10px; padding: 1.5px 7px; border-radius: 6px;
  color: #c9a7ff; background: rgba(160, 120, 255, 0.14);
  border: 1px solid rgba(160, 120, 255, 0.35);
}
.spacer { flex: 1; }
.policy { font-size: 11px; color: var(--text-secondary); }
.time { font-size: 11.5px; color: var(--text-tertiary); }

.tl-explain {
  margin-top: 10px; font-size: 13px; line-height: 1.75;
  color: var(--text-primary);
}

.tl-bottom {
  margin-top: 12px; display: flex; gap: 26px;
  padding-top: 10px; border-top: 1px solid rgba(255, 255, 255, 0.06);
}
.weights { flex: 1; display: flex; flex-direction: column; gap: 7px; min-width: 0; }
.w-row { display: flex; align-items: center; gap: 10px; }
.w-label { font-size: 11.5px; color: var(--text-secondary); width: 82px; flex-shrink: 0; }
.w-bar {
  flex: 1; height: 7px; border-radius: 4px;
  background: rgba(255, 255, 255, 0.07); overflow: hidden;
}
.w-fill { height: 100%; border-radius: 4px; transition: width 0.4s ease; }
.w-fill.ble { background: linear-gradient(90deg, #2f6fed, #58a6ff); }
.w-fill.motion { background: linear-gradient(90deg, #b06ae0, #d18cf5); }
.w-pct { font-size: 11px; color: var(--text-secondary); width: 38px; text-align: right; }

.meta-side { display: flex; flex-direction: column; gap: 6px; align-items: flex-end; }
.conf { display: flex; align-items: baseline; gap: 2px; }
.conf label { font-size: 11px; color: var(--text-secondary); margin-right: 7px; }
.conf b { font-size: 20px; font-weight: 800; color: #7dc4ff; }
.conf-pct { font-size: 11px; color: var(--text-secondary); }
.node-id { display: flex; align-items: center; gap: 7px; font-size: 11px; }
.node-id label { color: var(--text-secondary); }
.node-id a { color: #7dc4ff; text-decoration: none; }
.node-id a:hover { text-decoration: underline; }

.research-grid { display: flex; gap: 22px; flex-wrap: wrap; }
.r-item { display: flex; gap: 8px; font-size: 12px; }
.r-item label { color: var(--text-secondary); }
</style>
