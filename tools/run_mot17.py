"""
MOT17 单序列推理脚本。

示例:
    python tools/run_mot17.py --seq MOT17/images/train/MOT17-02-FRCNN --mot-output results/mot/MOT17-02-FRCNN.txt
    python tools/run_mot17.py --seq MOT17/images/train/MOT17-02-FRCNN --tracker botsort --no-show
"""
from __future__ import annotations

import argparse
import configparser
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.detector import PersonDetector
from src.tracker import PersonTracker
from src.visualizer import Visualizer


def _create_writer(path: str, fps: float, size: tuple[int, int]):
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    for codec, ext in [("avc1", ".mp4"), ("mp4v", ".mp4")]:
        out = output.with_suffix(ext) if output.suffix != ext else output
        out.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*codec), fps, size)
        if writer.isOpened():
            return writer, str(out)
        writer.release()
    raise RuntimeError("无法创建视频写入器")

DEFAULT_CONFIG = ROOT / "configs" / "pipeline_config.yaml"


class MOTImageSequenceReader:
    def __init__(self, sequence_path: str | Path):
        self.sequence_path = Path(sequence_path)
        self.img_dir = self.sequence_path / "img1"
        if not self.img_dir.exists():
            raise FileNotFoundError(f"MOT17 序列目录缺少 img1: {self.img_dir}")

        self.sequence_name = self.sequence_path.name
        self.frame_rate = 30
        self.frame_size: tuple[int, int] | None = None
        self._index = 0
        self._opened = True

        seqinfo_path = self.sequence_path / "seqinfo.ini"
        if seqinfo_path.exists():
            parser = configparser.ConfigParser()
            parser.read(seqinfo_path, encoding="utf-8")
            self.frame_rate = parser.getint("Sequence", "frameRate", fallback=30)
            width = parser.getint("Sequence", "imWidth", fallback=0)
            height = parser.getint("Sequence", "imHeight", fallback=0)
            if width > 0 and height > 0:
                self.frame_size = (width, height)

        self.image_files = sorted(self.img_dir.glob("*.jpg"))
        if not self.image_files:
            self.image_files = sorted(self.img_dir.glob("*.png"))
        if not self.image_files:
            raise FileNotFoundError(f"MOT17 序列中未找到图像帧: {self.img_dir}")

    def isOpened(self) -> bool:
        return self._opened

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self._index >= len(self.image_files):
            return False, None

        frame = cv2.imread(str(self.image_files[self._index]))
        self._index += 1
        if frame is None:
            return False, None

        if self.frame_size is None:
            h, w = frame.shape[:2]
            self.frame_size = (w, h)
        return True, frame

    def release(self):
        self._opened = False


class MOTChallengeWriter:
    def __init__(self, output_path: str | Path):
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = self.output_path.open("w", encoding="utf-8")

    def write(self, frame_id: int, tracks: np.ndarray | None):
        if tracks is None or len(tracks) == 0:
            return

        for track in tracks:
            x1, y1, x2, y2 = map(float, track[:4])
            track_id = int(track[4])
            conf = float(track[5])
            width = max(0.0, x2 - x1)
            height = max(0.0, y2 - y1)
            self._fp.write(
                f"{frame_id},{track_id},{x1:.2f},{y1:.2f},{width:.2f},{height:.2f},{conf:.6f},-1,-1,-1\n"
            )

    def close(self):
        self._fp.close()


def load_config(config_path: str | Path) -> dict:
    with Path(config_path).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_runtime_cfg(base_cfg: dict, args) -> dict:
    cfg = yaml.safe_load(yaml.safe_dump(base_cfg, allow_unicode=True))
    if args.tracker:
        cfg["tracker"]["type"] = args.tracker
        cfg["tracker"]["config_file"] = f"trackers/{args.tracker}.yaml"
    if args.model:
        cfg["detector"]["model"] = args.model
    if args.conf is not None:
        cfg["detector"]["conf"] = args.conf
    if args.imgsz is not None:
        cfg["detector"]["imgsz"] = args.imgsz
    return cfg


def run_mot17_sequence(
    sequence_path: str | Path,
    cfg: dict,
    show: bool = False,
    save_video: bool = False,
    video_output: str | Path | None = None,
    mot_output: str | Path | None = None,
):
    reader = MOTImageSequenceReader(sequence_path)

    det_cfg = cfg["detector"]
    trk_cfg = cfg["tracker"]
    viz_cfg = cfg["visualizer"]

    detector = PersonDetector(
        model_path=det_cfg["model"],
        conf=det_cfg["conf"],
        iou=det_cfg["iou"],
        imgsz=det_cfg["imgsz"],
        device=str(det_cfg["device"]),
        half=det_cfg.get("half", True),
        max_det=det_cfg.get("max_det", 300),
    )
    tracker = PersonTracker(
        tracker_type=trk_cfg["type"],
        config_file=trk_cfg["config_file"],
        reid_model=trk_cfg.get("reid_model"),
        device=str(det_cfg["device"]),
        half=det_cfg.get("half", True),
        frame_rate=reader.frame_rate,
    )
    visualizer = Visualizer(
        trail_len=viz_cfg.get("trail_len", 30),
        show_fps=viz_cfg.get("show_fps", True),
        show_count=viz_cfg.get("show_count", True),
    )

    mot_writer = MOTChallengeWriter(mot_output) if mot_output else None
    video_writer = None
    fps_buf = []
    fps_buf_size = 30
    frame_id = 0

    print(f"[MOT17] 推理启动: {reader.sequence_name}")
    detector.warmup()

    show_gui = show

    try:
        while True:
            ret, frame = reader.read()
            if not ret:
                break

            frame_id += 1
            t0 = time.perf_counter()
            dets = detector.detect(frame)
            tracks = tracker.update(dets, frame)
            elapsed = time.perf_counter() - t0

            fps_buf.append(elapsed)
            if len(fps_buf) > fps_buf_size:
                fps_buf.pop(0)
            fps = 1.0 / (sum(fps_buf) / len(fps_buf))

            vis = visualizer.draw(frame, tracks if tracks is not None else np.empty((0, 7)), fps)

            if mot_writer:
                mot_writer.write(frame_id, tracks)

            if save_video:
                if video_output is None:
                    video_output = ROOT / "results" / f"{reader.sequence_name}.mp4"
                if video_writer is None:
                    h, w = vis.shape[:2]
                    video_writer, _actual_path = _create_writer(
                        str(video_output), reader.frame_rate, (w, h)
                    )
                    video_output = str(_actual_path)
                video_writer.write(vis)

            if show_gui:
                try:
                    cv2.imshow("YOLOv11 MOT17", vis)
                    if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
                        break
                except cv2.error:
                    print("[MOT17] GUI 不可用，自动切换为无窗口模式")
                    show_gui = False
    finally:
        reader.release()
        if video_writer:
            video_writer.release()
        if mot_writer:
            mot_writer.close()
        try:
            cv2.destroyAllWindows()
        except cv2.error:
            pass
        print(f"[MOT17] 推理结束: {reader.sequence_name}  共 {frame_id} 帧")
        if mot_output:
            print(f"[MOT17] MOTChallenge txt → {Path(mot_output).resolve()}")
        if save_video:
            actual_video = video_output if video_output else ROOT / "results" / f"{reader.sequence_name}.mp4"
            print(f"[MOT17] 可视化视频  → {Path(actual_video).resolve()}")
        if not mot_output and not save_video:
            print("[MOT17] 提示: 未指定 --mot-output 或 --save-video，本次推理结果未保存。")
        return str(video_output) if save_video else None


def parse_args():
    parser = argparse.ArgumentParser(description="MOT17 单序列推理")
    parser.add_argument("--config", type=str, default=str(DEFAULT_CONFIG), help="基础配置文件")
    parser.add_argument("--seq", required=True, help="MOT17 序列目录，例如 MOT17/images/train/MOT17-02-FRCNN")
    parser.add_argument("--tracker", choices=["bytetrack", "botsort", "strongsort"], help="覆盖跟踪器类型")
    parser.add_argument("--model", type=str, help="覆盖检测模型权重")
    parser.add_argument("--conf", type=float, help="覆盖置信度阈值")
    parser.add_argument("--imgsz", type=int, help="覆盖输入尺寸")
    parser.add_argument("--show", action="store_true", help="显示可视化窗口")
    parser.add_argument("--no-show", action="store_true", help="不显示窗口")
    parser.add_argument("--save-video", action="store_true", help="保存可视化视频")
    parser.add_argument("--video-output", type=str, help="可视化视频输出路径")
    parser.add_argument("--mot-output", type=str, help="MOTChallenge txt 输出路径")
    return parser.parse_args()


def main():
    args = parse_args()
    cfg = build_runtime_cfg(load_config(args.config), args)
    show = False if args.no_show else bool(args.show)
    run_mot17_sequence(
        sequence_path=args.seq,
        cfg=cfg,
        show=show,
        save_video=args.save_video,
        video_output=args.video_output,
        mot_output=args.mot_output,
    )


if __name__ == "__main__":
    main()