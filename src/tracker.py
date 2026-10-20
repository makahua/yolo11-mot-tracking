"""
多目标跟踪器封装（基于 BoxMOT）
支持 ByteTrack / BoT-SORT / StrongSORT++
"""
from pathlib import Path

import numpy as np
import torch
import yaml
from boxmot.trackers.botsort.botsort import BotSort
from boxmot.trackers.bytetrack.bytetrack import ByteTrack
from boxmot.trackers.strongsort.strongsort import StrongSort

TRACKER_MAP = {
    "bytetrack": ByteTrack,
    "botsort": BotSort,
    "strongsort": StrongSort,
}


class PersonTracker:
    def __init__(self, tracker_type: str = "bytetrack",
                 config_file: str = "trackers/bytetrack.yaml",
                 reid_model: str = None,
                 device: str = "0",
                 half: bool = True,
                 frame_rate: int = 30):
        """
        Args:
            tracker_type: 跟踪算法类型 bytetrack / botsort / strongsort
            config_file: 跟踪器配置文件路径
            reid_model: Re-ID 模型权重路径（None 表示不使用 Re-ID）
            device: 推理设备
            half: Re-ID 是否使用半精度
            frame_rate: 视频帧率
        """
        tracker_cls = TRACKER_MAP.get(tracker_type.lower())
        if tracker_cls is None:
            raise ValueError(f"未知跟踪器类型: {tracker_type}，"
                             f"可选: {list(TRACKER_MAP.keys())}")

        self.tracker_type = tracker_type.lower()
        self.device = device
        self.half = half
        self.frame_rate = frame_rate

        tracker_cfg = self._load_tracker_config(config_file)
        self.tracker = self._build_tracker(
            tracker_cls=tracker_cls,
            tracker_cfg=tracker_cfg,
            reid_model=reid_model,
        )

    def _load_tracker_config(self, config_file: str) -> dict:
        config_path = Path(config_file)
        if not config_path.exists():
            raise FileNotFoundError(f"跟踪器配置文件不存在: {config_file}")

        with config_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _to_torch_device(self) -> torch.device:
        if str(self.device).lower() == "cpu":
            return torch.device("cpu")
        return torch.device(f"cuda:{self.device}")

    def _build_tracker(self, tracker_cls, tracker_cfg: dict, reid_model: str):
        if self.tracker_type == "bytetrack":
            return tracker_cls(
                min_conf=tracker_cfg.get("track_low_thresh", 0.1),
                track_thresh=tracker_cfg.get("track_high_thresh", 0.45),
                match_thresh=tracker_cfg.get("match_thresh", 0.8),
                track_buffer=tracker_cfg.get("track_buffer", 30),
                frame_rate=self.frame_rate,
            )

        if self.tracker_type == "botsort":
            with_reid = tracker_cfg.get("with_reid", False)
            reid_weights = Path(reid_model) if reid_model else Path()
            return tracker_cls(
                reid_weights=reid_weights,
                device=self._to_torch_device(),
                half=self.half,
                track_high_thresh=tracker_cfg.get("track_high_thresh", 0.5),
                track_low_thresh=tracker_cfg.get("track_low_thresh", 0.1),
                new_track_thresh=tracker_cfg.get("new_track_thresh", 0.6),
                track_buffer=tracker_cfg.get("track_buffer", 30),
                match_thresh=tracker_cfg.get("match_thresh", 0.8),
                proximity_thresh=tracker_cfg.get("proximity_thresh", 0.5),
                appearance_thresh=tracker_cfg.get("appearance_thresh", 0.25),
                cmc_method=tracker_cfg.get("gmc_method", "ecc"),
                frame_rate=self.frame_rate,
                with_reid=with_reid,
            )

        if not reid_model:
            raise ValueError("StrongSORT 需要配置 tracker.reid_model")

        return tracker_cls(
            reid_weights=Path(reid_model),
            device=self._to_torch_device(),
            half=self.half,
            min_conf=tracker_cfg.get("track_low_thresh", 0.1),
            max_iou_dist=tracker_cfg.get("match_thresh", 0.8),
            n_init=tracker_cfg.get("min_hits", 3),
        )

    def update(self, dets: np.ndarray, frame: np.ndarray) -> np.ndarray:
        """
        更新跟踪状态

        Args:
            dets: 检测结果，shape (N, 6) → [x1, y1, x2, y2, conf, cls]
            frame: 当前帧 BGR 图像（Re-ID 需要）

        Returns:
            tracks: shape (M, 7) → [x1, y1, x2, y2, track_id, conf, cls]
                    M 为当前激活轨迹数
        """
        if dets is None or len(dets) == 0:
            # 无检测时喂空数组，维持 Kalman 预测
            empty = np.empty((0, 6), dtype=np.float32)
            return self.tracker.update(empty, frame)

        return self.tracker.update(dets, frame)

    def reset(self):
        """重置跟踪器状态（换视频源时调用）"""
        self.tracker.reset()
