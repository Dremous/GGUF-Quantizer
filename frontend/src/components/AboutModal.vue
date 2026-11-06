<script setup>
import { ref, watch } from 'vue'
import { health } from '../api'

const props = defineProps({
  open: { type: Boolean, default: false },
})
const emit = defineEmits(['close'])

const info = ref(null)
const loading = ref(false)

async function loadInfo() {
  loading.value = true
  try {
    info.value = await health()
  } catch {
    info.value = null
  } finally {
    loading.value = false
  }
}

// 每次打开时拉取最新信息
watch(
  () => props.open,
  (v) => {
    if (v) loadInfo()
  }
)

function onKey(e) {
  if (e.key === 'Escape' && props.open) emit('close')
}
window.addEventListener('keydown', onKey)
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition duration-150 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="open"
        class="fixed inset-0 z-50 grid place-items-center bg-slate-950/70 px-4 backdrop-blur-sm"
        @click.self="emit('close')"
      >
        <div
          class="w-full max-w-md overflow-hidden rounded-2xl border border-white/10 bg-slate-900 shadow-2xl shadow-black/50"
        >
          <!-- 标题栏 -->
          <div class="flex items-center gap-3 border-b border-white/10 px-6 py-4">
            <div
              class="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-emerald-400 to-teal-500 text-sm font-black text-emerald-950"
            >
              GQ
            </div>
            <div class="flex-1">
              <h3 class="text-[15px] font-bold text-white">关于 GGUF Quantizer</h3>
              <p class="text-xs text-slate-400">版本与运行环境信息</p>
            </div>
            <button
              class="grid h-8 w-8 place-items-center rounded-lg text-slate-400 transition-colors hover:bg-white/10 hover:text-white"
              aria-label="关闭"
              @click="emit('close')"
            >
              ✕
            </button>
          </div>

          <!-- 内容 -->
          <div class="px-6 py-5">
            <div v-if="loading" class="py-6 text-center text-sm text-slate-400">加载中…</div>

            <div v-else-if="info" class="space-y-3 text-sm">
              <!-- llama.cpp 版本：重点展示 -->
              <div
                class="flex items-center justify-between rounded-xl border border-emerald-400/20 bg-emerald-400/[0.07] px-4 py-3"
              >
                <span class="text-slate-300">llama.cpp 版本</span>
                <span class="font-mono font-bold text-emerald-300">{{ info.llama_cpp_version }}</span>
              </div>

              <div class="flex items-center justify-between px-1">
                <span class="text-slate-400">应用版本</span>
                <span class="font-mono text-slate-200">{{ info.version }}</span>
              </div>
              <div class="flex items-center justify-between px-1">
                <span class="text-slate-400">量化工具路径</span>
                <span class="font-mono text-xs text-slate-200">{{ info.quant_binary }}</span>
              </div>
              <div class="flex items-center justify-between px-1">
                <span class="text-slate-400">可用磁盘</span>
                <span class="font-mono text-slate-200">{{ info.disk_free_gib }} GiB</span>
              </div>
              <div class="flex items-center justify-between px-1">
                <span class="text-slate-400">进行中作业</span>
                <span class="font-mono text-slate-200">{{ info.active_jobs }}</span>
              </div>
            </div>

            <div v-else class="py-6 text-center text-sm text-rose-300">
              无法获取服务信息，请确认后端已启动。
            </div>
          </div>

          <!-- 底部技术栈 -->
          <div class="border-t border-white/10 px-6 py-3 text-center text-[11px] text-slate-500">
            FastAPI · Vue 3 · Vite · Tailwind · 基于 llama.cpp（MIT）
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
