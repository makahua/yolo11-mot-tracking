<script setup lang="ts">
import type { PropType } from 'vue'

import type { MOT17Result, MOT17Sequence, SummaryItem, TrackerMode, TrackerOption } from '../types/dashboard'

defineProps({
  mot17Sequences: {
    type: Array as PropType<MOT17Sequence[]>,
    required: true,
  },
  mot17Running: {
    type: Boolean,
    required: true,
  },
  mot17Error: {
    type: String,
    required: true,
  },
  mot17Result: {
    type: Object as PropType<MOT17Result | null>,
    required: true,
  },
  mot17Summary: {
    type: Array as PropType<SummaryItem[]>,
    required: true,
  },
  trackerOptions: {
    type: Array as PropType<TrackerOption[]>,
    required: true,
  },
})

const mot17SequencePath = defineModel<string>('mot17SequencePath', { required: true })
const mot17Tracker = defineModel<TrackerMode>('mot17Tracker', { required: true })
const mot17Confidence = defineModel<number>('mot17Confidence', { required: true })
const mot17ImageSize = defineModel<number>('mot17ImageSize', { required: true })

const emit = defineEmits<{
  run: []
}>()
</script>

<template>
  <section class="detail-grid">
    <article class="panel control-panel">
      <div class="panel-head compact">
        <div>
          <p class="panel-kicker">MOT17 测试</p>
          <h2>选择序列后直接测试</h2>
        </div>
      </div>

      <div class="field-group">
        <label class="input-card select-card">
          <span>序列路径</span>
          <select v-model="mot17SequencePath">
            <option value="" disabled>请选择一个 MOT17 序列</option>
            <option v-for="item in mot17Sequences" :key="item.path" :value="item.path">
              {{ item.split }} / {{ item.name }}
            </option>
          </select>
        </label>
      </div>

      <div class="field-group">
        <span class="field-label">跟踪算法</span>
        <div class="option-row three-up">
          <button
            v-for="item in trackerOptions"
            :key="item.key"
            type="button"
            class="choice-card"
            :data-active="mot17Tracker === item.key"
            @click="mot17Tracker = item.key"
          >
            <strong>{{ item.label }}</strong>
            <span>{{ item.note }}</span>
          </button>
        </div>
      </div>

      <div class="slider-grid">
        <label class="slider-card">
          <span>置信度阈值</span>
          <strong>{{ mot17Confidence.toFixed(2) }}</strong>
          <input v-model="mot17Confidence" type="range" min="0.15" max="0.65" step="0.01" />
        </label>
        <label class="slider-card">
          <span>输入尺寸</span>
          <strong>{{ mot17ImageSize }} px</strong>
          <input v-model="mot17ImageSize" type="range" min="640" max="1280" step="32" />
        </label>
      </div>

      <div class="action-row">
        <button type="button" class="primary-button" :disabled="mot17Running || !mot17SequencePath" @click="emit('run')">
          {{ mot17Running ? '测试中...' : '开始 MOT17 测试' }}
        </button>
      </div>
    </article>

    <article class="panel log-panel">
      <div class="panel-head compact">
        <div>
          <p class="panel-kicker">测试结果</p>
          <h2>序列输出与日志</h2>
        </div>
      </div>

      <div v-if="mot17Error" class="error-banner">{{ mot17Error }}</div>

      <div class="summary-grid result-summary-grid">
        <article v-for="item in mot17Summary" :key="item.label" class="summary-card">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </article>
      </div>

      <div v-if="mot17Result" class="result-stack">
        <video class="preview-media" :src="mot17Result.videoUrl" controls></video>
        <div class="link-row">
          <a class="inline-link" :href="mot17Result.videoUrl" target="_blank">打开结果视频</a>
          <a class="inline-link" :href="mot17Result.motUrl" target="_blank">打开 MOTChallenge 结果</a>
        </div>
        <div class="event-list compact-list">
          <article v-for="line in mot17Result.logs.slice().reverse().slice(0, 8)" :key="line" class="event-item">
            <div class="event-time">log</div>
            <div>
              <strong>{{ line }}</strong>
            </div>
          </article>
        </div>
      </div>
      <div v-else class="empty-state">还没有运行 MOT17 测试。</div>
    </article>
  </section>
</template>
