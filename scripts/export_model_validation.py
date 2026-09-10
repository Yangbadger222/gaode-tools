#!/usr/bin/env python3
"""Create per-tile RGB, overlay and pixel-label files for model validation."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amap_tool.annotation_export import tile_edge_parts
from amap_tool.paths import resolve_data_path


COLORS = {
    "vehicle_road": "#ff3b30",
    "pedestrian_path": "#ffd60a",
    "narrow_path": "#34c759",
    "service_path": "#0a84ff",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def materialize_rgb(source: Path, destination: Path, mode: str) -> None:
    if destination.exists():
        destination.unlink()
    if mode == "copy":
        shutil.copy2(source, destination)
        return
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def annotation_status(annotation: dict) -> str:
    region = annotation.get("region", {})
    return "draft" if region.get("draft_source") or region.get("draft_warning") else "human_reviewed"


def export_region(region_file: Path, annotation_file: Path, output_dir: Path, rgb_mode: str):
    region = read_json(region_file)
    annotation = read_json(annotation_file)
    status = annotation_status(annotation)
    width, height = int(region["tile_width"]), int(region["tile_height"])
    project_root = Path(__file__).resolve().parents[1]
    records = []

    for tile in region.get("tiles", []):
        source = resolve_data_path(tile["output_file"], region_file, project_root)
        if not source.exists():
            raise FileNotFoundError(f"RGB tile is missing: {source}")
        image_id = tile["image_id"]
        rgb_path = output_dir / "rgb" / f"{image_id}.png"
        overlay_path = output_dir / "overlays" / f"{image_id}.png"
        label_path = output_dir / "labels" / f"{image_id}.json"
        materialize_rgb(source, rgb_path, rgb_mode)

        tile_x = float(tile.get("global_x", tile["col"] * width * (1 - region["overlap"])))
        tile_y = float(tile.get("global_y", tile["row"] * height * (1 - region["overlap"])))
        parts = tile_edge_parts(annotation.get("edges", []), tile_x, tile_y, width, height)
        label = {
            "schema_version": "1.0",
            "image_id": image_id,
            "region_id": region["region_id"],
            "image_size": {"width": width, "height": height},
            "coordinate_system": "image_pixels_origin_top_left",
            "annotation_status": status,
            "source_annotation": str(annotation_file),
            "segments": parts,
        }
        write_json(label_path, label)

        with Image.open(source) as original:
            overlay = original.convert("RGB").copy()
        draw = ImageDraw.Draw(overlay)
        for part in parts:
            draw.line(part["points"], fill=COLORS.get(part["path_type"], "#ffffff"), width=4)
        overlay.save(overlay_path, format="PNG")

        records.append(
            {
                "image_id": image_id,
                "region_id": region["region_id"],
                "rgb_file": str(rgb_path.relative_to(output_dir)),
                "overlay_file": str(overlay_path.relative_to(output_dir)),
                "label_file": str(label_path.relative_to(output_dir)),
                "width": width,
                "height": height,
                "segment_count": len(parts),
                "annotation_status": status,
            }
        )
    return records


def write_readme(output_dir: Path, image_count: int, draft_count: int) -> None:
    text = f"""# 模型验证包

本目录包含 {image_count} 张 1024x1024 RGB 卫星图及其逐图像素坐标标注。

- `rgb/`：模型输入图。
- `labels/`：每张图的路线片段，坐标以左上角为 `(0, 0)`，单位为像素。
- `overlays/`：人工核对图。红色=机动车路，黄色=人行路径，绿色=窄路，蓝色=服务道路。
- `manifest.csv` / `manifest.jsonl`：文件对照表。

## 标签状态

`annotation_status=draft` 的标签来自 OSM 初始草稿，尚未逐条完成 RGB 人工复核。
本包有 {draft_count} 张 draft 图，只应用于模型流程、格式和可视化验证，不能当作最终训练真值或精度结论。
"""
    (output_dir / "README.md").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export one annotator's per-tile model-validation package")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--scheme", choices=("4_people", "3_people"), default="4_people")
    parser.add_argument("--annotator", choices=("A", "B", "C", "D"), required=True)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--rgb-mode", choices=("hardlink", "copy"), default="hardlink")
    parser.add_argument("--overwrite", action="store_true", help="replace an existing export directory")
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    output_dir = (args.out_dir or workspace / "model_validation" / args.scheme / args.annotator).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        if not args.overwrite:
            parser.error(f"output directory is not empty: {output_dir}; use --overwrite to replace it")
        shutil.rmtree(output_dir)
    for name in ("rgb", "overlays", "labels"):
        (output_dir / name).mkdir(parents=True, exist_ok=True)

    with (workspace / "progress" / f"progress_{args.scheme}.csv").open(encoding="utf-8") as handle:
        assignments = [row for row in csv.DictReader(handle) if row["annotator_id"] == args.annotator]
    assignments.sort(key=lambda row: int(row["order"]))
    if not assignments:
        parser.error(f"no assignments for annotator {args.annotator}")

    records = []
    for assignment in assignments:
        region_file = workspace / assignment["region_file"]
        annotation_file = workspace / assignment["annotation_file"]
        if not annotation_file.exists():
            print(f"SKIP {assignment['site_id']}: no annotation file")
            continue
        records.extend(export_region(region_file, annotation_file, output_dir, args.rgb_mode))
        print(f"EXPORTED {assignment['site_id']}")

    fieldnames = ["image_id", "region_id", "rgb_file", "overlay_file", "label_file", "width", "height", "segment_count", "annotation_status"]
    with (output_dir / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    with (output_dir / "manifest.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "model_validation_only",
        "scheme": args.scheme,
        "annotator": args.annotator,
        "rgb_mode": args.rgb_mode,
        "image_count": len(records),
        "draft_image_count": sum(record["annotation_status"] == "draft" for record in records),
    }
    write_json(output_dir / "package.json", manifest)
    write_readme(output_dir, manifest["image_count"], manifest["draft_image_count"])
    print(f"DONE {manifest['image_count']} images -> {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
