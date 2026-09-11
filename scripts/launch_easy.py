#!/usr/bin/env python3
"""Start the annotator without asking the user to activate a virtualenv.

This bootstrapper uses only Python's standard library until the project
environment is ready. It creates `.venv` when needed, installs the pinned
project requirements, and then replaces itself with the real Qt launcher.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = PROJECT_ROOT / ".venv"
REQUIREMENTS = PROJECT_ROOT / "requirements.txt"


def managed_python() -> Path:
    use_windowless = os.name == "nt" and (
        os.environ.get("AMAP_HIDE_CONSOLE") == "1"
        or Path(sys.executable).name.lower() == "pythonw.exe"
    )
    name = "pythonw.exe" if use_windowless else "python.exe" if os.name == "nt" else "python"
    return VENV_DIR / ("Scripts" if os.name == "nt" else "bin") / name


def base_python() -> list[str] | None:
    candidates: list[list[str]] = []
    if os.name == "nt":
        windows_py = Path(os.environ.get("WINDIR", r"C:\Windows")) / "py.exe"
        if windows_py.exists():
            candidates.append([str(windows_py), "-3.12"])
        if shutil.which("py"):
            candidates.append(["py", "-3.12"])
        if shutil.which("python3.12"):
            candidates.append(["python3.12"])
        if shutil.which("python"):
            candidates.append(["python"])
    else:
        names = (
            "python3.12",
            "/opt/homebrew/bin/python3.12",
            "/usr/local/bin/python3.12",
            "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12",
            "python3",
            "python",
        )
        for name in names:
            if shutil.which(name):
                candidates.append([name])
    for candidate in candidates:
        try:
            result = subprocess.run(
                [*candidate, "-c", "import sys; print(sys.version_info[:2])"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=True,
            )
        except (OSError, subprocess.CalledProcessError):
            continue
        if "(3, 12)" in result.stdout:
            return candidate
    return None


def run_hidden(command: list[str]) -> None:
    kwargs = {"cwd": PROJECT_ROOT, "check": True}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.run(command, **kwargs)


def show_error(message: str) -> None:
    if platform.system() == "Darwin" and shutil.which("osascript"):
        escaped = message.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        subprocess.run(
            ["osascript", "-e", f'display dialog "{escaped}" with title "AMap 路线标注工具" buttons {{"好"}} default button "好"'],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, "AMap Path Annotator", 0x10)
            return
        except (AttributeError, OSError):
            pass
    print(message, file=sys.stderr)


def ensure_environment() -> Path:
    python = managed_python()
    if python.exists():
        try:
            run_hidden([str(python), "-c", "import PySide6, PIL, yaml, dotenv"])
            return python
        except (OSError, subprocess.CalledProcessError):
            pass

    base = base_python()
    if base is None:
        raise RuntimeError(
            "没有找到 Python 3.12。请先安装 Python 3.12，然后再次双击启动器。"
            if os.name != "nt"
            else "找不到 Python 3.12。请先安装 Python 3.12 x64，然后再次双击启动器。"
        )
    if not VENV_DIR.exists():
        run_hidden([*base, "-m", "venv", str(VENV_DIR)])
    python = managed_python()
    if not python.exists():
        raise RuntimeError(f"项目环境创建失败：{python}")
    run_hidden([str(python), "-m", "pip", "install", "--upgrade", "pip"])
    run_hidden([str(python), "-m", "pip", "install", "-r", str(REQUIREMENTS)])
    return python


def main() -> int:
    try:
        python = ensure_environment()
        command = [str(python), str(PROJECT_ROOT / "scripts" / "launch_annotator.py"), *sys.argv[1:]]
        os.chdir(PROJECT_ROOT)
        os.execv(str(python), command)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        show_error(
            "启动标注器失败。\n\n"
            f"{exc}\n\n"
            "请确认已安装 Python 3.12，并检查网络后重试。"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
