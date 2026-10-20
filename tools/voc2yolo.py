"""
VOC XML 格式 → YOLO TXT 格式转换脚本
将 B_行人数据集_VOC格式 转换并合并到 merged_dataset

用法：
    python tools/voc2yolo.py
"""
import os
import shutil
import random
import xml.etree.ElementTree as ET
from pathlib import Path


# ========== 配置 ==========
VOC_IMG_DIR   = Path("B_行人数据集_VOC格式/JPEGImages")
VOC_ANN_DIR   = Path("B_行人数据集_VOC格式/Annotations")
OUT_DIR       = Path("data/merged_dataset")
TRAIN_RATIO   = 0.8
RANDOM_SEED   = 42
CLASS_NAMES   = ["person"]   # VOC 中对应的类别名
# ==========================


def voc_bbox_to_yolo(size, bbox):
    """将 VOC 绝对坐标转为 YOLO 归一化格式"""
    dw = 1.0 / size[0]
    dh = 1.0 / size[1]
    x = (bbox[0] + bbox[2]) / 2.0 * dw
    y = (bbox[1] + bbox[3]) / 2.0 * dh
    w = (bbox[2] - bbox[0]) * dw
    h = (bbox[3] - bbox[1]) * dh
    return x, y, w, h


def convert_annotation(xml_path: Path, size_hint=None):
    """解析单个 XML 文件，返回 (img_size, yolo_lines)"""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    size_node = root.find("size")
    w = int(size_node.find("width").text)
    h = int(size_node.find("height").text)

    lines = []
    for obj in root.findall("object"):
        cls_name = obj.find("name").text.strip()
        if cls_name not in CLASS_NAMES:
            continue
        cls_id = CLASS_NAMES.index(cls_name)
        bndbox = obj.find("bndbox")
        xmin = float(bndbox.find("xmin").text)
        ymin = float(bndbox.find("ymin").text)
        xmax = float(bndbox.find("xmax").text)
        ymax = float(bndbox.find("ymax").text)
        x, y, bw, bh = voc_bbox_to_yolo((w, h), (xmin, ymin, xmax, ymax))
        lines.append(f"{cls_id} {x:.6f} {y:.6f} {bw:.6f} {bh:.6f}")
    return (w, h), lines


def main():
    random.seed(RANDOM_SEED)

    # 创建输出目录
    for split in ("train", "valid"):
        (OUT_DIR / split / "images").mkdir(parents=True, exist_ok=True)
        (OUT_DIR / split / "labels").mkdir(parents=True, exist_ok=True)

    # ── Step 1: 复制 A 集（已是 YOLO 格式）──
    print("=== 复制 A 集（YOLO 格式）===")
    a_train_imgs = Path("A_行人数据集_YOLO格式/train/images")
    a_train_lbls = Path("A_行人数据集_YOLO格式/train/labels")
    a_valid_imgs = Path("A_行人数据集_YOLO格式/valid/images")
    a_valid_lbls = Path("A_行人数据集_YOLO格式/valid/labels")

    for img in a_train_imgs.glob("*"):
        shutil.copy2(img, OUT_DIR / "train" / "images" / img.name)
    for lbl in a_train_lbls.glob("*.txt"):
        shutil.copy2(lbl, OUT_DIR / "train" / "labels" / lbl.name)
    for img in a_valid_imgs.glob("*"):
        shutil.copy2(img, OUT_DIR / "valid" / "images" / img.name)
    for lbl in a_valid_lbls.glob("*.txt"):
        shutil.copy2(lbl, OUT_DIR / "valid" / "labels" / lbl.name)
    print(f"  A 集 train: {len(list(a_train_imgs.glob('*')))} 张")
    print(f"  A 集 valid: {len(list(a_valid_imgs.glob('*')))} 张")

    # ── Step 2: 转换 B 集（VOC → YOLO）并划分 ──
    print("\n=== 转换 B 集（VOC → YOLO）===")
    xml_files = sorted(VOC_ANN_DIR.glob("*.xml"))
    random.shuffle(xml_files)
    split_idx = int(len(xml_files) * TRAIN_RATIO)
    b_train_xmls = xml_files[:split_idx]
    b_valid_xmls = xml_files[split_idx:]

    converted, skipped = 0, 0
    for split_name, xml_list in [("train", b_train_xmls), ("valid", b_valid_xmls)]:
        for xml_path in xml_list:
            stem = xml_path.stem

            # 查找对应图片（支持 jpg/jpeg/png）
            img_path = None
            for ext in (".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"):
                candidate = VOC_IMG_DIR / (stem + ext)
                if candidate.exists():
                    img_path = candidate
                    break

            if img_path is None:
                skipped += 1
                continue

            # 解析标注
            try:
                _, yolo_lines = convert_annotation(xml_path)
            except Exception as e:
                print(f"  [警告] 解析失败 {xml_path.name}: {e}")
                skipped += 1
                continue

            if not yolo_lines:
                skipped += 1
                continue

            # 写入目标目录（加 b_ 前缀避免与 A 集重名）
            out_name = "b_" + stem
            shutil.copy2(img_path, OUT_DIR / split_name / "images" / (out_name + img_path.suffix))
            lbl_out = OUT_DIR / split_name / "labels" / (out_name + ".txt")
            lbl_out.write_text("\n".join(yolo_lines), encoding="utf-8")
            converted += 1

    print(f"  B 集转换成功: {converted} 张，跳过: {skipped} 张")
    print(f"  B 集 train: {len(b_train_xmls)} 张，valid: {len(b_valid_xmls)} 张")

    # ── Step 3: 生成 dataset.yaml ──
    total_train = len(list((OUT_DIR / "train" / "images").glob("*")))
    total_valid = len(list((OUT_DIR / "valid" / "images").glob("*")))

    yaml_content = f"""# 合并数据集（A集 + B集）
path: {OUT_DIR.resolve().as_posix()}
train: train/images
val: valid/images

nc: 1
names:
  - person

# 数据集统计
# train: {total_train} 张
# valid: {total_valid} 张
"""
    (OUT_DIR / "dataset.yaml").write_text(yaml_content, encoding="utf-8")

    print(f"\n=== 完成 ===")
    print(f"  合并后 train: {total_train} 张")
    print(f"  合并后 valid: {total_valid} 张")
    print(f"  dataset.yaml 已写入: {OUT_DIR / 'dataset.yaml'}")


if __name__ == "__main__":
    main()
