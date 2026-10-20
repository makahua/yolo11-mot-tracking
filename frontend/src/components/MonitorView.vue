<script setup lang="ts">
import type { PropType } from 'vue'
import { computed, onMounted, onUnmounted, ref } from 'vue'

import type {
    EventItem,
    RuntimeState,
    ScenarioPreset,
    SourceMode,
    SourceOption,
    SummaryItem,
    TrackerMode,
    TrackerOption,
} from '../types/dashboard'

const props = defineProps({
  sourceOptions: {
    type: Array as PropType<SourceOption[]>,
    required: true,
  },
  trackerOptions: {
    type: Array as PropType<TrackerOption[]>,
    required: true,
  },
  scenarioPresets: {
    type: Array as PropType<ScenarioPreset[]>,
    required: true,
  },
  monitorHighlights: {
    type: Array as PropType<SummaryItem[]>,
    required: true,
  },
  eventLog: {
    type: Array as PropType<EventItem[]>,
    required: true,
  },
  currentPresetTitle: {
    type: String,
    required: true,
  },
  currentPresetSummary: {
    type: String,
    required: true,
  },
  commandDisplay: {
    type: String,
    required: true,
  },
  runtimeLabel: {
    type: String,
    required: true,
  },
  runtimeState: {
    type: String as PropType<RuntimeState>,
    required: true,
  },
  sourceLabel: {
    type: String,
    required: true,
  },
  trackerLabel: {
    type: String,
    required: true,
  },
  apiError: {
    type: String,
    required: true,
  },
  statusDetail: {
    type: String,
    required: true,
  },
  isRequesting: {
    type: Boolean,
    required: true,
  },
  peopleCount: {
    type: Number,
    required: true,
  },
  fps: {
    type: Number,
    required: true,
  },
  latency: {
    type: Number,
    required: true,
  },
  trackStability: {
    type: Number,
    required: true,
  },
  coverage: {
    type: Number,
    required: true,
  },
})

const activePresetId = defineModel<string>('activePresetId', { required: true })
const source = defineModel<SourceMode>('source', { required: true })
const tracker = defineModel<TrackerMode>('tracker', { required: true })
const confidence = defineModel<number>('confidence', { required: true })
const imageSize = defineModel<number>('imageSize', { required: true })
const saveVideo = defineModel<boolean>('saveVideo', { required: true })
const showWindow = defineModel<boolean>('showWindow', { required: true })
const samplePath = defineModel<string>('samplePath', { required: true })
const rtspUrl = defineModel<string>('rtspUrl', { required: true })

const emit = defineEmits<{
  start: []
  stop: []
}>()

const isBusy = computed(
  () => props.runtimeState === 'running' || props.runtimeState === 'warming',
)

// 流显示相关
const streamUrl = ref('/api/runtime/stream')
const refreshKey = ref(0)
let frameRefreshInterval: number | null = null

onMounted(() => {
  // 每 100ms 刷新一次流（帮助某些浏览器更新 MJPEG）
  frameRefreshInterval = window.setInterval(() => {
    refreshKey.value += 1
  }, 100)
})

onUnmounted(() => {
  if (frameRefreshInterval !== null) {
    clearInterval(frameRefreshInterval)
  }
})
</script>

<template>
  <div class="monitor-shell">
    <section class="workspace-grid">
      <article class="panel monitor-stage">
        <div class="panel-head">
          <div>
            <p class="panel-kicker">体验屏幕</p>
            <h2>实时监控视图</h2>
          </div>
          <span class="panel-tag">{{ sourceLabel }}</span>
        </div>

        <div class="screen-card">
          <div class="screen-header">
            <span>YOLOv11 / {{ trackerLabel }}</span>
            <span>{{ runtimeLabel }}</span>
          </div>

          <div class="screen-body">
            <!-- 实时视频流 MJPEG -->
            <img 
              v-if="isBusy" 
              :key="refreshKey"
              :src="streamUrl" 
              alt="实时监控画面"
              class="stream-image"
            />
            <!-- 无运行时显示占位符 -->
            <div v-else class="stream-placeholder">
              <div class="scanline"></div>
              <div class="screen-grid"></div>
              <div class="stage-metrics idle">
                <strong>--</strong>
                <span>等待启动</span>
              </div>
            </div>
            
            <!-- 人数统计 -->
            <div class="stage-metrics">
              <strong>{{ peopleCount }}</strong>
              <span>画面人数</span>
            </div>
          </div>

          <div class="screen-footer">
            <div>
              <span>FPS</span>
              <strong>{{ fps }}</strong>
            </div>
            <div>
              <span>延迟</span>
              <strong>{{ latency }} ms</strong>
            </div>
            <div>
              <span>轨迹稳定</span>
              <strong>{{ trackStability }}%</strong>
            </div>
            <div>
              <span>覆盖率</span>
              <strong>{{ coverage }}%</strong>
            </div>
          </div>
        </div>

        <div class="command-block">
          <div>
            <p class="panel-kicker">命令映射</p>
            <h3>前端操作对应到主入口</h3>
          </div>
          <code>{{ commandDisplay }}</code>
        </div>
      </article>

      <aside class="panel side-panel preset-panel">
        <div class="panel-head compact">
          <div>
            <p class="panel-kicker">场景预设</p>
            <h2>一键切换实时体验脚本</h2>
          </div>
        </div>

        <div class="preset-list">
          <button
            v-for="preset in scenarioPresets"
            :key="preset.id"
            type="button"
            class="preset-card"
            :data-active="activePresetId === preset.id"
            @click="activePresetId = preset.id"
          >
            <strong>{{ preset.title }}</strong>
            <span>{{ preset.summary }}</span>
          </button>
        </div>

        <div class="summary-grid side-summary-grid">
          <article v-for="item in monitorHighlights" :key="item.label" class="summary-card">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </article>
        </div>

        <div class="hint-card strong compact-hint">
          <p class="panel-kicker">当前预设</p>
          <h3>{{ currentPresetTitle }}</h3>
          <p>{{ currentPresetSummary }}</p>
        </div>
      </aside>
    </section>

    <section class="detail-grid">
      <article class="panel control-panel">
        <div class="panel-head compact">
          <div>
            <p class="panel-kicker">运行配置</p>
            <h2>调整后即可生成体验命令</h2>
          </div>
        </div>

        <div class="field-group">
          <span class="field-label">视频源类型</span>
          <div class="option-row three-up">
            <button
              v-for="option in sourceOptions"
              :key="option.key"
              type="button"
              class="choice-card"
              :data-active="source === option.key"
              @click="source = option.key"
            >
              <strong>{{ option.label }}</strong>
              <span>{{ option.hint }}</span>
            </button>
          </div>
        </div>

        <div class="field-group">
          <span class="field-label">跟踪算法</span>
          <div class="option-row three-up">
            <button
              v-for="item in trackerOptions"
              :key="item.key"
              type="button"
              class="choice-card"
              :data-active="tracker === item.key"
              @click="tracker = item.key"
            >
              <strong>{{ item.label }}</strong>
              <span>{{ item.note }}</span>
            </button>
          </div>
        </div>

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

        <div v-if="source === 'video'" class="field-group">
          <label class="input-card">
            <span>视频路径</span>
            <input v-model="samplePath" type="text" placeholder="data/test.mp4" />
          </label>
        </div>

        <div v-if="source === 'rtsp'" class="field-group">
          <label class="input-card">
            <span>RTSP 地址</span>
            <input v-model="rtspUrl" type="text" placeholder="rtsp://demo-camera/live" />
          </label>
        </div>

        <div class="switch-row">
          <label class="switch-card">
            <input v-model="saveVideo" type="checkbox" />
            <span>保存输出视频</span>
          </label>
          <label class="switch-card">
            <input v-model="showWindow" type="checkbox" />
            <span>显示可视化窗口</span>
          </label>
        </div>

        <div class="action-row">
          <button type="button" class="primary-button" :disabled="isRequesting || isBusy" @click="emit('start')">
            启动体验
          </button>
          <button
            type="button"
            class="secondary-button"
            :disabled="isRequesting || runtimeState === 'idle'"
            @click="emit('stop')"
          >
            停止体验
          </button>
        </div>
      </article>

      <article class="panel log-panel">
        <div class="panel-head compact">
          <div>
            <p class="panel-kicker">事件流</p>
            <h2>后端运行日志</h2>
          </div>
        </div>

        <div v-if="apiError" class="error-banner">{{ apiError }}</div>

        <div class="hint-card compact-hint">
          <p class="panel-kicker">运行状态</p>
          <p>{{ statusDetail }}</p>
        </div>

        <div class="event-list">
          <article
            v-for="item in eventLog"
            :key="`${item.time}-${item.title}`"
            class="event-item"
            :data-level="item.level"
          >
            <div class="event-time">{{ item.time }}</div>
            <div>
              <strong>{{ item.title }}</strong>
              <p v-if="item.detail">{{ item.detail }}</p>
            </div>
          </article>
        </div>
      </article>
    </section>
  </div>
</template>

<style scoped>
.stream-image {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}

.stream-placeholder {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1a1a1a 0%, #0f0f0f 100%);
}

.stream-placeholder .stage-metrics.idle {
  opacity: 0.5;
}
</style>
