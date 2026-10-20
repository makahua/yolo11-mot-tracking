"""
可视化工具
- BBox + Track ID 绘制
- 历史轨迹线
- FPS / 人数叠加显示
"""
import cv2
import numpy as np
from collections import defaultdict, deque


# 40 种高对比度颜色，用 track_id % 40 索引
_PALETTE = [
    (255, 56, 56),  (255, 157, 151), (255, 112, 31),  (255, 178, 29),
    (207, 210, 49), (72, 249, 10),   (146, 204, 23),  (61, 219, 134),
    (26, 147, 52),  (0, 212, 187),   (44, 153, 168),  (0, 194, 255),
    (52, 69, 147),  (100, 115, 255), (0, 24, 236),    (132, 56, 255),
    (82, 0, 133),   (203, 56, 255),  (255, 149, 200), (255, 55, 199),
    (255, 56, 56),  (255, 157, 151), (255, 112, 31),  (255, 178, 29),
    (207, 210, 49), (72, 249, 10),   (146, 204, 23),  (61, 219, 134),
    (26, 147, 52),  (0, 212, 187),   (44, 153, 168),  (0, 194, 255),
    (52, 69, 147),  (100, 115, 255), (0, 24, 236),    (132, 56, 255),
    (82, 0, 133),   (203, 56, 255),  (255, 149, 200), (255, 55, 199),
]


def _get_color(track_id: int):
    return _PALETTE[int(track_id) % len(_PALETTE)]


class Visualizer:
    def __init__(self, trail_len: int = 30, show_fps: bool = True,
                 show_count: bool = True):
        self.trail_len = trail_len
        self.show_fps = show_fps
        self.show_count = show_count
        # 每个 track_id 的历史中心点队列
        self._trails: dict[int, deque] = defaultdict(lambda: deque(maxlen=trail_len))

    def draw(self, frame: np.ndarray, tracks: np.ndarray, fps: float = 0.0) -> np.ndarray:
        """
        在帧上绘制跟踪结果

        Args:
            frame: BGR 图像
            tracks: shape (M, 7) → [x1, y1, x2, y2, track_id, conf, cls]
            fps: 当前帧率

        Returns:
            标注后的 frame
        """
        vis = frame.copy()
        active_ids = set()

        for track in tracks:
            x1, y1, x2, y2 = int(track[0]), int(track[1]), int(track[2]), int(track[3])
            tid = int(track[4])
            conf = float(track[5])
            color = _get_color(tid)
            active_ids.add(tid)

            # 更新轨迹
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            self._trails[tid].append((cx, cy))

            # 绘制边界框
            cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)

            # 绘制 ID 标签
            label = f"ID:{tid}"
            (lw, lh), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(vis, (x1, y1 - lh - baseline - 4), (x1 + lw, y1), color, -1)
            cv2.putText(vis, label, (x1, y1 - baseline - 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            # 绘制历史轨迹线
            pts = list(self._trails[tid])
            for i in range(1, len(pts)):
                alpha = i / len(pts)
                thickness = max(1, int(alpha * 3))
                cv2.line(vis, pts[i - 1], pts[i], color, thickness)

        # 清理已消失的轨迹记录（避免内存持续增长）
        stale = set(self._trails.keys()) - active_ids
        for tid in stale:
            del self._trails[tid]

        # 叠加 FPS 和人数信息
        h, w = vis.shape[:2]
        if self.show_count:
            count_text = f"Persons: {len(tracks)}"
            cv2.putText(vis, count_text, (10, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
        if self.show_fps and fps > 0:
            fps_text = f"FPS: {fps:.1f}"
            cv2.putText(vis, fps_text, (10, 70),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)

        return vis

    def reset(self):
        self._trails.clear()
