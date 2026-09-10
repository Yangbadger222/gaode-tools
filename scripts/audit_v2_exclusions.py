#!/usr/bin/env python3
"""Report ambiguous historical V2 exclusions without modifying annotations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from amap_tool.annotation_audit import audit_v2_exclusions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="Annotation JSON files or folders")
    args = parser.parse_args()
    files: set[Path] = set()
    for value in args.paths:
        path = Path(value).expanduser()
        if path.is_dir():
            files.update(candidate for candidate in path.rglob("*.json") if candidate.is_file())
        elif path.is_file():
            files.add(path)
    report = audit_v2_exclusions(sorted(files))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
