"""Safe JSON persistence helpers used by the annotation editor."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path


class AnnotationWriteError(RuntimeError):
    pass


def atomic_write_json(data: dict, path: str | Path, *, backup: bool = True) -> Path:
    destination = Path(path)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not os.access(destination.parent, os.W_OK):
            raise PermissionError(f"output directory is not writable: {destination.parent}")
        payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.stem}-",
            suffix=".tmp",
            dir=destination.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            json.loads(temporary.read_text(encoding="utf-8"))
            if backup and destination.exists():
                shutil.copy2(destination, destination.with_suffix(destination.suffix + ".bak"))
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AnnotationWriteError(str(exc)) from exc
    return destination
