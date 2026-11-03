<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  types: { type: Object, required: true }, // { groups, types, default }
  upload: { type: Object, default: null },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['start'])

const typeSelect = ref(props.types?.default || 'q4_K_M')
const outputName = ref('')

const currentType = computed(() => props.types?.types?.[typeSelect.value])
const currentGroup = computed(() => props.types?.groups?.[currentType.value?.[1]] || '')

function defaultName() {
  const stem = (props.upload?.filename || 'model').replace(/\.gguf$/i, '')
  return `${stem}-${typeSelect.value}.gguf`
}

watch(typeSelect, () => {
  if (!outputName.value || outputName.value === lastSuggestion) {
    outputName.value = defaultName()
  }
})
let lastSuggestion = ''
watch([typeSelect, () => props.upload?.filename], () => {
  lastSuggestion = defaultName()
})

function start() {
  emit('start', {
    quantType: typeSelect.value,
    outputName: outputName.value || defaultName(),
  })
}
</script>

<template>
  <div>
    <div class="grid gap-5 sm:grid-cols-2">
      <!-- 量化类型 -->
      <div>
        <label class="mb-2 block text-xs font-medium tracking-wide text-slate-400">量化类型</label>
        <select
          v-model="typeSelect"
          class="gg-input w-full rounded-xl px-3.5 py-2.5 text-sm text-slate-100"
        >
          <optgroup v-for="(label, gid) in types.groups" :key="gid" :label="label">
            <option
              v-for="([desc, grp, rec], name) in types.types"
              v-show="grp === gid"
              :key="name"
              :value="name"
            >
              {{ name }}{{ rec ? ' ★' : '' }}
            </option>
          </optgroup>
        </select>
        <p class="mt-2.5 min-h-5 text-xs text-slate-400">
          <span v-if="currentType" class="text-slate-200">{{ typeSelect }}</span>
          <span v-if="currentGroup"> · {{ currentGroup }}</span>
          <span v-if="currentType"> — {{ currentType[0] }}</span>
        </p>
      </div>

      <!-- 输出文件名 -->
      <div>
        <label class="mb-2 block text-xs font-medium tracking-wide text-slate-400">输出文件名</label>
        <input
          v-model="outputName"
          type="text"
          :placeholder="defaultName()"
          class="gg-input w-full rounded-xl px-3.5 py-2.5 text-sm text-slate-100 placeholder:text-slate-500"
        />
        <p class="mt-2.5 min-h-5 text-xs text-slate-500">留空则自动生成，如 {{ defaultName() }}</p>
      </div>
    </div>

    <button
      class="group mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-emerald-400 to-teal-400 px-6 py-3 text-sm font-bold text-emerald-950 shadow-lg shadow-emerald-500/20 transition-all hover:shadow-emerald-400/30 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-40"
      :disabled="disabled || !upload"
      @click="start"
    >
      <span class="text-base transition-transform group-hover:translate-x-0.5">⚡</span>
      开始量化
    </button>
  </div>
</template>
