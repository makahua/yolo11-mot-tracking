<script setup lang="ts">
import type { PropType } from 'vue';

import type { AssetCard, ScenarioPreset } from '../types/dashboard';

defineProps({
  assetCards: {
    type: Array as PropType<AssetCard[]>,
    required: true,
  },
  flowSteps: {
    type: Array as PropType<string[]>,
    required: true,
  },
  currentPreset: {
    type: Object as PropType<ScenarioPreset>,
    required: true,
  },
})
</script>

<template>
  <section class="detail-grid assets-grid">
    <article class="panel asset-panel">
      <div class="panel-head compact">
        <div>
          <p class="panel-kicker">项目资产</p>
          <h2>把训练、模型、推理资产可视化</h2>
        </div>
      </div>

      <div class="asset-grid">
        <article v-for="item in assetCards" :key="item.label" class="asset-card">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <p>{{ item.detail }}</p>
        </article>
      </div>
    </article>

    <article class="panel flow-panel">
      <div class="panel-head compact">
        <div>
          <p class="panel-kicker">工作流</p>
          <h2>现在已经具备的页面能力</h2>
        </div>
      </div>

      <div class="flow-list">
        <article v-for="(step, index) in flowSteps" :key="step" class="flow-item">
          <span>{{ String(index + 1).padStart(2, '0') }}</span>
          <p>{{ step }}</p>
        </article>
      </div>

      <div class="hint-card strong">
        <p class="panel-kicker">当前预设</p>
        <h3>{{ currentPreset.title }}</h3>
        <p>{{ currentPreset.summary }}</p>
      </div>
    </article>
  </section>
</template>