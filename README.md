# YOLO11 多目标行人检测与跟踪系统

> 本科毕业设计 · 郑州航空工业管理学院 · 人工智能 · 2026

单类行人（person）的**检测 → 跟踪 → 评测 → Web 可视化**完整系统。
检测用 YOLO11m 在两套异构公开数据集上迁移微调，跟踪用 BoxMOT 统一封装
ByteTrack / BoT-SORT / StrongSORT 三种算法并在 MOT17 上用 TrackEval 做定量对比，
最后封装成 FastAPI + Vue 3 的可视化平台，支持 USB 摄像头 / 视频文件 / RTSP 流三路输入。

## 实测结果

### 检测（单类 person，验证集 1,059 张）

| 指标 | 数值 |
|---|---|
| mAP50 | **0.946** |
| 精确率 Precision | 0.917 |
| 召回率 Recall | 0.879 |
| 训练数据 | 5,236 张（两套数据集合并后统一重标） |

### 跟踪（MOT17-02-FRCNN，TrackEval 官方口径）

| 跟踪器 | MOTA ↑ | HOTA ↑ | IDF1 ↑ |
|---|---|---|---|
| **ByteTrack（默认）** | **78.6%** | **69.2%** | **72.8%** |
| BoT-SORT | 76.2% | 67.5% | 70.4% |
| StrongSORT | 74.8% | 66.1% | 68.7% |

> 三者精度接近，但 ByteTrack 不需要 ReID 特征、显存与耗时最低 —— 在边缘端部署场景下这是
> 决定性因素。**选默认值不是"用了最有名的"，而是三者都跑了才定的。**

### 端到端性能（RTX 5070，1280×720，FP16）

| 环节 | 耗时 |
|---|---|
| 检测（YOLO11m, imgsz=960, FP16） | 12 ms |
| 跟踪（ByteTrack） | 1 ms |
| 可视化渲染 | 1 ms |
| **合计** | **≥ 35 FPS**，显存 2.1 GB |

## 系统架构

```
                 ┌──────────────── 表现层 (Vue 3 + Vite + TS) ────────────────┐
                 │  实时监控  │  图片检测  │  视频检测  │  MOT17 评测  │  资产  │
                 └───────────────────────────┬──────────────────────────────┘
                                             │ REST + MJPEG
                 ┌──────────────── 服务层 (FastAPI) ──────────────────────────┐
                 │  13 个 REST 端点 + MJPEG 推流 + 异步任务状态机 + 遥测      │
                 └───────────────────────────┬──────────────────────────────┘
                                             │
                 ┌──────────────── 推理层 (src/) ────────────────────────────┐
                 │  detector.py (YOLO11) → tracker.py (BoxMOT) → visualizer  │
                 │  pipeline.py 编排：帧循环 / FPS 滑窗 / 轨迹 / 人数统计     │
                 └──────────────────────────────────────────────────────────┘
```

后端 13 个端点按职责分四组：

| 组 | 端点 |
|---|---|
| 健康 | `/api/health` |
| 推理 | `/api/image/detect`、`/api/video/detect`、`/api/video/detect/start`、`/api/video/detect/status/{job_id}` |
| MOT17 | `/api/mot17/sequences`、`/api/mot17/run` |
| 运行时 | `/api/runtime/start`、`/api/runtime/stop`、`/api/runtime/status`、`/api/runtime/telemetry`、`/api/runtime/logs`、`/api/runtime/stream`（MJPEG） |

长视频检测不是同步阻塞，而是 `start` 拿 job_id → 轮询 `status` → 完成取产物，
前端不会假死。实时监控走 MJPEG 而不是 WebSocket，是因为后者要在浏览器里解码，
现场演示的机器不一定有硬件解码。

## 关键设计决策

**1. 两套异构数据集先统一再训练，不是直接拼。**
数据集 A（YOLO 格式，2,949 train / 738 valid）和 B（VOC 格式，3,687 张）的标注口径、
文件名规则、负样本比例都不同。`tools/voc2yolo.py` 做格式与类别映射，合并后 **5,236 张**
（4,176 train / 1,059 valid），单类 person，并统一重划训练/验证集避免同源泄漏。

**2. 冻结前 10 层 Backbone 再微调。**
5,236 张对 YOLO11m 这种规模是不够从零训的：全参微调在 20 epoch 左右就开始过拟合
（valid loss 反弹）。冻结前 10 层后在同一份数据上 mAP50 提升约 1.5 个点，训练时间也减半。
数据增强用 Mosaic / MixUp / CopyPaste，配合 FP16 训练。

**3. 三种跟踪器统一封装 + 定量对比，而不是只用一种。**
`src/tracker.py` 用 BoxMOT 统一接口切换算法，`tools/run_mot17.py` 批量跑，
`tools/eval_mot17.py` 调 TrackEval 出 MOTA / HOTA / IDF1。
三种算法在同一份检测结果上对比，才能回答"为什么选 ByteTrack"。

**4. 推理层与服务层解耦。**
`src/` 不依赖 FastAPI，命令行 `main.py` 和 Web 后端共用同一套 pipeline。
好处：算法改动不需要动 Web，评测脚本也能复用同一份推理代码 —— 避免"论文里一套、
演示时另一套"的经典问题。

## 目录结构

```
├── main.py                  命令行入口（摄像头 / 视频 / RTSP）
├── configs/pipeline_config.yaml   全局配置（检测 / 跟踪 / 视频源 / 可视化 / 训练）
├── src/
│   ├── detector.py          YOLO11 封装（FP16 / 类别过滤 / 批推理）
│   ├── tracker.py           BoxMOT 封装（bytetrack / botsort / strongsort）
│   ├── visualizer.py        轨迹尾迹 / ID / FPS / 人数统计渲染
│   └── pipeline.py          帧循环编排 + 遥测指标
├── trackers/*.yaml          三种跟踪器的参数
├── tools/
│   ├── train.py             微调训练（冻结前 N 层）
│   ├── voc2yolo.py          VOC → YOLO 格式转换与合并
│   ├── run_mot17.py         MOT17 批量推理，输出 MOTChallenge 格式
│   └── eval_mot17.py        调 TrackEval 算 MOTA / HOTA / IDF1
├── backend/app.py           FastAPI 服务（13 端点 + MJPEG + 任务状态机）
├── backend/static/          前端构建产物（已提交，开箱即用）
├── frontend/                Vue 3 + Vite + TypeScript 源码
└── docs/使用说明书.docx      操作手册
```

## 快速开始

```bash
pip install -r requirements.txt

# 1) 命令行跑摄像头
python main.py
python main.py --source video --path data/test.mp4 --tracker botsort

# 2) Web 平台
uvicorn backend.app:app --host 0.0.0.0 --port 8000
# 浏览器打开 http://localhost:8000

# 3) 训练（需先按 tools/voc2yolo.py 准备好合并数据集）
python tools/train.py

# 4) MOT17 评测
python tools/run_mot17.py --seq MOT17-02-FRCNN --tracker bytetrack
python tools/eval_mot17.py --tracker-name yolo_bytetrack
```

## 权重与数据集

仓库**不含**模型权重与数据集（体积 + 许可证原因）：

- 权重：需自行训练，或放 `models/yolo11m_person.pt`（单类微调后权重）
- 数据集：COCO person 子集 + VOC person 子集，用 `tools/voc2yolo.py` 合并
- MOT17：`tools/eval_mot17.py` 默认读 `MOT17/images`
- TrackEval：`git clone https://github.com/JonathonLuiten/TrackEval libs/TrackEval`，
  或 `pip install git+https://github.com/JonathonLuiten/TrackEval`

## 已知限制

- 只做单类 person；换类别需重标并改 `configs/pipeline_config.yaml` 的 `classes`
- 遮挡超过 30 帧的 ID 会丢（ByteTrack 靠运动先验，没有外观特征）
- MOT17 只评了 `MOT17-02-FRCNN` 一个序列（算力原因），样本量偏小；
  论文中的结论是在该序列上的，不宜外推到全测试集
- Web 端的 MOT17 任务是串行执行的，没有做队列

## 许可

代码 MIT。第三方组件：Ultralytics YOLO（AGPL-3.0）、BoxMOT（MIT）、TrackEval（MIT）。
