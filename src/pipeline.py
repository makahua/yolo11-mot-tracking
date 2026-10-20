"""
主推理流水线
整合：检测 → 跟踪 → 可视化
"""
import os
import time
from pathlib import Path

import cv2
import numpy as np
import yaml

from src.detector import PersonDetector
from src.tracker import PersonTracker
from src.visualizer import Visualizer


def create_video_writer(output_path: str | Path, fps: float, size: tuple[int, int]):
    """创建 VideoWriter，按优先级尝试多种编码器；返回 (writer, actual_path)"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    for codec, ext in [("avc1", ".mp4"), ("mp4v", ".mp4")]:
        out = output_path.with_suffix(ext) if output_path.suffix != ext else output_path
        out.parent.mkdir(parents=True, exist_ok=True)
        fourcc = cv2.VideoWriter_fourcc(*codec)
        writer = cv2.VideoWriter(str(out), fourcc, fps, size)
        if writer.isOpened():
            print(f"[Pipeline] 编码器: {codec}")
            return writer, str(out)
        writer.release()
    raise RuntimeError("无法创建视频写入器")


class MOTPipeline:
    def __init__(self, config_path: str = "configs/pipeline_config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        det_cfg = cfg["detector"]
        trk_cfg = cfg["tracker"]
        viz_cfg = cfg["visualizer"]

        self.detector = PersonDetector(
            model_path=det_cfg["model"],
            conf=det_cfg["conf"],
            iou=det_cfg["iou"],
            imgsz=det_cfg["imgsz"],
            device=str(det_cfg["device"]),
            half=det_cfg.get("half", True),
            max_det=det_cfg.get("max_det", 300),
        )

        self.tracker = PersonTracker(
            tracker_type=trk_cfg["type"],
            config_file=trk_cfg["config_file"],
            reid_model=trk_cfg.get("reid_model"),
            device=str(det_cfg["device"]),
        )

        self.visualizer = Visualizer(
            trail_len=viz_cfg.get("trail_len", 30),
            show_fps=viz_cfg.get("show_fps", True),
            show_count=viz_cfg.get("show_count", True),
        )

        self.save_video = viz_cfg.get("save_video", False)
        self.output_path = viz_cfg.get("output_path", "results/output.mp4")
        self.writer = None

        # FPS 计算（滑动平均）
        self._fps_buf = []
        self._fps_buf_size = 30

        # 遥测指标
        self._track_age: dict[int, int] = {}   # track_id -> 已出现帧数
        self._last_latency_ms: float = 0.0
        self._last_fps: float = 0.0
        self._last_people: int = 0
        self._frame_h: int = 1
        self._frame_w: int = 1

    def _get_source(self, cfg: dict):
        src_cfg = cfg["source"]
        src_type = src_cfg["type"]
        if src_type == "camera":
            cap = cv2.VideoCapture(src_cfg.get("camera_id", 0))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        elif src_type == "video":
            cap = cv2.VideoCapture(src_cfg["video_path"])
        elif src_type == "rtsp":
            cap = cv2.VideoCapture(src_cfg["rtsp_url"])
        else:
            raise ValueError(f"未知 source.type: {src_type}")
        return cap

    def process_frame(self, frame: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """
        处理单帧

        Returns:
            (vis_frame, tracks)  tracks shape (M, 7)
        """
        t0 = time.perf_counter()

        dets = self.detector.detect(frame)
        tracks = self.tracker.update(dets, frame)

        elapsed = time.perf_counter() - t0
        self._fps_buf.append(elapsed)
        if len(self._fps_buf) > self._fps_buf_size:
            self._fps_buf.pop(0)
        fps = 1.0 / (sum(self._fps_buf) / len(self._fps_buf))

        # 更新遥测
        track_arr = tracks if tracks is not None else np.empty((0, 7))
        active_ids = {int(t[4]) for t in track_arr}

        # 更新各 track 的累计帧数
        for tid in active_ids:
            self._track_age[tid] = self._track_age.get(tid, 0) + 1
        # 清理长期消失的 id（不在 active 中超过 60 帧则遗忘）
        gone = [k for k in list(self._track_age) if k not in active_ids]
        for k in gone:
            self._track_age[k] -= 1
            if self._track_age[k] <= 0:
                del self._track_age[k]

        people_count = len(active_ids)
        stable_count = sum(1 for tid in active_ids if self._track_age.get(tid, 0) >= 5)
        track_stability = round(stable_count / people_count * 100) if people_count > 0 else 0

        h, w = frame.shape[:2]
        self._frame_h, self._frame_w = h, w
        bbox_area = sum(
            max(0, int(t[2]) - int(t[0])) * max(0, int(t[3]) - int(t[1]))
            for t in track_arr
        )
        coverage = round(min(100.0, bbox_area / (h * w) * 100), 1) if h * w > 0 else 0.0

        self._last_fps = round(fps, 1)
        self._last_latency_ms = round(elapsed * 1000, 1)
        self._last_people = people_count
        self._last_track_stability = track_stability
        self._last_coverage = coverage

        # 每帧向 stdout 打印遥测行（后端日志线程解析）
        print(
            f"[TELEMETRY] "
            f'{{"fps":{self._last_fps},'
            f'"people_count":{self._last_people},'
            f'"latency_ms":{self._last_latency_ms},'
            f'"track_stability":{self._last_track_stability},'
            f'"coverage":{self._last_coverage}}}',
            flush=True,
        )

        vis = self.visualizer.draw(frame, track_arr, fps)
        return vis, tracks

    def run(self, config_path: str = "configs/pipeline_config.yaml"):
        """启动推理主循环"""
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        cap = self._get_source(cfg)
        if not cap.isOpened():
            raise RuntimeError("无法打开视频源，请检查摄像头连接或视频路径")

        print("[Pipeline] 推理启动，按 Q 退出...")
        self.detector.warmup()

        show = cfg["visualizer"].get("show", True)
        show_available = show  # 运行时按需降级

        # 获取流输出目录（来自环境变量）
        stream_output_dir = os.environ.get("YOLO_STREAM_OUTPUT_DIR")
        if stream_output_dir:
            stream_output_dir = Path(stream_output_dir)
            stream_output_dir.mkdir(parents=True, exist_ok=True)
            frame_output = stream_output_dir / "frame.jpg"
        else:
            frame_output = None

        stop_file = Path(os.environ.get("YOLO_STOP_FILE", ".yolo_stop"))
        if stop_file.exists():
            stop_file.unlink()

        try:
            while True:
                if stop_file.exists():
                    print("[Pipeline] 检测到停止信号，正在退出...")
                    stop_file.unlink()
                    break

                ret, frame = cap.read()
                if not ret:
                    print("[Pipeline] 视频读取结束或摄像头断开")
                    break

                vis, tracks = self.process_frame(frame)

                # 保存实时帧到共享位置（用于 MJPEG 流）
                if frame_output:
                    try:
                        cv2.imwrite(str(frame_output), vis)
                    except Exception as e:
                        print(f"[Pipeline] 帧保存失败: {e}")

                if self.save_video:
                    if self.writer is None:
                        h, w = vis.shape[:2]
                        self.writer, self.output_path = create_video_writer(
                            self.output_path, 30, (w, h)
                        )
                    self.writer.write(vis)

                if show_available:
                    try:
                        cv2.imshow("YOLOv11 MOT", vis)
                        if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
                            break
                    except cv2.error:
                        print("[Pipeline] GUI 不可用，自动切换为无窗口模式")
                        show_available = False

        except KeyboardInterrupt:
            print("[Pipeline] 收到停止信号，正在保存视频...")
        finally:
            cap.release()
            if self.writer:
                self.writer.release()
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass
            print("[Pipeline] 已关闭")
