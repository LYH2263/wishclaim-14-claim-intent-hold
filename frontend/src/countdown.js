import { ref, onMounted, onUnmounted } from 'vue'

// Ticking clock so hold countdowns stay live on wall / detail / mine.
export function useNow(intervalMs = 1000) {
  const now = ref(Date.now())
  let t
  onMounted(() => { t = setInterval(() => { now.value = Date.now() }, intervalMs) })
  onUnmounted(() => clearInterval(t))
  return now
}

export function remainSec(iso, nowMs) {
  if (!iso) return null
  return Math.max(0, Math.floor((new Date(iso).getTime() - nowMs) / 1000))
}

export function fmtRemain(sec) {
  if (sec == null) return ''
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  return h
    ? `${h}h${String(m).padStart(2, '0')}m`
    : `${m}m${String(s).padStart(2, '0')}s`
}
