import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { RealtimeEvent } from '@/types'
import { getRecentEvents } from '@/api'

export const useRealtimeStore = defineStore('realtime', () => {
  const events = ref<RealtimeEvent[]>([])
  let intervalId: number | null = null

  async function fetchEvents() {
    const result = await getRecentEvents()
    if (result.success && result.data?.length) {
      events.value = result.data
    }
  }

  async function startPolling() {
    await fetchEvents()
    intervalId = window.setInterval(async () => {
      await fetchEvents()
    }, 15000)
  }

  function stopPolling() {
    if (intervalId !== null) {
      clearInterval(intervalId)
      intervalId = null
    }
  }

  return { events, startPolling, stopPolling }
})
