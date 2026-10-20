import type {
  AssetCard,
  ScenarioPreset,
  SourceOption,
  TrackerOption,
  ViewTab,
} from '../types/dashboard'

export const viewTabs: ViewTab[] = [
  { key: 'monitor', label: '实时体验', hint: '摄像头 / 视频流实时链路' },
  { key: 'mot17', label: 'MOT17 测试', hint: '点选序列直接跑跟踪' },
  { key: 'image', label: '图片检测', hint: '上传单张图片做人物检测' },
  { key: 'video', label: '视频检测', hint: '上传视频并输出跟踪结果' },
  { key: 'assets', label: '数据资产', hint: '项目数据、模型与流程说明' },
]

export const sourceOptions: SourceOption[] = [
  { key: 'camera', label: 'USB 摄像头', hint: '现场实时演示' },
  { key: 'video', label: '本地视频', hint: '导入 mp4 做离线回放' },
  { key: 'rtsp', label: 'RTSP 流', hint: '接入监控流或网络摄像头' },
]

export const trackerOptions: TrackerOption[] = [
  { key: 'bytetrack', label: 'ByteTrack', note: '默认稳妥，适合实时体验' },
  { key: 'botsort', label: 'BoT-SORT', note: '遮挡场景更稳，但开销更高' },
  { key: 'strongsort', label: 'StrongSORT', note: '偏向 ReID 增强场景' },
]

export const scenarioPresets: ScenarioPreset[] = [
  {
    id: 'campus-gate',
    title: '校门口高峰时段',
    summary: '多人同向移动，适合看 ID 连续性和人数统计。',
    source: 'camera',
    tracker: 'bytetrack',
    conf: 0.35,
    imgsz: 960,
  },
  {
    id: 'mall-video',
    title: '商场离线视频复盘',
    summary: '需要保存输出视频，适合展示轨迹线与 FPS。',
    source: 'video',
    tracker: 'botsort',
    conf: 0.28,
    imgsz: 1280,
  },
  {
    id: 'night-rtsp',
    title: '夜间远距 RTSP',
    summary: '远距离小目标场景，优先提高输入尺寸。',
    source: 'rtsp',
    tracker: 'strongsort',
    conf: 0.22,
    imgsz: 1280,
  },
]

export const assetCards: AssetCard[] = [
  { label: '训练集规模', value: '7,373', detail: '合并后 train + valid 总图像数' },
  { label: '默认检测权重', value: 'YOLO11m', detail: '项目已内置 models/yolo11m_person.pt' },
  { label: '跟踪方案', value: '3 套', detail: 'ByteTrack / BoT-SORT / StrongSORT' },
  { label: '测试入口', value: '4 类', detail: '实时、MOT17、图片、视频都能直接点测' },
]

export const flowSteps = [
  '实时链路通过 FastAPI 托管 main.py 子进程',
  'MOT17 页面直接调用单序列测试接口',
  '图片页面上传后返回标注图与框列表',
  '视频页面上传后输出处理后的视频文件',
]
