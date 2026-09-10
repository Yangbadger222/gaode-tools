#!/usr/bin/env python3
"""Write schema-v2 copies of legacy annotation JSON without touching sources."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amap_tool.annotation_io import AnnotationWriteError, atomic_write_json
from amap_tool.annotation_schema import upgrade_document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="legacy JSON file or folder")
    parser.add_argument("--out-dir", type=Path, required=True, help="new output folder; source files are never overwritten")
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.out_dir.resolve()
    files = [source] if source.is_file() else sorted(source.rglob("*.json"))
    if not files:
        parser.error("no JSON files found")
    if source.is_dir() and (output == source or source in output.parents):
        parser.error("--out-dir must be separate from the source")

    written = skipped = 0
    for path in files:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            relative = Path(path.name) if source.is_file() else path.relative_to(source)
            document, was_legacy = upgrade_document(raw, image_id=path.stem)
            if not was_legacy:
                skipped += 1
                continue
            destination = output / relative
            if destination.exists():
                print(f"SKIP exists: {destination}")
                skipped += 1
                continue
            atomic_write_json(document, destination, backup=False)
            print(f"WROTE {destination}")
            written += 1
        except (OSError, ValueError, TypeError, AnnotationWriteError) as exc:
            print(f"SKIP invalid {path}: {exc}", file=sys.stderr)
            skipped += 1
    print(f"Done: {written} written, {skipped} skipped; sources unchanged")
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
