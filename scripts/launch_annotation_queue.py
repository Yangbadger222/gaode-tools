#!/usr/bin/env python3
"""Open one person's assigned regions with visible previous/next navigation."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amap_tool.qt_runtime import prepare_qt_runtime

prepare_qt_runtime()

from amap_tool.annotator import launch


def main() -> int:
    parser = argparse.ArgumentParser(description="Open an assigned annotation queue")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--scheme", choices=("4_people", "3_people"), default="4_people")
    parser.add_argument("--annotator", choices=("A", "B", "C", "D"), required=True)
    parser.add_argument("--region", help="site_id to open first; defaults to the first unfinished assignment")
    args = parser.parse_args()

    progress = args.workspace / "progress" / f"progress_{args.scheme}.csv"
    with progress.open(encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row["annotator_id"] == args.annotator]
    rows.sort(key=lambda row: int(row["order"]))
    if not rows:
        parser.error(f"no assignments for annotator {args.annotator}")

    target = args.region or next((row["site_id"] for row in rows if row["status"] != "DONE"), rows[0]["site_id"])
    try:
        index = next(i for i, row in enumerate(rows) if row["site_id"] == target)
    except StopIteration:
        parser.error(f"{target!r} is not assigned to annotator {args.annotator}")

    queue = [(args.workspace / row["region_file"], args.workspace / row["annotation_file"]) for row in rows]
    launch(*queue[index], queue=queue, queue_index=index)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
