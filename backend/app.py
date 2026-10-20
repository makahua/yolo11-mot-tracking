from __future__ import annotations

import configparser
import contextlib
import io
import json
import shutil
import subprocess
import sys
import threading
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
import yaml
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.detector import PersonDetector
from src.pipeline import MOTPipeline
from tools.run_mot17 import (
    DEFAULT_CONFIG,
    build_runtime_cfg,
    load_config,
    run_mot17_sequence,
)

BASE_CONFIG_PATH = ROOT_DIR / "configs" / "pipeline_config.yaml"
RUNTIME_CONFIG_PATH = ROOT_DIR / "configs" / "_runtime_api.yaml"
GENERATED_DIR = ROOT_DIR / "backend" / "generated"
UPLOAD_DIR = GENERATED_DIR / "uploads"
IMAGE_OUTPUT_DIR = GENERATED_DIR / "images"
VIDEO_OUTPUT_DIR = GENERATED_DIR / "videos"
MOT_OUTPUT_DIR = GENERATED_DIR / "mot17"
TEMP_CONFIG_DIR = GENERATED_DIR / "configs"
STREAM_DIR = GENERATED_DIR / "stream"

for directory in (GENERATED_DIR, UPLOAD_DIR, IMAGE_OUTPUT_DIR, VIDEO_OUTPUT_DIR, MOT_OUTPUT_DIR, TEMP_CONFIG_DIR, STREAM_DIR):
    directory.mkdir(parents=True, exist_ok=True)


class FrameBuffer:
    """实时帧缓冲区，用于 MJPEG 流"""
    def __init__(self):
        self._lock = threading.RLock()
        self._current_frame: np.ndarray | None = None
        self._frame_updated = threading.Event()

    def put_frame(self, frame: np.ndarray) -> None:
        """保存新的帧"""
        with self._lock:
            self._current_frame = frame.copy() if isinstance(frame, np.ndarray) else frame
            self._frame_updated.set()

    def get_frame(self) -> np.ndarray | None:
        """获取当前帧"""
        with self._lock:
            return self._current_frame.copy() if self._current_frame is not None else None

    def encode_jpeg(self, quality: int = 80) -> bytes | None:
        """编码当前帧为 JPEG"""
        frame = self.get_frame()
        if frame is None:
            return None
        ok, jpeg_bytes = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return jpeg_bytes.tobytes() if ok else None


def frame_generator(frame_buffer: FrameBuffer, interval_ms: int = 33):
    """MJPEG 流生成器"""
    while True:
        jpeg_bytes = frame_buffer.encode_jpeg(quality=75)
        if jpeg_bytes is None:
            frame_buffer._frame_updated.wait(timeout=0.1)
            continue

        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n'
            b'Content-Length: ' + str(len(jpeg_bytes)).encode() + b'\r\n'
            b'\r\n' + jpeg_bytes + b'\r\n'
        )
        frame_buffer._frame_updated.clear()


class TelemetryStore:
    """接收来自 pipeline stdout 的遥测数据，存入内存"""

    _DEFAULTS = {
        "fps": 0.0,
        "people_count": 0,
        "latency_ms": 0.0,
        "track_stability": 0,
        "coverage": 0.0,
    }

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict = dict(self._DEFAULTS)

    def update(self, payload: dict) -> None:
        """由日志线程调用，无需持锁（GIL 保护）"""
        with self._lock:
            self._data = {**self._DEFAULTS, **payload}

    def reset(self) -> None:
        with self._lock:
            self._data = dict(self._DEFAULTS)

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._data)



class RuntimeStartRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source: Literal["camera", "video", "rtsp"] = "camera"
    tracker: Literal["bytetrack", "botsort", "strongsort"] = "bytetrack"
    confidence: float = Field(default=0.35, ge=0.05, le=0.99)
    image_size: int = Field(default=640, ge=320, le=2048, alias="imageSize")
    save_video: bool = Field(default=False, alias="saveVideo")
    show_window: bool = Field(default=True, alias="showWindow")
    sample_path: str | None = Field(default=None, alias="samplePath")
    rtsp_url: str | None = Field(default=None, alias="rtspUrl")


class MOT17RunRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    sequence_path: str = Field(alias="sequencePath")
    tracker: Literal["bytetrack", "botsort", "strongsort"] = "bytetrack"
    confidence: float = Field(default=0.35, ge=0.05, le=0.99)
    image_size: int = Field(default=960, ge=320, le=2048, alias="imageSize")


class RuntimeLogEntry(BaseModel):
    timestamp: str
    level: Literal["info", "warn", "error", "success"]
    message: str


class RuntimeStatusResponse(BaseModel):
    state: Literal["idle", "starting", "running", "stopping", "error"]
    pid: int | None
    command: str | None
    config_path: str | None = Field(alias="configPath")
    started_at: str | None = Field(alias="startedAt")
    exit_code: int | None = Field(alias="exitCode")
    last_error: str | None = Field(alias="lastError")


class RuntimeLogResponse(BaseModel):
    items: list[RuntimeLogEntry]


class MOT17SequenceItem(BaseModel):
    split: str
    name: str
    path: str


class MOT17SequenceListResponse(BaseModel):
    items: list[MOT17SequenceItem]


class MOT17RunResponse(BaseModel):
    sequence_name: str = Field(alias="sequenceName")
    sequence_path: str = Field(alias="sequencePath")
    tracker: str
    video_url: str = Field(alias="videoUrl")
    mot_url: str = Field(alias="motUrl")
    logs: list[str]
    total_frames: int = Field(alias="totalFrames")
    unique_tracks: int = Field(alias="uniqueTracks")
    avg_tracks_per_frame: float = Field(alias="avgTracksPerFrame")
    duration_seconds: float = Field(alias="durationSeconds")


class ImageDetectionItem(BaseModel):
    box: list[float]
    confidence: float


class ImageDetectResponse(BaseModel):
    filename: str
    image_url: str = Field(alias="imageUrl")
    count: int
    detections: list[ImageDetectionItem]


class VideoDetectResponse(BaseModel):
    filename: str
    output_url: str = Field(alias="outputUrl")
    logs: list[str]
    exit_code: int = Field(alias="exitCode")


class VideoJobStartResponse(BaseModel):
    job_id: str = Field(alias="jobId")
    state: Literal["queued", "running", "completed", "error"]


class VideoJobStatusResponse(BaseModel):
    job_id: str = Field(alias="jobId")
    filename: str
    state: Literal["queued", "running", "completed", "error"]
    progress: float
    processed_frames: int = Field(alias="processedFrames")
    total_frames: int = Field(alias="totalFrames")
    current_fps: float = Field(alias="currentFps")
    average_count: float = Field(alias="averageCount")
    max_count: int = Field(alias="maxCount")
    output_url: str | None = Field(default=None, alias="outputUrl")
    logs: list[str]
    error: str | None = None


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_base_pipeline_config() -> dict:
    with BASE_CONFIG_PATH.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def apply_pipeline_overrides(
    config: dict,
    *,
    source_type: str,
    tracker: str,
    confidence: float,
    image_size: int,
    save_video: bool,
    show_window: bool,
    video_path: str | None = None,
    rtsp_url: str | None = None,
    output_path: str | None = None,
) -> dict:
    runtime = yaml.safe_load(yaml.safe_dump(config, allow_unicode=True))
    runtime["source"]["type"] = source_type
    runtime["tracker"]["type"] = tracker
    runtime["tracker"]["config_file"] = f"trackers/{tracker}.yaml"
    runtime["detector"]["conf"] = confidence
    runtime["detector"]["imgsz"] = image_size
    runtime["visualizer"]["save_video"] = save_video
    runtime["visualizer"]["show"] = show_window

    if output_path:
        runtime["visualizer"]["output_path"] = output_path

    if source_type == "video":
        if not video_path:
            raise ValueError("视频模式缺少 video_path。")
        runtime["source"]["video_path"] = video_path
        runtime["source"].pop("rtsp_url", None)
    elif source_type == "rtsp":
        if not rtsp_url:
            raise ValueError("RTSP 模式缺少 rtsp_url。")
        runtime["source"]["rtsp_url"] = rtsp_url
        runtime["source"].pop("video_path", None)
    else:
        runtime["source"].pop("video_path", None)
        runtime["source"].pop("rtsp_url", None)

    return runtime


def save_yaml_config(path: Path, config: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(config, file, allow_unicode=True, sort_keys=False)


def save_upload_file(upload: UploadFile, target_dir: Path) -> Path:
    suffix = Path(upload.filename or "").suffix or ".bin"
    stored_path = target_dir / f"{uuid.uuid4().hex}{suffix}"
    with stored_path.open("wb") as output:
        shutil.copyfileobj(upload.file, output)
    return stored_path


def public_url(request: Request, path: Path) -> str:
    relative = path.relative_to(GENERATED_DIR).as_posix()
    return str(request.url_for("generated", path=relative))


def list_mot17_sequences() -> list[MOT17SequenceItem]:
    items: list[MOT17SequenceItem] = []
    images_root = ROOT_DIR / "MOT17"
    for split in ("train", "test"):
        split_dir = images_root / split
        if not split_dir.exists():
            continue
        for sequence_dir in sorted(split_dir.iterdir()):
            if sequence_dir.is_dir() and (sequence_dir / "img1").exists():
                items.append(
                    MOT17SequenceItem(
                        split=split,
                        name=sequence_dir.name,
                        path=str(sequence_dir.relative_to(ROOT_DIR)).replace("\\", "/"),
                    )
                )
    return items


def summarize_mot_file(mot_path: Path, sequence_path: Path) -> tuple[int, int, float, float]:
    total_frames = 0
    unique_tracks: set[int] = set()
    frame_counts: dict[int, int] = {}

    if mot_path.exists():
        with mot_path.open("r", encoding="utf-8") as file:
            for line in file:
                parts = line.strip().split(",")
                if len(parts) < 2:
                    continue
                frame_id = int(float(parts[0]))
                track_id = int(float(parts[1]))
                frame_counts[frame_id] = frame_counts.get(frame_id, 0) + 1
                unique_tracks.add(track_id)

    seqinfo_path = sequence_path / "seqinfo.ini"
    frame_rate = 30
    if seqinfo_path.exists():
        config = configparser.ConfigParser()
        config.read(seqinfo_path, encoding="utf-8")
        frame_rate = config.getint("Sequence", "frameRate", fallback=30)
        total_frames = config.getint("Sequence", "seqLength", fallback=0)

    if total_frames == 0 and frame_counts:
        total_frames = max(frame_counts)

    avg_tracks_per_frame = round(sum(frame_counts.values()) / max(1, len(frame_counts)), 2) if frame_counts else 0.0
    duration_seconds = round(total_frames / frame_rate, 2) if frame_rate > 0 else 0.0
    return total_frames, len(unique_tracks), avg_tracks_per_frame, duration_seconds


class DetectorService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._detector: PersonDetector | None = None
        self._iou = 0.45

    def _ensure_detector(self) -> PersonDetector:
        if self._detector is None:
            base = load_base_pipeline_config()["detector"]
            self._iou = float(base["iou"])
            self._detector = PersonDetector(
                model_path=base["model"],
                conf=float(base["conf"]),
                iou=self._iou,
                imgsz=int(base["imgsz"]),
                device=str(base["device"]),
                half=bool(base.get("half", True)),
                max_det=int(base.get("max_det", 300)),
            )
            self._detector.warmup()
        return self._detector

    def detect_image(self, image_path: Path, confidence: float, image_size: int) -> tuple[Path, list[ImageDetectionItem]]:
        with self._lock:
            detector = self._ensure_detector()
            detector.conf = confidence
            detector.iou = self._iou
            detector.imgsz = image_size

            image = cv2.imread(str(image_path))
            if image is None:
                raise ValueError("上传图片无法读取，请确认文件格式是否正确。")

            detections = detector.detect(image)
            annotated = image.copy()
            items: list[ImageDetectionItem] = []
            for det in detections:
                x1, y1, x2, y2, score, _ = det.tolist()
                cv2.rectangle(annotated, (int(x1), int(y1)), (int(x2), int(y2)), (61, 217, 179), 2)
                cv2.putText(
                    annotated,
                    f"person {score:.2f}",
                    (int(x1), max(20, int(y1) - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (61, 217, 179),
                    2,
                )
                items.append(
                    ImageDetectionItem(
                        box=[round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)],
                        confidence=round(score, 4),
                    )
                )

            output_path = IMAGE_OUTPUT_DIR / f"{image_path.stem}_detected.jpg"
            cv2.imwrite(str(output_path), annotated)
            return output_path, items


class VideoJobManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, dict] = {}

    def start(
        self,
        *,
        filename: str,
        tracker: str,
        confidence: float,
        image_size: int,
        stored_path: Path,
        output_path: Path,
    ) -> VideoJobStartResponse:
        job_id = uuid.uuid4().hex
        with self._lock:
            self._jobs[job_id] = {
                "jobId": job_id,
                "filename": filename,
                "state": "queued",
                "progress": 0.0,
                "processedFrames": 0,
                "totalFrames": 0,
                "currentFps": 0.0,
                "averageCount": 0.0,
                "maxCount": 0,
                "outputUrl": None,
                "outputPath": str(output_path),
                "logs": [f"{now_iso()} 已创建视频检测任务"],
                "error": None,
            }

        thread = threading.Thread(
            target=self._run_job,
            args=(job_id, tracker, confidence, image_size, stored_path, output_path),
            daemon=True,
        )
        thread.start()
        return VideoJobStartResponse(jobId=job_id, state="queued")

    def get_status(self, job_id: str) -> VideoJobStatusResponse:
        with self._lock:
            payload = self._jobs.get(job_id)
            if not payload:
                raise KeyError(job_id)
            return VideoJobStatusResponse(**payload)

    def set_output_url(self, job_id: str, output_url: str) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["outputUrl"] = output_url

    def get_output_path(self, job_id: str) -> Path | None:
        with self._lock:
            if job_id not in self._jobs:
                return None
            raw = self._jobs[job_id].get("outputPath")
            return Path(raw) if raw else None

    def _append_log(self, job_id: str, message: str) -> None:
        with self._lock:
            if job_id not in self._jobs:
                return
            logs = self._jobs[job_id]["logs"]
            logs.append(f"{now_iso()} {message}")
            self._jobs[job_id]["logs"] = logs[-40:]

    def _update(self, job_id: str, **kwargs) -> None:
        with self._lock:
            if job_id not in self._jobs:
                return
            self._jobs[job_id].update(kwargs)

    def _run_job(
        self,
        job_id: str,
        tracker: str,
        confidence: float,
        image_size: int,
        stored_path: Path,
        output_path: Path,
    ) -> None:
        self._update(job_id, state="running")
        self._append_log(job_id, "开始解析视频并准备推理")

        try:
            pipeline = None
            capture = None
            writer = None
            runtime = apply_pipeline_overrides(
                load_base_pipeline_config(),
                source_type="video",
                tracker=tracker,
                confidence=confidence,
                image_size=image_size,
                save_video=True,
                show_window=False,
                video_path=str(stored_path),
                output_path=str(output_path),
            )
            temp_config = TEMP_CONFIG_DIR / f"video_job_{job_id}.yaml"
            save_yaml_config(temp_config, runtime)

            pipeline = MOTPipeline(str(temp_config))
            capture = cv2.VideoCapture(str(stored_path))
            if not capture.isOpened():
                raise RuntimeError("无法打开上传的视频文件。")

            total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            fps_value = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
            self._update(job_id, totalFrames=total_frames)

            processed_frames = 0
            count_sum = 0
            max_count = 0

            pipeline.detector.warmup()
            self._append_log(job_id, "模型预热完成，开始逐帧处理")

            while True:
                ok, frame = capture.read()
                if not ok:
                    break

                vis, tracks = pipeline.process_frame(frame)
                current_count = int(len(tracks) if tracks is not None else 0)
                processed_frames += 1
                count_sum += current_count
                max_count = max(max_count, current_count)

                if writer is None:
                    height, width = vis.shape[:2]
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    for codec, _ext in [("avc1", None), ("mp4v", None)]:
                        w = cv2.VideoWriter(
                            str(output_path),
                            cv2.VideoWriter_fourcc(*codec),
                            fps_value if fps_value > 0 else 30.0,
                            (width, height),
                        )
                        if w.isOpened():
                            writer = w
                            break
                        w.release()
                    if writer is None:
                        raise RuntimeError("无法创建视频写入器，已尝试 avc1/VP90/mp4v")
                writer.write(vis)

                current_fps = round(1.0 / (sum(pipeline._fps_buf) / len(pipeline._fps_buf)), 2) if pipeline._fps_buf else 0.0
                progress = round(processed_frames / total_frames * 100, 2) if total_frames > 0 else 0.0
                average_count = round(count_sum / processed_frames, 2)
                self._update(
                    job_id,
                    progress=progress,
                    processedFrames=processed_frames,
                    currentFps=current_fps,
                    averageCount=average_count,
                    maxCount=max_count,
                )

                if processed_frames == 1 or processed_frames % 30 == 0:
                    self._append_log(job_id, f"已处理 {processed_frames}/{max(total_frames, processed_frames)} 帧")

            final_progress = 100.0 if processed_frames > 0 else 0.0
            self._update(job_id, state="completed", progress=final_progress)
            self._append_log(job_id, "视频检测完成")
        except Exception as exc:
            self._update(job_id, state="error", error=str(exc))
            self._append_log(job_id, f"视频检测失败：{exc}")
        finally:
            if writer is not None:
                writer.release()
            if capture is not None:
                capture.release()
            if pipeline is not None and pipeline.writer:
                pipeline.writer.release()
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass


class RuntimeManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._logs: deque[RuntimeLogEntry] = deque(maxlen=200)
        self._process: subprocess.Popen[str] | None = None
        self._run_token = 0
        self._stop_requested = False
        self._state: Literal["idle", "starting", "running", "stopping", "error"] = "idle"
        self._pid: int | None = None
        self._command: str | None = None
        self._config_path: str | None = None
        self._started_at: str | None = None
        self._exit_code: int | None = None
        self._last_error: str | None = None

    def start(self, payload: RuntimeStartRequest) -> RuntimeStatusResponse:
        with self._lock:
            self._sync_process_state_locked()
            if self._process and self._process.poll() is None:
                raise RuntimeError("当前已有推理任务在运行，请先停止后再启动。")

            config_path = self._write_runtime_config(payload)
            command = [sys.executable, "-u", "main.py", "--config", str(config_path)]

            self._logs.clear()
            self._run_token += 1
            self._stop_requested = False
            self._state = "starting"
            self._pid = None
            self._command = " ".join(command)
            self._config_path = str(config_path)
            self._started_at = now_iso()
            self._exit_code = None
            self._last_error = None
            self._append_log_locked("info", f"收到启动请求：{self._command}")

            creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            
            # 设置环境变量，告诉 main.py 帧输出目录和停止信号文件
            env = dict(__import__("os").environ)
            env["YOLO_STREAM_OUTPUT_DIR"] = str(STREAM_DIR)
            stop_file = str(GENERATED_DIR / ".yolo_stop")
            env["YOLO_STOP_FILE"] = stop_file
            Path(stop_file).unlink(missing_ok=True)
            
            process = subprocess.Popen(
                command,
                cwd=str(ROOT_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creation_flags,
                env=env,
            )

            self._process = process
            self._pid = process.pid
            token = self._run_token

        threading.Thread(target=self._stream_logs, args=(token, process), daemon=True).start()
        threading.Thread(target=self._watch_process, args=(token, process), daemon=True).start()
        threading.Thread(target=self._watch_frames, args=(token,), daemon=True).start()
        return self.snapshot()

    def stop(self) -> RuntimeStatusResponse:
        with self._lock:
            self._sync_process_state_locked()
            process = self._process
            if not process or process.poll() is not None:
                self._state = "idle"
                self._append_log_locked("warn", "收到停止请求，但当前没有运行中的推理任务。")
                return self._snapshot_locked()

            self._stop_requested = True
            self._state = "stopping"
            self._append_log_locked("warn", "收到停止请求，正在终止推理进程。")

        # 写入停止信号文件，让 pipeline 自行优雅退出
        stop_file = GENERATED_DIR / ".yolo_stop"
        stop_file.touch()
        self._append_log_locked("info", "已发出停止信号，等待推理进程退出...")
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        finally:
            stop_file.unlink(missing_ok=True)

        return self.snapshot()

    def snapshot(self) -> RuntimeStatusResponse:
        with self._lock:
            self._sync_process_state_locked()
            return self._snapshot_locked()

    def get_logs(self, limit: int) -> RuntimeLogResponse:
        with self._lock:
            items = list(self._logs)[-limit:]
        return RuntimeLogResponse(items=items)

    def _snapshot_locked(self) -> RuntimeStatusResponse:
        return RuntimeStatusResponse(
            state=self._state,
            pid=self._pid,
            command=self._command,
            configPath=self._config_path,
            startedAt=self._started_at,
            exitCode=self._exit_code,
            lastError=self._last_error,
        )

    def _sync_process_state_locked(self) -> None:
        if not self._process:
            return

        exit_code = self._process.poll()
        if exit_code is None:
            return

        self._finalize_process_locked(exit_code)

    def _finalize_process_locked(self, exit_code: int) -> None:
        self._exit_code = exit_code
        self._pid = None
        self._process = None

        if self._stop_requested:
            self._state = "idle"
            self._append_log_locked("success", f"推理进程已停止，退出码 {exit_code}。")
            self._stop_requested = False
            return

        if exit_code == 0:
            self._state = "idle"
            self._append_log_locked("success", "推理任务正常结束。")
            return

        self._state = "error"
        self._last_error = f"推理进程异常退出，退出码 {exit_code}。"
        self._append_log_locked("error", self._last_error)

    def _write_runtime_config(self, payload: RuntimeStartRequest) -> Path:
        config = apply_pipeline_overrides(
            load_base_pipeline_config(),
            source_type=payload.source,
            tracker=payload.tracker,
            confidence=payload.confidence,
            image_size=payload.image_size,
            save_video=payload.save_video,
            show_window=payload.show_window,
            video_path=payload.sample_path,
            rtsp_url=payload.rtsp_url,
        )
        save_yaml_config(RUNTIME_CONFIG_PATH, config)
        return RUNTIME_CONFIG_PATH

    def _stream_logs(self, token: int, process: subprocess.Popen[str]) -> None:
        if not process.stdout:
            return

        for raw_line in iter(process.stdout.readline, ""):
            line = raw_line.strip()
            if not line:
                continue

            # 解析遥测行（无锁，直接更新内存）
            if line.startswith("[TELEMETRY] "):
                try:
                    payload = json.loads(line[len("[TELEMETRY] "):])
                    telemetry_store.update(payload)
                except Exception:
                    pass
                continue

            with self._lock:
                if token != self._run_token:
                    continue

                level: Literal["info", "warn", "error", "success"] = "info"
                if "Traceback" in line or "RuntimeError" in line:
                    level = "error"
                elif "已关闭" in line or "正常结束" in line:
                    level = "success"
                elif "停止" in line or "退出" in line:
                    level = "warn"

                self._append_log_locked(level, line)

                if self._state == "starting" and "推理启动" in line:
                    self._state = "running"
                if "无法打开视频源" in line:
                    self._last_error = line
                    self._state = "error"

        process.stdout.close()

    def _watch_process(self, token: int, process: subprocess.Popen[str]) -> None:
        exit_code = process.wait()
        with self._lock:
            if token != self._run_token:
                return
            self._finalize_process_locked(exit_code)

    def _watch_frames(self, token: int) -> None:
        """监视帧文件，更新 frame_buffer"""
        last_mtime = 0
        while True:
            with self._lock:
                if token != self._run_token:
                    break
            
            frame_file = STREAM_DIR / "frame.jpg"
            if frame_file.exists():
                try:
                    current_mtime = frame_file.stat().st_mtime
                    if current_mtime > last_mtime:
                        frame = cv2.imread(str(frame_file))
                        if frame is not None:
                            frame_buffer.put_frame(frame)
                            last_mtime = current_mtime
                except Exception:
                    pass
            
            threading.Event().wait(timeout=0.01)  # 每 10ms 检查一次

    def _append_log_locked(
        self,
        level: Literal["info", "warn", "error", "success"],
        message: str,
    ) -> None:
        self._logs.append(RuntimeLogEntry(timestamp=now_iso(), level=level, message=message))


runtime_manager = RuntimeManager()
detector_service = DetectorService()
video_job_manager = VideoJobManager()
frame_buffer = FrameBuffer()
telemetry_store = TelemetryStore()

app = FastAPI(title="YOLOv11 Experience API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8102",
        "http://localhost:8102",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/generated", StaticFiles(directory=str(GENERATED_DIR)), name="generated")

STATIC_DIR = ROOT_DIR / "backend" / "static"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/api/mot17/sequences", response_model=MOT17SequenceListResponse)
def get_mot17_sequences() -> MOT17SequenceListResponse:
    return MOT17SequenceListResponse(items=list_mot17_sequences())


@app.post("/api/mot17/run", response_model=MOT17RunResponse)
def run_mot17_endpoint(payload: MOT17RunRequest, request: Request) -> MOT17RunResponse:
    sequence_path = ROOT_DIR / payload.sequence_path
    if not sequence_path.exists():
        raise HTTPException(status_code=404, detail=f"MOT17 序列不存在：{payload.sequence_path}")

    args = type(
        "Args",
        (),
        {
            "tracker": payload.tracker,
            "model": None,
            "conf": payload.confidence,
            "imgsz": payload.image_size,
        },
    )()
    runtime_cfg = build_runtime_cfg(load_config(DEFAULT_CONFIG), args)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sequence_name = sequence_path.name
    video_output = MOT_OUTPUT_DIR / f"{sequence_name}_{timestamp}.mp4"
    mot_output = MOT_OUTPUT_DIR / f"{sequence_name}_{timestamp}.txt"
    stream = io.StringIO()

    try:
        with contextlib.redirect_stdout(stream):
            actual_video = run_mot17_sequence(
                sequence_path=sequence_path,
                cfg=runtime_cfg,
                show=False,
                save_video=True,
                video_output=video_output,
                mot_output=mot_output,
            )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"MOT17 测试失败：{exc}") from exc

    logs = [line for line in stream.getvalue().splitlines() if line.strip()]
    total_frames, unique_tracks, avg_tracks_per_frame, duration_seconds = summarize_mot_file(mot_output, sequence_path)

    video_path = Path(actual_video) if actual_video else video_output
    return MOT17RunResponse(
        sequenceName=sequence_name,
        sequencePath=payload.sequence_path,
        tracker=payload.tracker,
        videoUrl=public_url(request, video_path),
        motUrl=public_url(request, mot_output),
        logs=logs[-50:],
        totalFrames=total_frames,
        uniqueTracks=unique_tracks,
        avgTracksPerFrame=avg_tracks_per_frame,
        durationSeconds=duration_seconds,
    )


@app.post("/api/image/detect", response_model=ImageDetectResponse)
def detect_image(
    request: Request,
    file: UploadFile = File(...),
    confidence: float = Form(0.35),
    image_size: int = Form(960, alias="imageSize"),
) -> ImageDetectResponse:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
        raise HTTPException(status_code=400, detail="仅支持 jpg/jpeg/png/bmp/webp 图片。")

    stored = save_upload_file(file, UPLOAD_DIR)
    try:
        output_path, detections = detector_service.detect_image(stored, confidence, image_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"图片检测失败：{exc}") from exc
    finally:
        file.file.close()

    return ImageDetectResponse(
        filename=file.filename or stored.name,
        imageUrl=public_url(request, output_path),
        count=len(detections),
        detections=detections,
    )


@app.post("/api/video/detect", response_model=VideoDetectResponse)
def detect_video(
    request: Request,
    file: UploadFile = File(...),
    tracker: str = Form("bytetrack"),
    confidence: float = Form(0.35),
    image_size: int = Form(960, alias="imageSize"),
) -> VideoDetectResponse:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".mp4", ".avi", ".mov", ".mkv"}:
        raise HTTPException(status_code=400, detail="仅支持 mp4/avi/mov/mkv 视频。")
    if tracker not in {"bytetrack", "botsort", "strongsort"}:
        raise HTTPException(status_code=400, detail="不支持的跟踪器类型。")

    stored = save_upload_file(file, UPLOAD_DIR)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = VIDEO_OUTPUT_DIR / f"{stored.stem}_{timestamp}.mp4"
    config_path = TEMP_CONFIG_DIR / f"video_{stored.stem}_{timestamp}.yaml"

    try:
        runtime = apply_pipeline_overrides(
            load_base_pipeline_config(),
            source_type="video",
            tracker=tracker,
            confidence=confidence,
            image_size=image_size,
            save_video=True,
            show_window=False,
            video_path=str(stored),
            output_path=str(output_path),
        )
        save_yaml_config(config_path, runtime)

        command = [sys.executable, "-u", "main.py", "--config", str(config_path)]
        result = subprocess.run(
            command,
            cwd=str(ROOT_DIR),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    finally:
        file.file.close()

    logs = [line for line in (result.stdout or "").splitlines() if line.strip()]
    if result.returncode != 0:
        error_lines = logs[-10:] if logs else [(result.stderr or "视频检测失败").strip()]
        raise HTTPException(status_code=500, detail="\n".join(error_lines))

    return VideoDetectResponse(
        filename=file.filename or stored.name,
        outputUrl=public_url(request, output_path),
        logs=logs[-50:],
        exitCode=result.returncode,
    )


@app.post("/api/video/detect/start", response_model=VideoJobStartResponse)
def start_video_detect(
    file: UploadFile = File(...),
    tracker: str = Form("bytetrack"),
    confidence: float = Form(0.35),
    image_size: int = Form(960, alias="imageSize"),
) -> VideoJobStartResponse:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".mp4", ".avi", ".mov", ".mkv"}:
        raise HTTPException(status_code=400, detail="仅支持 mp4/avi/mov/mkv 视频。")
    if tracker not in {"bytetrack", "botsort", "strongsort"}:
        raise HTTPException(status_code=400, detail="不支持的跟踪器类型。")

    stored = save_upload_file(file, UPLOAD_DIR)
    file.file.close()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = VIDEO_OUTPUT_DIR / f"{stored.stem}_{timestamp}.mp4"
    return video_job_manager.start(
        filename=file.filename or stored.name,
        tracker=tracker,
        confidence=confidence,
        image_size=image_size,
        stored_path=stored,
        output_path=output_path,
    )


@app.get("/api/video/detect/status/{job_id}", response_model=VideoJobStatusResponse)
def get_video_detect_status(job_id: str, request: Request) -> VideoJobStatusResponse:
    try:
        status = video_job_manager.get_status(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="视频任务不存在。") from exc

    output_path = video_job_manager.get_output_path(job_id)
    if status.output_url is None and output_path is not None and output_path.exists():
        video_job_manager.set_output_url(job_id, public_url(request, output_path))
        status = video_job_manager.get_status(job_id)

    return status


@app.post("/api/runtime/start", response_model=RuntimeStatusResponse)
def start_runtime(payload: RuntimeStartRequest) -> RuntimeStatusResponse:
    try:
        return runtime_manager.start(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/runtime/stop", response_model=RuntimeStatusResponse)
def stop_runtime() -> RuntimeStatusResponse:
    telemetry_store.reset()
    return runtime_manager.stop()


@app.get("/api/runtime/status", response_model=RuntimeStatusResponse)
def get_runtime_status() -> RuntimeStatusResponse:
    return runtime_manager.snapshot()


@app.get("/api/runtime/telemetry")
def get_runtime_telemetry() -> dict:
    return telemetry_store.snapshot()


@app.get("/api/runtime/logs", response_model=RuntimeLogResponse)
def get_runtime_logs(limit: int = Query(default=50, ge=1, le=200)) -> RuntimeLogResponse:
    return runtime_manager.get_logs(limit)


@app.get("/api/runtime/stream")
def get_runtime_stream():
    """实时视频流 MJPEG"""
    return StreamingResponse(
        frame_generator(frame_buffer),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.get("/{full_path:path}", include_in_schema=False)
def serve_spa(full_path: str):
    """SPA 兜底路由，所有非 API 请求均返回前端 index.html"""
    index_file = STATIC_DIR / "index.html"
    if STATIC_DIR.exists() and index_file.exists():
        return FileResponse(str(index_file))
    return {"detail": "前端尚未构建，请先执行 pnpm.cmd build"}