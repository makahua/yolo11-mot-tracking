export type ViewMode = 'monitor' | 'mot17' | 'image' | 'video' | 'assets'
export type SourceMode = 'camera' | 'video' | 'rtsp'
export type TrackerMode = 'bytetrack' | 'botsort' | 'strongsort'
export type RuntimeState = 'idle' | 'warming' | 'running' | 'error'
export type BackendRuntimeState = 'idle' | 'starting' | 'running' | 'stopping' | 'error'

export type ViewTab = {
  key: ViewMode
  label: string
  hint: string
}

export type SourceOption = {
  key: SourceMode
  label: string
  hint: string
}

export type TrackerOption = {
  key: TrackerMode
  label: string
  note: string
}

export type ScenarioPreset = {
  id: string
  title: string
  summary: string
  source: SourceMode
  tracker: TrackerMode
  conf: number
  imgsz: number
}

export type EventItem = {
  time: string
  level: 'info' | 'success' | 'warn' | 'error'
  title: string
  detail: string
}

export type RuntimeStatus = {
  state: BackendRuntimeState
  pid: number | null
  command: string | null
  configPath: string | null
  startedAt: string | null
  exitCode: number | null
  lastError: string | null
}

export type RuntimeLog = {
  timestamp: string
  level: 'info' | 'warn' | 'error' | 'success'
  message: string
}

export type MOT17Sequence = {
  split: string
  name: string
  path: string
}

export type MOT17Result = {
  sequenceName: string
  sequencePath: string
  tracker: string
  videoUrl: string
  motUrl: string
  logs: string[]
  totalFrames: number
  uniqueTracks: number
  avgTracksPerFrame: number
  durationSeconds: number
}

export type DetectionItem = {
  box: number[]
  confidence: number
}

export type ImageResult = {
  filename: string
  imageUrl: string
  count: number
  detections: DetectionItem[]
}

export type VideoResult = {
  filename: string
  outputUrl: string
  logs: string[]
  exitCode: number
}

export type VideoJobStart = {
  jobId: string
  state: 'queued' | 'running' | 'completed' | 'error'
}

export type VideoJobStatus = {
  jobId: string
  filename: string
  state: 'queued' | 'running' | 'completed' | 'error'
  progress: number
  processedFrames: number
  totalFrames: number
  currentFps: number
  averageCount: number
  maxCount: number
  outputUrl: string | null
  logs: string[]
  error: string | null
}

export type SummaryItem = {
  label: string
  value: string
}

export type AssetCard = {
  label: string
  value: string
  detail: string
}

export type OverlayBox = {
  id: number
  top: string
  left: string
  width: string
  height: string
  track: string
}
