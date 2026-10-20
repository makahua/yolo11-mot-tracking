"""
主入口 — 一条命令启动推理
用法:
    python main.py                              # 使用默认配置（摄像头）
    python main.py --source video --path data/test.mp4
    python main.py --tracker botsort
    python main.py --conf 0.3 --imgsz 1280
"""
import argparse
import yaml
from pathlib import Path

from src.pipeline import MOTPipeline


def parse_args():
    parser = argparse.ArgumentParser(description="YOLOv11 多目标人物检测与跟踪")
    parser.add_argument("--config", type=str, default="configs/pipeline_config.yaml",
                        help="配置文件路径")
    parser.add_argument("--source", type=str, choices=["camera", "video", "rtsp"],
                        help="视频源类型（覆盖配置文件）")
    parser.add_argument("--path", type=str,
                        help="视频文件路径（source=video 时使用）")
    parser.add_argument("--camera-id", type=int,
                        help="摄像头 ID（source=camera 时使用）")
    parser.add_argument("--tracker", type=str, choices=["bytetrack", "botsort", "strongsort"],
                        help="跟踪算法（覆盖配置文件）")
    parser.add_argument("--model", type=str,
                        help="模型权重路径（覆盖配置文件）")
    parser.add_argument("--conf", type=float, help="置信度阈值")
    parser.add_argument("--imgsz", type=int, help="推理输入尺寸")
    parser.add_argument("--save", action="store_true", help="保存输出视频")
    parser.add_argument("--no-show", action="store_true", help="不显示窗口（仅保存）")
    return parser.parse_args()


def apply_overrides(config_path: str, args) -> str:
    """将命令行参数覆盖到配置文件并保存为临时配置"""
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if args.source:
        cfg["source"]["type"] = args.source
    if args.path:
        cfg["source"]["video_path"] = args.path
    if args.camera_id is not None:
        cfg["source"]["camera_id"] = args.camera_id
    if args.tracker:
        cfg["tracker"]["type"] = args.tracker
        cfg["tracker"]["config_file"] = f"trackers/{args.tracker}.yaml"
    if args.model:
        cfg["detector"]["model"] = args.model
    if args.conf:
        cfg["detector"]["conf"] = args.conf
    if args.imgsz:
        cfg["detector"]["imgsz"] = args.imgsz
    if args.save:
        cfg["visualizer"]["save_video"] = True
    if args.no_show:
        cfg["visualizer"]["show"] = False

    # 写入临时配置
    tmp_path = "configs/_runtime_config.yaml"
    with open(tmp_path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True)
    return tmp_path


def main():
    args = parse_args()
    config_path = apply_overrides(args.config, args)

    pipeline = MOTPipeline(config_path)
    pipeline.run(config_path)


if __name__ == "__main__":
    main()
