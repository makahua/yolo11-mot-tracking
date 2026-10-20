"""
训练脚本
用法：
    python tools/train.py
    python tools/train.py --epochs 100 --imgsz 1280 --model yolo11l
"""
import argparse
from pathlib import Path
from ultralytics.models.yolo.model import YOLO


def parse_args():
    parser = argparse.ArgumentParser(description="YOLOv11 人物检测训练")
    parser.add_argument("--model",   type=str, default="yolo11m.pt", help="预训练权重")
    parser.add_argument("--data",    type=str, default="data/merged_dataset/dataset.yaml")
    parser.add_argument("--epochs",  type=int, default=50)
    parser.add_argument("--imgsz",   type=int, default=640)
    parser.add_argument("--batch",   type=int, default=16)
    parser.add_argument("--device",  type=str, default="0")
    parser.add_argument("--name",    type=str, default="person_det_v1")
    return parser.parse_args()


def main():
    args = parse_args()

    model_path = Path("models") / args.model
    if not model_path.exists():
        print(f"[INFO] 本地未找到 {model_path}，将从 Ultralytics 自动下载...")
        model_path = args.model  # ultralytics 会自动下载

    model = YOLO(str(model_path))

    results = model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        lr0=1e-4,
        freeze=10,           # 冻结前 10 层 Backbone（微调策略）
        workers=4,
        project="runs/train",
        name=args.name,
        # 数据增强（针对复杂场景）
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.5,           # 光照鲁棒性增强
        mixup=0.1,
        copy_paste=0.2,      # 遮挡场景增强
        mosaic=1.0,
        # 单类别优化
        single_cls=False,
        classes=[0],
        verbose=True,
    )

    print(f"\n训练完成！最佳权重: {results.save_dir}/weights/best.pt")


if __name__ == "__main__":
    main()
