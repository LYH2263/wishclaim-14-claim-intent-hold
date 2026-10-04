<template>
  <div class="wall">
    <h1 class="serif">我的认领</h1>
    <input v-model="name" @change="load" placeholder="认领人名" />
    <p v-if="err" class="err">{{ err }}</p>
    <article v-for="w in rows" :key="w.id" class="card" :class="{ held: w.status==='held' }">
      <h3>{{ w.title }}</h3>
      <span class="tag">{{ w.status }} · 到期 {{ w.expires_at || '—' }}</span>
      <HoldBadge :w="w" @expired="load" />
      <div v-if="w.status==='held' && w.hold_claimer===name" style="margin-top:8px">
        <button @click="confirm(w)">确认转正</button>
      </div>
    </article>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
import HoldBadge from '../components/HoldBadge.vue'
const name = ref('访客')
const rows = ref([])
const err = ref('')
async function load() { err.value=''; try { rows.value = await api('/mine?claimer=' + encodeURIComponent(name.value)) } catch(e){ err.value=e.message } }
async function confirm(w) {
  err.value=''
  try { await api('/wishes/'+w.id+'/confirm',{method:'POST',body:JSON.stringify({claimer:name.value})}); await load() }
  catch(e){ err.value=e.message }
}
onMounted(load)
</script>
