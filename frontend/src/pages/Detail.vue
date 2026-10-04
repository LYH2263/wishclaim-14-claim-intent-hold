<template>
  <div class="wall">
    <h1 class="serif">{{ w.title }}</h1>
    <p>{{ w.note }}</p>
    <p class="tag">状态 {{ w.status }} · 认领人 {{ w.claimer || '—' }}</p>
    <HoldBadge :w="w" @expired="load" />
    <p v-if="err" class="err">{{ err }}</p>
    <input v-model="claimer" placeholder="你的名字" />
    <input v-model.number="holdSeconds" type="number" min="1" placeholder="暂挂秒数（>0）" />
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button class="ghost" @click="hold">暂挂意向</button>
      <button @click="confirm" :disabled="!canConfirm">确认转正</button>
      <button class="ghost" @click="claim">直接认领</button>
      <button class="ghost" @click="release">释放</button>
      <button class="ghost" @click="fulfill">核销完成</button>
    </div>
    <p v-if="w.status==='held'" class="tag">
      暂挂中：仅意向人 <strong>{{ w.hold_claimer }}</strong> 可在倒计时内确认转正；他人暂不可认领。
    </p>
  </div>
</template>
<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import HoldBadge from '../components/HoldBadge.vue'
const props = defineProps({ id: String })
const w = ref({})
const claimer = ref('访客')
const holdSeconds = ref(600)
const err = ref('')
const canConfirm = computed(() => w.value.status === 'held' && w.value.hold_claimer === claimer.value)
async function load() { w.value = await api('/wishes/' + props.id) }
function boom(e){ err.value = e.message }
async function hold() {
  err.value=''
  try { await api('/wishes/'+props.id+'/hold',{method:'POST',body:JSON.stringify({claimer:claimer.value,seconds:holdSeconds.value})}); await load() } catch(e){ boom(e) }
}
async function confirm() {
  err.value=''
  try { await api('/wishes/'+props.id+'/confirm',{method:'POST',body:JSON.stringify({claimer:claimer.value})}); await load() } catch(e){ boom(e) }
}
async function claim() {
  err.value=''; try { await api('/wishes/'+props.id+'/claim',{method:'POST',body:JSON.stringify({claimer:claimer.value})}); await load() } catch(e){ boom(e) }
}
async function release() {
  err.value=''; try { await api('/wishes/'+props.id+'/release',{method:'POST',body:'{}'}); await load() } catch(e){ boom(e) }
}
async function fulfill() {
  err.value=''; try { await api('/wishes/'+props.id+'/fulfill',{method:'POST',body:'{}'}); await load() } catch(e){ boom(e) }
}
onMounted(load)
</script>
