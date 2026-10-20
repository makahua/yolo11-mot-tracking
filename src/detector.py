"""
YOLOv11 人物检测器封装
支持：图片、视频帧、摄像头帧
"""
# 使用内部路径导入，避免触发 SAM 模块对 torchvision 的依赖
from ultralytics.models.yolo.model import YOLO
import numpy as np
import cv2


class PersonDetector:
    def __init__(self, model_path: str, conf: float = 0.35, iou: float = 0.45,
                 imgsz: int = 640, device: str = "0", half: bool = True,
                 max_det: int = 300):
        """
        Args:
            model_path: YOLOv11 权重路径
            conf: 置信度阈值
            iou: NMS IoU 阈值
            imgsz: 推理输入尺寸
            device: 推理设备 ("0" = GPU 0, "cpu")
            half: 是否使用 FP16 加速
            max_det: 单帧最大检测数
        """
        self.model = YOLO(model_path)
        self.conf = conf
        self.iou = iou
        self.imgsz = imgsz
        self.device = device
        self.half = half and (device != "cpu")
        self.max_det = max_det

    def detect(self, frame: np.ndarray) -> np.ndarray:
        """
        检测单帧中的所有人物

        Args:
            frame: BGR 格式图像 (H, W, 3)

        Returns:
            dets: shape (N, 6) → [x1, y1, x2, y2, conf, cls]
                  如果没有检测结果则返回 shape (0, 6)
        """
        results = self.model(
            frame,
            classes=[0],          # 只检测 person
            conf=self.conf,
            iou=self.iou,
            imgsz=self.imgsz,
            device=self.device,
            half=self.half,
            max_det=self.max_det,
            verbose=False,
        )

        result = results[0]
        boxes = result.boxes

        if boxes is None or len(boxes) == 0:
            return np.empty((0, 6), dtype=np.float32)

        # xyxy + conf + cls
        dets = np.concatenate([
            boxes.xyxy.cpu().numpy(),
            boxes.conf.cpu().numpy().reshape(-1, 1),
            boxes.cls.cpu().numpy().reshape(-1, 1),
        ], axis=1).astype(np.float32)

        return dets

    def warmup(self):
        """推理前进行一次 warmup，消除首帧延迟"""
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        self.detect(dummy)
        print("[Detector] Warmup done.")
