# Windows 10/11 x64 validation

1. Install Python 3.12 x64.
2. Clone/copy this repository and open PowerShell in it.
3. Run `py -3.12 -m venv .venv`.
4. Activate with `.\.venv\Scripts\Activate.ps1` and install `pip install -r requirements-dev.txt`.
5. Copy `.env.example` to `.env` and configure `AMAP_JS_API_KEY`.
6. Run `python scripts\diagnose_environment.py`.
7. Run `pytest -q`.
8. Run a 3×3 `capture_region.py` collection.
9. Interrupt once with Ctrl+C and rerun with `--resume`.
10. Run `check_region.py` and require 0 missing/invalid/wrong-size tiles and fixed overlap PASS.
11. Run `make_preview.py` and inspect both previews.
12. Double-click `scripts\run_annotator_windows.cmd`, then also test `powershell -File scripts\run_annotator.ps1`.
13. Switch between 中文 and English; close and reopen to verify the choice is remembered.
14. Hover over Draw for 3 seconds and verify the delayed explanation appears, then disappears after moving away.
15. Copy a macOS region to Windows and open it with `python scripts\launch_annotator.py --region ...`.
16. Test zoom, pan, draw, finish, select, attributes, control points, split, merge, ignore, undo/redo, save and reopen.
17. Open Image Guide and verify its step changes from an empty image to an evidence-complete image.
18. Copy the Windows-modified annotation back to macOS and verify IDs, coordinates and attributes.
