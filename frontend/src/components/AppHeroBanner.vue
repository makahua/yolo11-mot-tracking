<script setup lang="ts">
import type { PropType } from 'vue';

import type { RuntimeState, SummaryItem, ViewTab } from '../types/dashboard';

defineProps({
  currentTab: {
    type: Object as PropType<ViewTab>,
    required: true,
  },
  runtimeState: {
    type: String as PropType<RuntimeState>,
    required: true,
  },
  runtimeLabel: {
    type: String,
    required: true,
  },
  backendHint: {
    type: String,
    required: true,
  },
  monitorHighlights: {
    type: Array as PropType<SummaryItem[]>,
    required: true,
  },
})
</script>

<template>
  <section class="masthead panel">
    <div class="hero-copy">
      <p class="eyebrow">{{ currentTab.label }}</p>
      <h1>{{ currentTab.label }}工作区</h1>
      <p class="lead">
        {{ currentTab.hint }}。顶部切换页面，下面直接进入对应能力，不再把菜单塞进右侧栏里。
      </p>
    </div>

    <div class="hero-summary">
      <div class="status-chip" :data-state="runtimeState">
        <span class="status-dot"></span>
        <span>{{ runtimeLabel }}</span>
      </div>
      <p class="status-text">{{ backendHint }}</p>
      <div class="summary-grid">
        <article v-for="item in monitorHighlights" :key="item.label" class="summary-card">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </article>
      </div>
    </div>
  </section>
</template>
