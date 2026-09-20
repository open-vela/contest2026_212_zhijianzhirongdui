import { ref, onMounted, onUnmounted } from 'vue'

// 每秒跳动一次的时钟，用于「最后心跳 x 秒前」等相对时间展示
export function useNowTick(intervalMs = 1000) {
  const now = ref(Date.now())
  let timer: number | null = null
  onMounted(() => {
    timer = window.setInterval(() => { now.value = Date.now() }, intervalMs)
  })
  onUnmounted(() => {
    if (timer !== null) window.clearInterval(timer)
  })
  return now
}

export function timeAgo(iso: string | null | undefined, nowMs: number): string {
  if (!iso) return '—'
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return '—'
  const diff = Math.max(0, nowMs - t)
  const s = Math.floor(diff / 1000)
  if (s < 60) return `${s} 秒前`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} 分钟前`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} 小时前`
  return `${Math.floor(h / 24)} 天前`
}
