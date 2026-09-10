#!/usr/bin/env python3
"""Launch Annotation Tool V2 with a welcome page, folder, or legacy region."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amap_tool.qt_runtime import prepare_qt_runtime

prepare_qt_runtime()

from amap_tool.annotator import AnnotatorWindow, APP_TITLE
from PySide6.QtWidgets import QApplication


def main() -> int:
    parser = argparse.ArgumentParser(description="AMap Path Annotator V2")
    parser.add_argument("--folder", help="optional image folder to open immediately")
    parser.add_argument("--region", help="optional legacy region.json")
    parser.add_argument("--annotation", help="legacy annotation JSON paired with --region")
    parser.add_argument("--language", choices=("zh", "en"), help="optional UI language override")
    args = parser.parse_args()
    if args.folder and args.region:
        parser.error("choose either --folder or --region")

    app = QApplication.instance() or QApplication([])
    app.setApplicationName(APP_TITLE)
    app.setOrganizationName("gaode-tools")
    window = AnnotatorWindow(args.region, args.annotation) if args.region else AnnotatorWindow()
    if args.language:
        window.set_language("zh_CN" if args.language == "zh" else "en_US")
    window.resize(1440, 900)
    window.show()
    if args.folder:
        window.open_folder(args.folder)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
