<template>
  <div class="wall">
    <h1 class="serif">{{ w.title }}</h1>
    <p>{{ w.note }}</p>
    <p class="tag">状态 {{ w.status }} · 认领人 {{ w.claimer || '—' }}</p>
    <p v-if="w.status==='held'" class="tag hold">
      意向暂挂：{{ w.hold_claimer }} · 剩 {{ fmtRemain(remainSec(w.hold_until, now)) }}
      <template v-if="remainSec(w.hold_until, now)===0">（已到期，待回 open）</template>
    </p>
    <p v-if="err" class="err">{{ err }}</p>
    <input v-model="claimer" placeholder="你的名字" />
    <input v-model.number="holdSeconds" type="number" min="1" placeholder="暂挂秒数" />
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button @click="hold">认领暂挂</button>
      <button @click="confirm">确认转正</button>
      <button class="ghost" @click="release">释放</button>
      <button class="ghost" @click="fulfill">核销完成</button>
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
import { useNow, remainSec, fmtRemain } from '../countdown'
const props = defineProps({ id: String })
const w = ref({})
const claimer = ref('访客')
const holdSeconds = ref(300)
const err = ref('')
const now = useNow()
async function load() { w.value = await api('/wishes/' + props.id) }
async function act(path, body) {
  err.value = ''
  try { await api('/wishes/' + props.id + path, { method: 'POST', body: JSON.stringify(body) }); await load() }
  catch (e) { err.value = e.message }
}
const hold = () => act('/claim', { claimer: claimer.value, hold_seconds: holdSeconds.value })
const confirm = () => act('/confirm', { claimer: claimer.value })
const release = () => act('/release', {})
const fulfill = () => act('/fulfill', {})
onMounted(load)
</script>
