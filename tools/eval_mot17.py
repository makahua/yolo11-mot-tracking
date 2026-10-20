"""
MOT17 批量推理 + TrackEval 评测脚本。

示例:
    python tools/eval_mot17.py --split train --tracker-name yolo_bytetrack
    python tools/eval_mot17.py --split train --seq MOT17-02-FRCNN MOT17-04-FRCNN --no-show
"""
import argparse
import configparser
import importlib
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_CONFIG = ROOT / "configs" / "pipeline_config.yaml"
DEFAULT_MOT_ROOT = ROOT / "MOT17" / "images"
DEFAULT_OUTPUT_ROOT = ROOT / "results" / "trackeval"


def parse_args():
    parser = argparse.ArgumentParser(description="MOT17 批量推理与 TrackEval 评测")
    parser.add_argument("--config", type=str, default=str(DEFAULT_CONFIG), help="基础配置文件")
    parser.add_argument("--mot-root", type=str, default=str(DEFAULT_MOT_ROOT), help="MOT17 images 根目录")
    parser.add_argument("--split", type=str, default="train", choices=["train", "test"], help="评测划分")
    parser.add_argument("--seq", nargs="+", help="只运行指定序列，例如 MOT17-02-FRCNN")
    parser.add_argument("--tracker", choices=["bytetrack", "botsort", "strongsort"], help="覆盖跟踪器类型")
    parser.add_argument("--tracker-name", type=str, default="yolov11_bytetrack", help="TrackEval 中的 tracker 名称")
    parser.add_argument("--model", type=str, help="覆盖检测模型权重")
    parser.add_argument("--conf", type=float, help="覆盖置信度阈值")
    parser.add_argument("--imgsz", type=int, help="覆盖输入尺寸")
    parser.add_argument("--output-root", type=str, default=str(DEFAULT_OUTPUT_ROOT), help="TrackEval 输出根目录")
    parser.add_argument("--show", action="store_true", help="显示可视化窗口")
    parser.add_argument("--no-show", action="store_true", help="不显示窗口")
    return parser.parse_args()


def load_config(config_path: Path) -> dict:
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_sequences(split_root: Path, selected_sequences: list[str] | None) -> list[Path]:
    if not split_root.exists():
        raise FileNotFoundError(f"MOT17 划分目录不存在: {split_root}")

    if selected_sequences:
        sequences = [split_root / name for name in selected_sequences]
    else:
        sequences = sorted(path for path in split_root.iterdir() if path.is_dir() and (path / "img1").exists())

    missing = [str(path) for path in sequences if not path.exists()]
    if missing:
        raise FileNotFoundError(f"以下 MOT17 序列不存在: {missing}")
    return sequences


def read_seqinfo(sequence_dir: Path) -> dict:
    parser = configparser.ConfigParser()
    parser.read(sequence_dir / "seqinfo.ini", encoding="utf-8")
    return {
        "frame_rate": parser.getint("Sequence", "frameRate", fallback=30),
        "seq_length": parser.getint("Sequence", "seqLength", fallback=0),
    }


def build_runtime_config(base_cfg: dict, args, sequence_dir: Path, tracker_output: Path) -> dict:
    cfg = yaml.safe_load(yaml.safe_dump(base_cfg, allow_unicode=True))

    cfg["source"]["type"] = "mot17"
    cfg["source"]["sequence_path"] = str(sequence_dir)
    cfg["visualizer"]["show"] = False if args.no_show else bool(args.show)
    cfg["visualizer"]["save_video"] = False

    if args.tracker:
        cfg["tracker"]["type"] = args.tracker
        cfg["tracker"]["config_file"] = f"trackers/{args.tracker}.yaml"
    if args.model:
        cfg["detector"]["model"] = args.model
    if args.conf is not None:
        cfg["detector"]["conf"] = args.conf
    if args.imgsz is not None:
        cfg["detector"]["imgsz"] = args.imgsz

    cfg.setdefault("export", {}).setdefault("mot", {})["enabled"] = True
    cfg["export"]["mot"]["output_path"] = str(tracker_output)
    cfg["export"]["mot"]["output_dir"] = str(tracker_output.parent)
    return cfg


def evaluate_with_trackeval(args, seq_info: dict[str, int]):
    try:
        trackeval = importlib.import_module("trackeval")
    except ImportError as exc:
        raise SystemExit(
            "未安装 trackeval，先执行: pip install git+https://github.com/JonathonLuiten/TrackEval.git"
        ) from exc

    eval_config = trackeval.Evaluator.get_default_eval_config()
    eval_config["USE_PARALLEL"] = False
    eval_config["DISPLAY_LESS_PROGRESS"] = False
    eval_config["PRINT_CONFIG"] = False

    dataset_config = trackeval.datasets.MotChallenge2DBox.get_default_dataset_config()
    dataset_config.update({
        "GT_FOLDER": args.mot_root,
        "TRACKERS_FOLDER": args.output_root,
        "TRACKERS_TO_EVAL": [args.tracker_name],
        "CLASSES_TO_EVAL": ["pedestrian"],
        "BENCHMARK": "MOT17",
        "SPLIT_TO_EVAL": args.split,
        "SEQ_INFO": seq_info,
        "GT_LOC_FORMAT": f"{{gt_folder}}/{args.split}/{{seq}}/gt/gt.txt",
        "SKIP_SPLIT_FOL": True,
        "PRINT_CONFIG": False,
    })

    evaluator = trackeval.Evaluator(eval_config)
    dataset_list = [trackeval.datasets.MotChallenge2DBox(dataset_config)]
    metrics_list = [
        trackeval.metrics.HOTA(),
        trackeval.metrics.CLEAR({"THRESHOLD": 0.5}),
        trackeval.metrics.Identity(),
    ]
    evaluator.evaluate(dataset_list, metrics_list)


def main():
    from tools.run_mot17 import run_mot17_sequence

    args = parse_args()
    args.config = str(Path(args.config).resolve())
    args.mot_root = str(Path(args.mot_root).resolve())
    args.output_root = str(Path(args.output_root).resolve())

    base_cfg = load_config(Path(args.config))
    split_root = Path(args.mot_root) / args.split
    output_root = Path(args.output_root)
    tracker_output_root = output_root / args.tracker_name / "data"
    tracker_output_root.mkdir(parents=True, exist_ok=True)

    sequences = get_sequences(split_root, args.seq)
    seq_info = {}

    for sequence_dir in sequences:
        info = read_seqinfo(sequence_dir)
        seq_info[sequence_dir.name] = info["seq_length"]
        tracker_output = tracker_output_root / f"{sequence_dir.name}.txt"
        runtime_cfg = build_runtime_config(base_cfg, args, sequence_dir, tracker_output)
        print(f"[MOT17] 开始推理: {sequence_dir.name}")
        run_mot17_sequence(
            sequence_path=sequence_dir,
            cfg=runtime_cfg,
            show=False if args.no_show else bool(args.show),
            save_video=False,
            mot_output=tracker_output,
        )

    if args.split != "train":
        print("[MOT17] test 划分通常无公开 GT，已完成结果导出，跳过 TrackEval")
        return

    print("[MOT17] 开始 TrackEval 评测")
    evaluate_with_trackeval(args, seq_info)


if __name__ == "__main__":
    main()