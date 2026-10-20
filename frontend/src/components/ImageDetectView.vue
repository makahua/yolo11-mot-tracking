<script setup lang="ts">
import type { PropType } from 'vue'

import type { ImageResult, SummaryItem } from '../types/dashboard'

defineProps({
  imageFileName: {
    type: String,
    required: true,
  },
  imageLocalPreview: {
    type: String,
    required: true,
  },
  imageRunning: {
    type: Boolean,
    required: true,
  },
  imageError: {
    type: String,
    required: true,
  },
  imageResult: {
    type: Object as PropType<ImageResult | null>,
    required: true,
  },
  imageSummary: {
    type: Array as PropType<SummaryItem[]>,
    required: true,
  },
  hasImageFile: {
    type: Boolean,
    required: true,
  },
})

const confidence = defineModel<number>('confidence', { required: true })
const imageSize = defineModel<number>('imageSize', { required: true })

const emit = defineEmits<{
  'file-change': [event: Event]
  run: []
}>()
</script>

<template>
  <section class="detail-grid">
    <article class="panel control-panel">
      <div class="panel-head compact">
        <div>
          <p class="panel-kicker">图片检测</p>
          <h2>上传单张图片进行人物检测</h2>
        </div>
      </div>

      <label class="upload-card">
        <span>选择图片文件</span>
        <input accept="image/*" type="file" @change="emit('file-change', $event)" />
        <strong>{{ imageFileName || '尚未选择文件' }}</strong>
      </label>

      <div class="slider-grid">
        <label class="slider-card">
          <span>置信度阈值</span>
          <strong>{{ confidence.toFixed(2) }}</strong>
          <input v-model="confidence" type="range" min="0.15" max="0.65" step="0.01" />
        </label>
        <label class="slider-card">
          <span>输入尺寸</span>
          <strong>{{ imageSize }} px</strong>
          <input v-model="imageSize" type="range" min="640" max="1280" step="32" />
        </label>
      </div>

      <div class="action-row">
        <button type="button" class="primary-button" :disabled="imageRunning || !hasImageFile" @click="emit('run')">
          {{ imageRunning ? '检测中...' : '开始图片检测' }}
        </button>
      </div>
    </article>

    <article class="panel log-panel">
      <div class="panel-head compact">
        <div>
          <p class="panel-kicker">检测结果</p>
          <h2>原图与标注图对照</h2>
        </div>
      </div>

      <div v-if="imageError" class="error-banner">{{ imageError }}</div>

      <div class="summary-grid result-summary-grid">
        <article v-for="item in imageSummary" :key="item.label" class="summary-card">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </article>
      </div>

      <div v-if="imageLocalPreview || imageResult" class="media-grid">
        <div v-if="imageLocalPreview" class="media-card">
          <p class="panel-kicker">上传原图</p>
          <img class="preview-media image-preview" :src="imageLocalPreview" alt="原始图片" />
        </div>
        <div v-if="imageResult" class="media-card">
          <p class="panel-kicker">检测结果</p>
          <img class="preview-media image-preview" :src="imageResult.imageUrl" alt="检测结果图片" />
        </div>
      </div>

      <div v-if="imageResult" class="sequence-table detection-table">
        <div class="table-row table-head-row">
          <span>#</span>
          <span>置信度</span>
          <span>坐标框</span>
        </div>
        <div
          v-for="(item, index) in imageResult.detections"
          :key="`${index}-${item.confidence}`"
          class="table-row detection-row"
        >
          <span>{{ index + 1 }}</span>
          <span>{{ item.confidence }}</span>
          <span>{{ item.box.join(', ') }}</span>
        </div>
      </div>
      <div v-else class="empty-state">上传图片后点击“开始图片检测”查看结果。</div>
    </article>
  </section>
</template>
