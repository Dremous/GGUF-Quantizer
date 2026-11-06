<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import * as api from './api'
import HealthBadge from './components/HealthBadge.vue'
import UploadZone from './components/UploadZone.vue'
import QuantForm from './components/QuantForm.vue'
import JobPanel from './components/JobPanel.vue'
import AboutModal from './components/AboutModal.vue'

const types = ref(null)
const upload = ref(null)
const job = ref(null)
const aboutOpen = ref(false)
let pollTimer = null

onMounted(async () => {
  try {
    types.value = await api.quantTypes()
  } catch {
    /* types 加载失败时表单不可用，健康徽章会显示异常 */
  }
})

onBeforeUnmount(() => stopPoll())

const jobActive = computed(() => !!job.value && ['queued', 'running'].includes(job.value.state))
const canStart = computed(() => !!upload.value && !jobActive.value)

function onUploaded(data) {
  upload.value = data
}

async function onStart({ quantType, outputName }) {
  if (!upload.value) return
  job.value = reactive({
    id: null,
    state: 'queued',
    progress: 0,
    output_name: outputName,
    quant_type: quantType,
    log: [],
    error: null,
  })
  try {
    const res = await api.quantize({
      upload_id: upload.value.id,
      quant_type: quantType,
      output_name: outputName,
      source_name: upload.value.filename,
    })
    job.value.id = res.job_id
    poll()
    pollTimer = setInterval(poll, 1500)
  } catch (e) {
    job.value.state = 'error'
    job.value.error = e.message
  }
}

async function poll() {
  if (!job.value?.id) return
  try {
    const j = await api.job(job.value.id, job.value.log.length)
    job.value.log.push(...j.log)
    job.value.state = j.state
    job.value.progress = j.progress
    job.value.error = j.error
    job.value.output_name = j.output_name
    job.value.quant_type = j.quant_type
    if (['done', 'error', 'cancelled'].includes(j.state)) stopPoll()
  } catch (e) {
    job.value.state = 'error'
    job.value.error = e.message
    stopPoll()
  }
}

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function onJobCancelled() {
  job.value.state = 'cancelled'
  stopPoll()
}

function onJobCleaned() {
  reset()
}

function reset() {
  stopPoll()
  job.value = null
  upload.value = null
}
</script>

<template>
  <div class="gg-bg min-h-screen">
    <div class="mx-auto w-full max-w-3xl px-5 pb-24 pt-10 sm:pt-14">
      <!-- 头部 -->
      <header class="mb-9 flex flex-wrap items-center gap-4">
        <div
          class="grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-emerald-400 to-teal-500 text-lg font-black text-emerald-950 shadow-lg shadow-emerald-500/30"
        >
          GQ
        </div>
        <div class="min-w-0 flex-1">
          <h1 class="text-xl font-bold tracking-tight text-white">GGUF Quantizer</h1>
          <p class="mt-0.5 text-[13px] text-slate-400">
            上传 FP16 GGUF → 选择量化参数 → 下载量化结果（基于 llama.cpp）
          </p>
        </div>
        <div class="flex items-center gap-2">
          <HealthBadge />
          <button
            class="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3.5 py-1.5 text-xs text-slate-300 transition-colors hover:border-emerald-400/40 hover:text-emerald-300"
            @click="aboutOpen = true"
          >
            <span aria-hidden="true">ⓘ</span> 关于
          </button>
        </div>
      </header>

      <!-- 步骤 1：上传 -->
      <section class="gg-card mb-5 rounded-2xl p-6">
        <div class="mb-5 flex items-center gap-3">
          <span
            class="grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-emerald-400/90 to-teal-400/90 text-[13px] font-bold text-emerald-950"
            >1</span
          >
          <h2 class="text-[15px] font-bold text-white">上传 FP16 GGUF</h2>
          <span class="text-xs text-slate-500">.gguf</span>
        </div>

        <UploadZone v-if="!upload" @uploaded="onUploaded" />

        <div
          v-else
          class="flex items-center gap-4 rounded-2xl border border-emerald-400/20 bg-emerald-400/[0.06] px-5 py-4"
        >
          <div
            class="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-emerald-400/15 text-lg text-emerald-300"
          >
            ✓
          </div>
          <div class="min-w-0 flex-1">
            <div class="truncate font-semibold text-slate-100">{{ upload.filename }}</div>
            <div class="mt-0.5 text-xs text-slate-400">{{ upload.size_gib }} GiB · 已就绪</div>
          </div>
          <button
            class="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-slate-400 transition-colors hover:border-rose-400/40 hover:text-rose-300"
            @click="reset"
          >
            更换
          </button>
        </div>
      </section>

      <!-- 步骤 2：参数 -->
      <section class="gg-card mb-5 rounded-2xl p-6">
        <div class="mb-5 flex items-center gap-3">
          <span
            class="grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-emerald-400/90 to-teal-400/90 text-[13px] font-bold text-emerald-950"
            >2</span
          >
          <h2 class="text-[15px] font-bold text-white">选择量化参数</h2>
          <span class="text-xs text-slate-500">类型 · 文件名</span>
        </div>
        <QuantForm
          v-if="types"
          :types="types"
          :upload="upload"
          :disabled="jobActive"
          @start="onStart"
        />
      </section>

      <!-- 步骤 3：作业 -->
      <section v-if="job" class="gg-card rounded-2xl p-6">
        <div class="mb-5 flex items-center gap-3">
          <span
            class="grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-emerald-400/90 to-teal-400/90 text-[13px] font-bold text-emerald-950"
            >3</span
          >
          <h2 class="text-[15px] font-bold text-white">量化进度与结果</h2>
          <span class="text-xs text-slate-500">实时日志</span>
        </div>
        <JobPanel :job="job" @cancelled="onJobCancelled" @cleaned="onJobCleaned" />
      </section>

      <footer class="mt-10 text-center text-xs text-slate-500">
        GGUF Quantizer · llama.cpp llama-quantize · FastAPI + Vue
      </footer>
    </div>

    <!-- 关于弹窗：展示 llama.cpp 版本等信息 -->
    <AboutModal :open="aboutOpen" @close="aboutOpen = false" />
  </div>
</template>
