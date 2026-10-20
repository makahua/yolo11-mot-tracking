<script setup lang="ts">
import type { PropType } from 'vue'

import type { SummaryItem, TrackerMode, TrackerOption, VideoJobStatus, VideoResult } from '../types/dashboard'

defineProps({
  videoFileName: {
    type: String,
    required: true,
  },
  videoRunning: {
    type: Boolean,
    required: true,
  },
  videoError: {
    type: String,
    required: true,
  },
  videoResult: {
    type: Object as PropType<VideoResult | null>,
    required: true,
  },
  videoStatus: {
    type: Object as PropType<VideoJobStatus | null>,
    required: true,
  },
  videoSummary: {
    type: Array as PropType<SummaryItem[]>,
    required: true,
  },
  trackerOptions: {
    type: Array as PropType<TrackerOption[]>,
    required: true,
  },
  hasVideoFile: {
    type: Boolean,
    required: true,
  },
})

const videoTracker = defineModel<TrackerMode>('videoTracker', { required: true })
const videoConfidence = defineModel<number>('videoConfidence', { required: true })
const videoImageSize = defineModel<number>('videoImageSize', { required: true })

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
          <p class="panel-kicker">视频检测</p>
          <h2>上传视频生成跟踪结果</h2>
        </div>
      </div>

      <label class="upload-card">
        <span>选择视频文件</span>
        <input accept="video/*" type="file" @change="emit('file-change', $event)" />
        <strong>{{ videoFileName || '尚未选择文件' }}</strong>
      </label>

      <div class="field-group">
        <span class="field-label">跟踪算法</span>
        <div class="option-row three-up">
          <button
            v-for="item in trackerOptions"
            :key="item.key"
            type="button"
            class="choice-card"
            :data-active="videoTracker === item.key"
            @click="videoTracker = item.key"
          >
            <strong>{{ item.label }}</strong>
            <span>{{ item.note }}</span>
          </button>
        </div>
      </div>

      <div class="slider-grid">
        <label class="slider-card">
          <span>置信度阈值</span>
          <strong>{{ videoConfidence.toFixed(2) }}</strong>
          <input v-model="videoConfidence" type="range" min="0.15" max="0.65" step="0.01" />
        </label>
        <label class="slider-card">
          <span>输入尺寸</span>
          <strong>{{ videoImageSize }} px</strong>
          <input v-model="videoImageSize" type="range" min="640" max="1280" step="32" />
        </label>
      </div>

      <div class="action-row">
        <button type="button" class="primary-button" :disabled="videoRunning || !hasVideoFile" @click="emit('run')">
          {{ videoRunning ? '处理中...' : '开始视频检测' }}
        </button>
      </div>
    </article>

    <article class="panel log-panel">
      <div class="panel-head compact">
        <div>
          <p class="panel-kicker">视频结果</p>
          <h2>处理后视频与后端日志</h2>
        </div>
      </div>

      <div v-if="videoError" class="error-banner">{{ videoError }}</div>

      <div class="summary-grid result-summary-grid video-summary-grid">
        <article v-for="item in videoSummary" :key="item.label" class="summary-card">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </article>
      </div>

      <div v-if="videoStatus" class="progress-card">
        <div class="progress-head">
          <span>视频处理进度</span>
          <strong>{{ videoStatus.progress.toFixed(1) }}%</strong>
        </div>
        <div class="progress-track">
          <div class="progress-fill" :style="{ width: `${videoStatus.progress}%` }"></div>
        </div>
        <p class="progress-note">
          当前状态：{{ videoStatus.state }}，已处理 {{ videoStatus.processedFrames }} /
          {{ videoStatus.totalFrames || '?' }} 帧
        </p>
      </div>

      <div v-if="videoResult" class="result-stack">
        <video class="preview-media" :src="videoResult.outputUrl" controls></video>
        <div class="link-row">
          <a class="inline-link" :href="videoResult.outputUrl" target="_blank">打开结果视频</a>
          <span class="pill-tag">退出码 {{ videoResult.exitCode }}</span>
        </div>
        <div class="event-list compact-list">
          <article v-for="line in videoResult.logs.slice().reverse().slice(0, 8)" :key="line" class="event-item">
            <div class="event-time">log</div>
            <div>
              <strong>{{ line }}</strong>
            </div>
          </article>
        </div>
      </div>
      <div v-else class="empty-state">上传视频后点击“开始视频检测”查看输出。</div>
    </article>
  </section>
</template>
