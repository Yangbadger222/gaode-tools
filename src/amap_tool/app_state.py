"""Small JSON-backed recent-folder, session and crash-recovery store."""

from __future__ import annotations

import copy
import platform
from datetime import datetime, timezone
from pathlib import Path

from .annotation_io import atomic_write_json


def default_state_path() -> Path:
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "AMapAnnotationTool" / "state.json"
    if platform.system() == "Windows":
        return Path.home() / "AppData" / "Local" / "AMapAnnotationTool" / "state.json"
    return Path.home() / ".local" / "state" / "amap-annotation-tool" / "state.json"


class AppStateStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else default_state_path()
        self.data = {"version": 1, "recent_folders": [], "sessions": {}, "recovery": None, "onboarding_seen": False}
        if self.path.exists():
            try:
                import json

                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.data.update(loaded)
            except (OSError, ValueError):
                pass

    def save(self) -> None:
        atomic_write_json(self.data, self.path, backup=False)

    def add_recent(self, folder: str | Path) -> None:
        resolved = str(Path(folder).expanduser().resolve())
        existing = [item for item in self.data.get("recent_folders", []) if item.get("path") != resolved]
        existing.insert(0, {"path": resolved, "last_opened": datetime.now(timezone.utc).isoformat()})
        self.data["recent_folders"] = existing[:10]
        self.save()

    def remove_recent(self, folder: str | Path) -> None:
        resolved = str(Path(folder).expanduser().resolve())
        self.data["recent_folders"] = [item for item in self.data.get("recent_folders", []) if item.get("path") != resolved]
        self.save()

    def recent_folders(self) -> list[dict]:
        return copy.deepcopy(self.data.get("recent_folders", []))

    def save_session(self, folder: str | Path, session: dict) -> None:
        key = str(Path(folder).expanduser().resolve())
        self.data.setdefault("sessions", {})[key] = copy.deepcopy(session)
        self.save()

    def session(self, folder: str | Path) -> dict:
        key = str(Path(folder).expanduser().resolve())
        return copy.deepcopy(self.data.get("sessions", {}).get(key, {}))

    def save_recovery(self, recovery: dict) -> None:
        self.data["recovery"] = copy.deepcopy(recovery)
        self.save()

    def recovery(self) -> dict | None:
        value = self.data.get("recovery")
        return copy.deepcopy(value) if isinstance(value, dict) else None

    def clear_recovery(self) -> None:
        if self.data.get("recovery") is not None:
            self.data["recovery"] = None
            self.save()

    def onboarding_seen(self) -> bool:
        return bool(self.data.get("onboarding_seen", False))

    def set_onboarding_seen(self) -> None:
        self.data["onboarding_seen"] = True
        self.save()
