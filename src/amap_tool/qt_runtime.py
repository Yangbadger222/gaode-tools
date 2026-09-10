"""Prepare Qt's platform plugin path before PySide6 imports the GUI stack."""

from __future__ import annotations

import importlib.util
import os
import platform
import stat
from pathlib import Path


def prepare_qt_runtime() -> Path | None:
    spec = importlib.util.find_spec("PySide6")
    if spec is None or spec.origin is None:
        return None
    plugin_root = Path(spec.origin).resolve().parent / "Qt" / "plugins"
    platforms = plugin_root / "platforms"
    if platforms.exists():
        os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(platforms))
        if platform.system() == "Darwin" and hasattr(os, "chflags"):
            # Finder/quarantine metadata has repeatedly marked more than the
            # platform dylib itself hidden.  Qt rejects the platform plugin if
            # one of its sibling plugin directories is hidden, so clear the
            # user flag for this venv-local plugin tree only.
            for path in [plugin_root, *plugin_root.rglob("*")]:
                try:
                    os.chflags(path, path.stat().st_flags & ~stat.UF_HIDDEN)
                except OSError:
                    # A read-only environment can still work if Qt finds the plugin.
                    pass
    return plugin_root if plugin_root.exists() else None
