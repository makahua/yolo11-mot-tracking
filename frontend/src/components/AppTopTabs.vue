<script setup lang="ts">
import type { PropType } from 'vue';

import type { ViewMode, ViewTab } from '../types/dashboard';

defineProps({
  tabs: {
    type: Array as PropType<ViewTab[]>,
    required: true,
  },
  activeView: {
    type: String as PropType<ViewMode>,
    required: true,
  },
  runtimeLabel: {
    type: String,
    required: true,
  },
})

const emit = defineEmits<{
  change: [value: ViewMode]
}>()
</script>

<template>
  <section class="topbar panel">
    <div class="topbar-brand">
      <p class="eyebrow">Tracking Console</p>
      <div>
        <h2>YOLOv11 人群跟踪工作台</h2>
        <p>把实时演示、MOT17 验证、图片检测和视频处理收拢到一个顶部导航里。</p>
      </div>
    </div>

    <div class="topbar-rail">
      <div class="topbar-runtime">
        <span class="status-dot"></span>
        <strong>{{ runtimeLabel }}</strong>
      </div>

      <div class="topbar-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="top-tab"
          :data-active="activeView === tab.key"
          @click="emit('change', tab.key)"
        >
          <strong>{{ tab.label }}</strong>
          <span>{{ tab.hint }}</span>
        </button>
      </div>
    </div>
  </section>
</template>
