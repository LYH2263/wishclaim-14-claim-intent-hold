<template>
  <div class="wall">
    <h1 class="serif">我的认领</h1>
    <input v-model="name" @change="load" placeholder="认领人名" />
    <article v-for="w in rows" :key="w.id" class="card" @click="$router.push('/wishes/'+w.id)">
      <h3>{{ w.title }}</h3>
      <span v-if="w.status==='held'" class="tag hold">
        暂挂中 · 剩 {{ fmtRemain(remainSec(w.hold_until, now)) }} · 待确认转正
      </span>
      <span v-else class="tag">{{ w.status }} · 到期 {{ w.expires_at }}</span>
    </article>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
import { useNow, remainSec, fmtRemain } from '../countdown'
const name = ref('访客')
const rows = ref([])
const now = useNow()
async function load() { rows.value = await api('/mine?claimer=' + encodeURIComponent(name.value)) }
onMounted(load)
</script>
