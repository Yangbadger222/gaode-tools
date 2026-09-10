#!/usr/bin/env python3
"""Prepare clean, per-annotator RGB folders from the 4-person assignment CSV.

The default mode creates hard links, so the package looks like an independent
folder without duplicating the large RGB files. No existing annotations are
copied or changed.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
from pathlib import Path


IMAGE_PATTERN = re.compile(r"_(r\d+_c\d+_z\d+)\.png$", re.IGNORECASE)


def link_or_copy(source: Path, destination: Path, mode: str) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if mode == "copy":
        shutil.copy2(source, destination)
        return "copy"
    try:
        os.link(source, destination)
        return "hardlink"
    except OSError:
        shutil.copy2(source, destination)
        return "copy-fallback"


def read_assignments(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def site_images(region_root: Path, site_id: str) -> list[Path]:
    site_root = region_root / site_id
    return sorted(
        (
            path
            for path in site_root.glob("*.png")
            if IMAGE_PATTERN.search(path.name)
        ),
        key=lambda path: (IMAGE_PATTERN.search(path.name).group(1), path.name),
    )


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def prepare(source_root: Path, output_root: Path, mode: str, overwrite: bool) -> dict:
    progress_path = source_root / "progress" / "progress_4_people.csv"
    region_root = source_root / "regions"
    if not progress_path.exists():
        raise FileNotFoundError(f"assignment CSV not found: {progress_path}")
    if not region_root.exists():
        raise FileNotFoundError(f"regions folder not found: {region_root}")
    if output_root.exists() and any(output_root.iterdir()) and not overwrite:
        raise FileExistsError(f"output folder is not empty: {output_root}; use --overwrite explicitly")
    if overwrite and output_root.exists():
        # Only remove the exact generated package requested by this command.
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    assignments = [row for row in read_assignments(progress_path) if row.get("annotator_id") in {"A", "B", "C", "D"}]
    assignments.sort(key=lambda row: (row["annotator_id"], int(row.get("order", 0))))
    rows: list[dict[str, str]] = []
    summary: list[dict[str, str]] = []
    for row in assignments:
        annotator = row["annotator_id"]
        site_id = row["site_id"]
        images = site_images(region_root, site_id)
        expected = int(row.get("image_count") or 0)
        if len(images) != expected:
            raise ValueError(f"{annotator}/{site_id}: assignment says {expected} images, found {len(images)}")
        person_root = output_root / annotator
        for image in images:
            destination = person_root / "rgb" / site_id / image.name
            link_mode = link_or_copy(image, destination, mode)
            image_id = image.stem
            rows.append(
                {
                    "annotator": annotator,
                    "order": row["order"],
                    "site_id": site_id,
                    "site_name_zh": row.get("site_name_zh", ""),
                    "image_id": image_id,
                    "source_file": image.relative_to(source_root).as_posix(),
                    "reannotation_file": destination.relative_to(output_root).as_posix(),
                    "link_mode": link_mode,
                }
            )
        summary.append(
            {
                "annotator": annotator,
                "site_id": site_id,
                "site_name_zh": row.get("site_name_zh", ""),
                "image_count": str(len(images)),
                "folder": (person_root / "rgb").relative_to(output_root).as_posix(),
            }
        )

    fields = ["annotator", "order", "site_id", "site_name_zh", "image_id", "source_file", "reannotation_file", "link_mode"]
    with (output_root / "manifest_all.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary_fields = ["annotator", "site_id", "site_name_zh", "image_count", "folder"]
    with (output_root / "assignment_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=summary_fields)
        writer.writeheader()
        writer.writerows(summary)

    for annotator in "ABCD":
        person_rows = [item for item in rows if item["annotator"] == annotator]
        sites = [item for item in summary if item["annotator"] == annotator]
        with (output_root / annotator / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(person_rows)
        site_lines = "\n".join(f"- `{item['site_id']}`：{item['site_name_zh']}（{item['image_count']} 张）" for item in sites)
        write_text(
            output_root / annotator / "README.md",
            f"""# {annotator} 重新标注包\n\n本文件夹只包含该标注员重新标注所需的原始 RGB 图片，共 **{len(person_rows)} 张**。\n\n## 启动\n\n在项目根目录运行：\n\n```bash\npython scripts/launch_annotator.py --folder outputs/suzhou_rgb_satellite_dataset_300/reannotation_4_people/{annotator}/rgb\n```\n\n## 本人负责区域\n\n{site_lines}\n\n## 注意\n\n- 这是干净的重新标注输入，不含旧的 annotation JSON。\n- 图片按区域分目录，程序会递归扫描。\n- 标注结果会写入本文件夹下的 `annotations_v2/`，不会修改 RGB。\n- 完成后把 `annotations_v2/` 与本 README 一起交回，不要改图片文件名。\n""",
        )

    total = len(rows)
    write_text(
        output_root / "README.md",
        f"""# 4 人重新标注图片包\n\n这是一份从现有 4 人分工表重新整理的干净 RGB 输入，共 **{total} 张**。每个人只打开自己的文件夹，避免把别人的图片或旧路线混在一起。\n\n## 文件夹结构\n\n```text\nreannotation_4_people/\n  A/rgb/区域名/*.png\n  B/rgb/区域名/*.png\n  C/rgb/区域名/*.png\n  D/rgb/区域名/*.png\n  assignment_summary.csv\n  manifest_all.csv\n```\n\n## 启动方式\n\n```bash\npython scripts/launch_annotator.py --folder outputs/suzhou_rgb_satellite_dataset_300/reannotation_4_people/A/rgb\n```\n\n把命令最后的 `A` 换成自己的字母。也可以直接把对应的 `A/rgb`、`B/rgb`、`C/rgb` 或 `D/rgb` 文件夹拖进标注器。\n\n## 数据安全\n\n- 文件夹中只有原始 RGB，不复制历史 annotation JSON，适合从零重新标注。\n- 默认使用硬链接，不额外复制图片内容，节省磁盘空间；图片本身仍可像普通 PNG 一样打开。\n- 原始数据位于 `annotation_workspace/regions/`，本次整理不会删除或修改它。\n- 每个人的图片数量和区域见 `assignment_summary.csv`。\n""",
    )
    return {"total": total, "summary": summary, "rows": rows, "output_root": output_root}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True, help="annotation_workspace folder")
    parser.add_argument("--output-root", type=Path, required=True, help="new reannotation package folder")
    parser.add_argument("--mode", choices=("hardlink", "copy"), default="hardlink")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    result = prepare(args.source_root.expanduser().resolve(), args.output_root.expanduser().resolve(), args.mode, args.overwrite)
    for annotator in "ABCD":
        count = sum(row["annotator"] == annotator for row in result["rows"])
        print(f"{annotator}: {count} images")
    print(f"TOTAL: {result['total']} images -> {result['output_root']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
