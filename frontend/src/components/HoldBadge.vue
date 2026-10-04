<template>
  <span v-if="active" class="hold-badge" :class="{ urgent: remaining <= 30 }">
    ⏳ 意向暂挂 · {{ w.hold_claimer || '—' }} · {{ fmt(remaining) }}
  </span>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'

const props = defineProps({ w: { type: Object, required: true } })
const emit = defineEmits(['expired'])

// Anchor the countdown to the server snapshot, not the local clock:
// remaining0 = hold_until - server_now, then tick down locally.
const remaining = ref(0)
let timer = null
let expiredEmitted = false

const active = computed(() => props.w && props.w.hold_active && !!props.w.hold_until)

function sync() {
  if (!props.w || !props.w.hold_until) { remaining.value = 0; return }
  const until = Date.parse(props.w.hold_until)
  const base = props.w.server_now ? Date.parse(props.w.server_now) : Date.now()
  remaining.value = Math.max(0, Math.round((until - base) / 1000))
  expiredEmitted = remaining.value === 0
}

function fmt(s) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60
  const mm = String(m).padStart(2, '0'), ss = String(sec).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

watch(() => props.w, sync, { deep: true })

onMounted(() => {
  sync()
  timer = setInterval(() => {
    if (remaining.value > 0) { remaining.value -= 1 }
    else if (active.value && !expiredEmitted) { expiredEmitted = true; emit('expired') }
  }, 1000)
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.hold-badge {
  display: inline-block; font-size: 12px; color: #8a4b4b;
  background: #fde2df; border: 1px solid #f3c4bf; border-radius: 999px;
  padding: 2px 10px; margin-top: 6px; font-variant-numeric: tabular-nums;
}
.hold-badge.urgent { background: #fbd0cb; border-color: #ec938a; animation: pulse 1s infinite; }
@keyframes pulse { 50% { opacity: .55; } }
</style>
