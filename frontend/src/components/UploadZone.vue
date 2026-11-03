<script setup>
import { ref } from 'vue'
import { upload } from '../api'

const emit = defineEmits(['uploaded'])
const fileInput = ref(null)
const busy = ref(false)
const error = ref('')
const dragging = ref(false)

function pick() {
  fileInput.value?.click()
}

function onFileChange(e) {
  const f = e.target.files?.[0]
  if (f) handleFile(f)
  e.target.value = ''
}

function onDrop(e) {
  dragging.value = false
  const f = e.dataTransfer?.files?.[0]
  if (f) handleFile(f)
}

async function handleFile(file) {
  error.value = ''
  if (!/\.gguf$/i.test(file.name)) {
    error.value = '仅接受 .gguf 文件'
    return
  }
  busy.value = true
  try {
    const data = await upload(file)
    emit('uploaded', {
      id: data.upload_id,
      filename: data.filename,
      size_gib: data.size_gib,
    })
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div>
    <div
      class="flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-12 text-center transition-all duration-200"
      :class="
        dragging
          ? 'border-emerald-400/70 bg-emerald-400/10'
          : 'border-white/12 bg-white/[0.02] hover:border-emerald-400/40 hover:bg-white/[0.04]'
      "
      @click="pick"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDrop"
    >
      <input ref="fileInput" type="file" accept=".gguf" class="hidden" @change="onFileChange" />
      <div
        class="mb-4 grid h-16 w-16 place-items-center rounded-2xl bg-gradient-to-br from-emerald-400 to-teal-500 text-3xl shadow-lg shadow-emerald-500/25"
      >
        <span v-if="busy" class="h-7 w-7 animate-spin rounded-full border-[3px] border-emerald-900/30 border-t-emerald-900"></span>
        <span v-else class="text-emerald-950">⬆</span>
      </div>
      <p class="text-base font-semibold text-slate-100">
        {{ busy ? '上传中…' : '点击选择或拖拽 GGUF 文件到此' }}
      </p>
      <p class="mt-1.5 text-sm text-slate-400">仅接受 FP16（float16 类型）的 GGUF 模型文件 · 上限由服务端配置</p>
    </div>

    <p v-if="error" class="mt-3 flex items-center gap-1.5 text-sm text-rose-400">
      <span class="text-base leading-none">⚠</span>{{ error }}
    </p>
  </div>
</template>
