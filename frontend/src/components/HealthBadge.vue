<script setup>
import { onMounted, ref } from 'vue'
import { health } from '../api'

const state = ref('loading') // loading | ok | error
const disk = ref(0)

onMounted(async () => {
  try {
    const h = await health()
    disk.value = h.disk_free_gib
    state.value = 'ok'
  } catch {
    state.value = 'error'
  }
})
</script>

<template>
  <div
    class="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3.5 py-1.5 text-xs text-slate-300"
  >
    <span class="relative flex h-2 w-2">
      <span
        v-if="state === 'ok'"
        class="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60"
      ></span>
      <span
        :class="state === 'ok' ? 'bg-emerald-400' : state === 'error' ? 'bg-rose-400' : 'bg-amber-400'"
        class="relative inline-flex h-2 w-2 rounded-full"
      ></span>
    </span>
    <template v-if="state === 'ok'">量化器就绪 · 可用磁盘 {{ disk }} GiB</template>
    <template v-else-if="state === 'error'">服务连接异常</template>
    <template v-else>连接中…</template>
  </div>
</template>
