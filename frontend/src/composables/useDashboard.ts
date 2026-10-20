import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import {
    assetCards,
    flowSteps,
    scenarioPresets,
    sourceOptions,
    trackerOptions,
    viewTabs,
} from '../constants/dashboard'
import type {
    EventItem,
    ImageResult,
    MOT17Result,
    MOT17Sequence,
    RuntimeLog,
    RuntimeState,
    RuntimeStatus,
    SourceMode,
    SummaryItem,
    TrackerMode,
    VideoJobStart,
    VideoJobStatus,
    VideoResult,
    ViewMode,
} from '../types/dashboard'

export function useDashboard() {
  const activeView = ref<ViewMode>('monitor')
  const activePresetId = ref(scenarioPresets[0].id)
  const source = ref<SourceMode>('camera')
  const tracker = ref<TrackerMode>('bytetrack')
  const confidence = ref(0.35)
  const imageSize = ref(960)
  const saveVideo = ref(true)
  const showWindow = ref(true)
  const fps = ref(0)
  const peopleCount = ref(0)
  const latency = ref(0)
  const trackStability = ref(0)
  const coverage = ref(0)
  const samplePath = ref('data/test.mp4')
  const rtspUrl = ref('rtsp://demo-camera/live')
  const backendStatus = ref<RuntimeStatus | null>(null)
  const runtimeLogs = ref<RuntimeLog[]>([])
  const uiEvents = ref<EventItem[]>([])
  const isRequesting = ref(false)
  const apiError = ref('')

  const mot17Sequences = ref<MOT17Sequence[]>([])
  const mot17SequencePath = ref('')
  const mot17Tracker = ref<TrackerMode>('bytetrack')
  const mot17Confidence = ref(0.35)
  const mot17ImageSize = ref(960)
  const mot17Running = ref(false)
  const mot17Error = ref('')
  const mot17Result = ref<MOT17Result | null>(null)

  const imageFile = ref<File | null>(null)
  const imageFileName = ref('')
  const imageLocalPreview = ref('')
  const imageRunning = ref(false)
  const imageError = ref('')
  const imageResult = ref<ImageResult | null>(null)

  const videoFile = ref<File | null>(null)
  const videoFileName = ref('')
  const videoTracker = ref<TrackerMode>('bytetrack')
  const videoConfidence = ref(0.35)
  const videoImageSize = ref(960)
  const videoRunning = ref(false)
  const videoError = ref('')
  const videoResult = ref<VideoResult | null>(null)
  const videoJobId = ref('')
  const videoStatus = ref<VideoJobStatus | null>(null)

  let pollTimer: ReturnType<typeof setInterval> | null = null

  const runtimeState = computed<RuntimeState>(() => {
    const state = backendStatus.value?.state ?? 'idle'
    if (state === 'running') return 'running'
    if (state === 'starting' || state === 'stopping') return 'warming'
    if (state === 'error') return 'error'
    return 'idle'
  })

  const runtimeLabel = computed(() => {
    if (runtimeState.value === 'running') return '运行中'
    if (runtimeState.value === 'warming') return '处理中'
    if (runtimeState.value === 'error') return '异常退出'
    return '未启动'
  })

  const sourceLabel = computed(
    () => sourceOptions.find((item) => item.key === source.value)?.label ?? source.value,
  )

  const trackerLabel = computed(
    () => trackerOptions.find((item) => item.key === tracker.value)?.label ?? tracker.value,
  )

  const currentPreset = computed(
    () => scenarioPresets.find((item) => item.id === activePresetId.value) ?? scenarioPresets[0],
  )

  const currentTab = computed(
    () => viewTabs.find((item) => item.key === activeView.value) ?? viewTabs[0],
  )

  const commandPreview = computed(() => {
    const parts = ['python', 'main.py', '--source', source.value, '--tracker', tracker.value]

    if (source.value === 'video') {
      parts.push('--path', samplePath.value)
    }
    if (source.value === 'rtsp') {
      parts.push('--config', 'configs/pipeline_config.yaml')
    }
    if (Math.abs(confidence.value - 0.35) > 0.001) {
      parts.push('--conf', confidence.value.toFixed(2))
    }
    if (imageSize.value !== 640) {
      parts.push('--imgsz', String(imageSize.value))
    }
    if (saveVideo.value) {
      parts.push('--save')
    }
    if (!showWindow.value) {
      parts.push('--no-show')
    }

    return parts.join(' ')
  })

  const commandDisplay = computed(() => backendStatus.value?.command ?? commandPreview.value)

  const backendHint = computed(() => {
    if (backendStatus.value?.pid) {
      return `后端进程 PID ${backendStatus.value.pid}`
    }
    if (backendStatus.value?.startedAt) {
      return `最近启动时间 ${formatClock(backendStatus.value.startedAt)}`
    }
    return '后端尚未启动推理任务'
  })

  const statusDetail = computed(() => {
    if (backendStatus.value?.lastError) {
      return backendStatus.value.lastError
    }
    if (backendStatus.value?.configPath) {
      return `运行配置：${backendStatus.value.configPath}`
    }
    return '点击“启动体验”后会调用 FastAPI 接口并托管 main.py 子进程。'
  })

  const mot17Summary = computed<SummaryItem[]>(() => {
    if (!mot17Result.value) {
      return [
        { label: '序列', value: '未运行' },
        { label: '总帧数', value: '--' },
        { label: '唯一轨迹', value: '--' },
        { label: '平均人数', value: '--' },
      ]
    }

    return [
      { label: '序列', value: mot17Result.value.sequenceName },
      { label: '总帧数', value: String(mot17Result.value.totalFrames) },
      { label: '唯一轨迹', value: String(mot17Result.value.uniqueTracks) },
      { label: '平均人数', value: `${mot17Result.value.avgTracksPerFrame.toFixed(2)} / 帧` },
      { label: '序列时长', value: `${mot17Result.value.durationSeconds.toFixed(2)} s` },
    ]
  })

  const imageSummary = computed<SummaryItem[]>(() => {
    if (!imageResult.value) {
      return [
        { label: '检测人数', value: '0' },
        { label: '最高置信度', value: '--' },
        { label: '平均置信度', value: '--' },
        { label: '平均框面积', value: '--' },
      ]
    }

    const detections = imageResult.value.detections
    const confidences = detections.map((item) => item.confidence)
    const areas = detections.map((item) => {
      const [x1, y1, x2, y2] = item.box
      return Math.max(0, x2 - x1) * Math.max(0, y2 - y1)
    })
    const averageConfidence = confidences.length
      ? confidences.reduce((sum, value) => sum + value, 0) / confidences.length
      : 0
    const averageArea = areas.length ? areas.reduce((sum, value) => sum + value, 0) / areas.length : 0
    const maxConfidence = confidences.length ? Math.max(...confidences) : 0

    return [
      { label: '检测人数', value: String(imageResult.value.count) },
      { label: '最高置信度', value: maxConfidence ? maxConfidence.toFixed(2) : '--' },
      { label: '平均置信度', value: averageConfidence ? averageConfidence.toFixed(2) : '--' },
      { label: '平均框面积', value: averageArea ? `${Math.round(averageArea)} px²` : '--' },
    ]
  })

  const videoSummary = computed<SummaryItem[]>(() => {
    if (!videoStatus.value) {
      return [
        { label: '处理进度', value: '0%' },
        { label: '已处理帧', value: '0 / 0' },
        { label: '平均人数', value: '--' },
        { label: '峰值人数', value: '--' },
      ]
    }

    return [
      { label: '处理进度', value: `${videoStatus.value.progress.toFixed(1)}%` },
      {
        label: '已处理帧',
        value: `${videoStatus.value.processedFrames} / ${videoStatus.value.totalFrames || '?'}`,
      },
      { label: '平均人数', value: `${videoStatus.value.averageCount.toFixed(2)} / 帧` },
      { label: '峰值人数', value: String(videoStatus.value.maxCount) },
      { label: '当前速度', value: `${videoStatus.value.currentFps.toFixed(2)} FPS` },
      { label: '任务状态', value: videoStatus.value.state },
    ]
  })

  const eventLog = computed<EventItem[]>(() => {
    if (runtimeLogs.value.length > 0) {
      return [...runtimeLogs.value]
        .reverse()
        .slice(0, 6)
        .map((item) => ({
          time: formatClock(item.timestamp),
          level: item.level,
          title: item.message,
          detail: item.level === 'error' ? '后端错误日志' : '后端运行日志',
        }))
    }

    return uiEvents.value
  })

  const monitorHighlights = computed<SummaryItem[]>(() => [
    { label: '当前视频源', value: sourceLabel.value },
    { label: '跟踪器', value: trackerLabel.value },
    { label: '置信度', value: confidence.value.toFixed(2) },
    { label: '输入尺寸', value: `${imageSize.value}px` },
  ])

  function stampTime() {
    return new Date().toLocaleTimeString('zh-CN', { hour12: false })
  }

  function formatClock(value: string) {
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) {
      return value
    }
    return date.toLocaleTimeString('zh-CN', { hour12: false })
  }

  function pushUiEvent(level: EventItem['level'], title: string, detail: string) {
    uiEvents.value = [{ time: stampTime(), level, title, detail }, ...uiEvents.value].slice(0, 6)
  }

  function applyPresetById(presetId: string) {
    const preset = scenarioPresets.find((item) => item.id === presetId)
    if (!preset) {
      return
    }

    activePresetId.value = preset.id
    source.value = preset.source
    tracker.value = preset.tracker
    confidence.value = preset.conf
    imageSize.value = preset.imgsz
    saveVideo.value = preset.source !== 'camera'
    showWindow.value = preset.source !== 'rtsp'
    pushUiEvent('info', `切换预设：${preset.title}`, preset.summary)
  }

  async function refreshTelemetry() {
    if (runtimeState.value !== 'running') {
      fps.value = 0
      peopleCount.value = 0
      latency.value = 0
      trackStability.value = 0
      coverage.value = 0
      return
    }
    try {
      const data = await requestJson<{
        fps: number
        people_count: number
        latency_ms: number
        track_stability: number
        coverage: number
      }>('/api/runtime/telemetry')
      fps.value = data.fps
      peopleCount.value = data.people_count
      latency.value = Math.round(data.latency_ms)
      trackStability.value = data.track_stability
      coverage.value = data.coverage
    } catch {
      // telemetry 读取失败不影响主流程
    }
  }

  async function requestJson<T>(url: string, init?: RequestInit) {
    const headers = new Headers(init?.headers ?? {})
    const isFormData = init?.body instanceof FormData
    if (!isFormData && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json')
    }

    const response = await fetch(url, {
      ...init,
      headers,
    })

    if (!response.ok) {
      let detail = `请求失败：${response.status}`
      try {
        const payload = await response.json()
        if (payload?.detail) {
          detail = String(payload.detail)
        }
      } catch {
        detail = response.statusText || detail
      }
      throw new Error(detail)
    }

    return (await response.json()) as T
  }

  async function refreshRuntime() {
    try {
      const [status, logs] = await Promise.all([
        requestJson<RuntimeStatus>('/api/runtime/status'),
        requestJson<{ items: RuntimeLog[] }>('/api/runtime/logs?limit=50'),
      ])

      backendStatus.value = status
      runtimeLogs.value = logs.items
      apiError.value = ''
      await refreshTelemetry()
    } catch (error) {
      apiError.value = error instanceof Error ? error.message : '无法连接后端接口。'
    }
  }

  async function fetchMot17Sequences() {
    try {
      const payload = await requestJson<{ items: MOT17Sequence[] }>('/api/mot17/sequences')
      mot17Sequences.value = payload.items
      if (!mot17SequencePath.value && payload.items.length > 0) {
        mot17SequencePath.value = payload.items[0].path
      }
    } catch (error) {
      mot17Error.value = error instanceof Error ? error.message : '无法加载 MOT17 序列列表。'
    }
  }

  async function startRuntime() {
    if (isRequesting.value) {
      return
    }

    isRequesting.value = true
    apiError.value = ''

    try {
      await requestJson<RuntimeStatus>('/api/runtime/start', {
        method: 'POST',
        body: JSON.stringify({
          source: source.value,
          tracker: tracker.value,
          confidence: Number(confidence.value.toFixed(2)),
          imageSize: imageSize.value,
          saveVideo: saveVideo.value,
          showWindow: showWindow.value,
          samplePath: samplePath.value,
          rtspUrl: rtspUrl.value,
        }),
      })
      await refreshRuntime()
    } catch (error) {
      apiError.value = error instanceof Error ? error.message : '启动失败。'
      pushUiEvent('error', '启动体验失败', apiError.value)
    } finally {
      isRequesting.value = false
    }
  }

  async function stopRuntime() {
    if (isRequesting.value) {
      return
    }

    isRequesting.value = true
    apiError.value = ''

    try {
      await requestJson<RuntimeStatus>('/api/runtime/stop', {
        method: 'POST',
      })
      await refreshRuntime()
    } catch (error) {
      apiError.value = error instanceof Error ? error.message : '停止失败。'
      pushUiEvent('error', '停止体验失败', apiError.value)
    } finally {
      isRequesting.value = false
    }
  }

  async function runMot17Test() {
    if (mot17Running.value || !mot17SequencePath.value) {
      return
    }

    mot17Running.value = true
    mot17Error.value = ''

    try {
      mot17Result.value = await requestJson<MOT17Result>('/api/mot17/run', {
        method: 'POST',
        body: JSON.stringify({
          sequencePath: mot17SequencePath.value,
          tracker: mot17Tracker.value,
          confidence: Number(mot17Confidence.value.toFixed(2)),
          imageSize: mot17ImageSize.value,
        }),
      })
    } catch (error) {
      mot17Error.value = error instanceof Error ? error.message : 'MOT17 测试失败。'
    } finally {
      mot17Running.value = false
    }
  }

  function onImageFileChange(event: Event) {
    const target = event.target as HTMLInputElement
    const file = target.files?.[0] ?? null
    imageFile.value = file
    imageFileName.value = file?.name ?? ''
    imageError.value = ''
    imageResult.value = null

    if (imageLocalPreview.value) {
      URL.revokeObjectURL(imageLocalPreview.value)
      imageLocalPreview.value = ''
    }

    if (file) {
      imageLocalPreview.value = URL.createObjectURL(file)
    }
  }

  function onVideoFileChange(event: Event) {
    const target = event.target as HTMLInputElement
    const file = target.files?.[0] ?? null
    videoFile.value = file
    videoFileName.value = file?.name ?? ''
    videoError.value = ''
    videoResult.value = null
  }

  async function runImageDetect() {
    if (!imageFile.value || imageRunning.value) {
      return
    }

    imageRunning.value = true
    imageError.value = ''

    try {
      const form = new FormData()
      form.append('file', imageFile.value)
      form.append('confidence', String(Number(confidence.value.toFixed(2))))
      form.append('imageSize', String(imageSize.value))
      imageResult.value = await requestJson<ImageResult>('/api/image/detect', {
        method: 'POST',
        body: form,
      })
    } catch (error) {
      imageError.value = error instanceof Error ? error.message : '图片检测失败。'
    } finally {
      imageRunning.value = false
    }
  }

  async function runVideoDetect() {
    if (!videoFile.value || videoRunning.value) {
      return
    }

    videoRunning.value = true
    videoError.value = ''
    videoResult.value = null
    videoStatus.value = null
    videoJobId.value = ''

    try {
      const form = new FormData()
      form.append('file', videoFile.value)
      form.append('tracker', videoTracker.value)
      form.append('confidence', String(Number(videoConfidence.value.toFixed(2))))
      form.append('imageSize', String(videoImageSize.value))
      const payload = await requestJson<VideoJobStart>('/api/video/detect/start', {
        method: 'POST',
        body: form,
      })
      videoJobId.value = payload.jobId
      await refreshVideoStatus()
    } catch (error) {
      videoError.value = error instanceof Error ? error.message : '视频检测失败。'
      videoRunning.value = false
    }
  }

  async function refreshVideoStatus() {
    if (!videoJobId.value) {
      return
    }

    try {
      const status = await requestJson<VideoJobStatus>(`/api/video/detect/status/${videoJobId.value}`)
      videoStatus.value = status

      if (status.state === 'completed') {
        videoRunning.value = false
        if (status.outputUrl) {
          videoResult.value = {
            filename: status.filename,
            outputUrl: status.outputUrl,
            logs: status.logs,
            exitCode: 0,
          }
        }
        return
      }

      if (status.state === 'error') {
        videoRunning.value = false
        videoError.value = status.error || '视频检测失败。'
      }
    } catch (error) {
      videoRunning.value = false
      videoError.value = error instanceof Error ? error.message : '无法获取视频处理进度。'
    }
  }

  onMounted(() => {
    applyPresetById(scenarioPresets[0].id)
    void refreshRuntime()
    void fetchMot17Sequences()
    pollTimer = setInterval(() => {
      void refreshRuntime()
      if (videoJobId.value && videoRunning.value) {
        void refreshVideoStatus()
      }
    }, 2000)
  })

  onBeforeUnmount(() => {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
    if (imageLocalPreview.value) {
      URL.revokeObjectURL(imageLocalPreview.value)
    }
  })

  return {
    activeView,
    activePresetId,
    source,
    tracker,
    confidence,
    imageSize,
    saveVideo,
    showWindow,
    fps,
    peopleCount,
    latency,
    trackStability,
    coverage,
    samplePath,
    rtspUrl,
    backendStatus,
    isRequesting,
    apiError,
    mot17Sequences,
    mot17SequencePath,
    mot17Tracker,
    mot17Confidence,
    mot17ImageSize,
    mot17Running,
    mot17Error,
    mot17Result,
    imageFile,
    imageFileName,
    imageLocalPreview,
    imageRunning,
    imageError,
    imageResult,
    videoFile,
    videoFileName,
    videoTracker,
    videoConfidence,
    videoImageSize,
    videoRunning,
    videoError,
    videoResult,
    videoStatus,
    runtimeState,
    runtimeLabel,
    sourceLabel,
    trackerLabel,
    currentPreset,
    currentTab,
    commandDisplay,
    backendHint,
    statusDetail,
    mot17Summary,
    imageSummary,
    videoSummary,
    eventLog,
    monitorHighlights,
    startRuntime,
    stopRuntime,
    runMot17Test,
    onImageFileChange,
    onVideoFileChange,
    runImageDetect,
    runVideoDetect,
    applyPresetById,
    viewTabs,
    sourceOptions,
    trackerOptions,
    scenarioPresets,
    assetCards,
    flowSteps,
  }
}
