<template>
  <div class="wall">
    <h1 class="serif">愿望墙</h1>
    <p class="tag">无顶栏 · 瀑布流 · 点卡片认领</p>
    <div class="masonry">
      <article v-for="w in rows" :key="w.id" class="card" @click="$router.push('/wishes/'+w.id)">
        <h3>{{ w.title || '（无标题）' }}</h3>
        <p>{{ w.note }}</p>
        <span class="tag">{{ w.status }} · {{ w.data_quality }}</span>
        <span v-if="w.status==='held'" class="tag hold">
          暂挂中 · {{ w.hold_claimer }} · 剩 {{ fmtRemain(remainSec(w.hold_until, now)) }}
        </span>
      </article>
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
import { useNow, remainSec, fmtRemain } from '../countdown'
const rows = ref([])
const now = useNow()
onMounted(async () => { rows.value = await api('/wishes') })
</script>
