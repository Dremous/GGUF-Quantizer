<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { cancel, downloadUrl } from '../api'

const props = defineProps({
  job: { type: Object, required: true },
})

const emit = defineEmits(['cancelled'])
const logBox = ref(null)
const cancelling = ref(false)

const stateInfo = computed(() => {
  const map = {
    queued: { label: '排队中', cls: 'bg-slate-500/20 text-slate-300 border-slate-400/20' },
    running: { label: '量化中', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-400/30' },
    done: { label: '已完成', cls: 'bg-emerald-500/20 text-emerald-300 border-emerald-400/30' },
    error: { label: '失败', cls: 'bg-rose-500/15 text-rose-300 border-rose-400/30' },
    cancelled: { label: '已取消', cls: 'bg-amber-500/15 text-amber-300 border-amber-400/30' },
  }
  return map[props.job.state] || map.queued
})

const isActive = computed(() => ['queued', 'running'].includes(props.job.state))
const isDone = computed(() => props.job.state === 'done')

watch(
  () => props.job.log.length,
  async () => {
    await nextTick()
    if (logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight
  },
)

async function doCancel() {
  cancelling.value = true
  try {
    await cancel(props.job.id)
    emit('cancelled')
  } finally {
    cancelling.value = false
  }
}
</script>

<template>
  <div>
    <!-- 状态头 -->
    <div class="mb-4 flex flex-wrap items-center gap-3">
      <span
        class="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wide"
        :class="stateInfo.cls"
      >
        <span v-if="isActive" class="h-2 w-2 animate-pulse rounded-full bg-current"></span>
        {{ stateInfo.label }}
      </span>
      <span class="truncate text-sm text-slate-400">{{ job.output_name }} · {{ job.quant_type }}</span>
    </div>

    <!-- 进度条 -->
    <div class="h-2 overflow-hidden rounded-full bg-white/5">
      <div
        v-if="isActive"
        class="h-full rounded-full bg-gradient-to-r from-emerald-400 to-teal-400 shadow-[0_0_12px_rgba(16,185,129,0.6)]"
        :style="{ width: '35%' }"
      >
        <div class="h-full w-full animate-[indet_1.3s_ease-in-out_infinite] bg-gradient-to-r from-transparent via-white/40 to-transparent"></div>
      </div>
      <div
        v-else
        class="h-full rounded-full bg-gradient-to-r from-emerald-400 to-teal-400 transition-all duration-500"
        :style="{ width: (job.progress || 0) + '%' }"
      ></div>
    </div>

    <!-- 日志终端 -->
    <div
      ref="logBox"
      class="mt-4 h-56 overflow-y-auto rounded-xl border border-white/8 bg-black/40 p-4 font-mono text-[12.5px] leading-relaxed text-slate-300"
    >
      <p v-for="(line, i) in job.log" :key="i" class="whitespace-pre-wrap break-all">{{ line }}</p>
      <p v-if="!job.log.length" class="text-slate-500">等待日志输出…</p>
    </div>

    <p v-if="job.error" class="mt-3 flex items-center gap-1.5 text-sm text-rose-400">
      <span class="text-base leading-none">⚠</span>{{ job.error }}
    </p>

    <!-- 操作 -->
    <div class="mt-4 flex items-center justify-between gap-3">
      <button
        v-if="isActive"
        class="rounded-lg border border-rose-400/30 px-4 py-2 text-sm font-medium text-rose-300 transition-colors hover:border-rose-400/60 hover:bg-rose-400/10 disabled:opacity-40"
        :disabled="cancelling"
        @click="doCancel"
      >
        {{ cancelling ? '取消中…' : '取消' }}
      </button>
      <span v-else></span>

      <a
        v-if="isDone"
        :href="downloadUrl(job.id)"
        class="inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-emerald-400 to-teal-400 px-5 py-2.5 text-sm font-bold text-emerald-950 shadow-lg shadow-emerald-500/20 transition-all hover:shadow-emerald-400/30 active:scale-[0.98]"
      >
        ⬇ 下载量化结果
      </a>
    </div>
  </div>
</template>

<style>
@keyframes indet {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(200%); }
}
</style>
