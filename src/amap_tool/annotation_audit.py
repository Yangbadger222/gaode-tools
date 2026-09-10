"""Read-only audits for schema-v2 annotation semantics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .annotation_schema import polyline_length, upgrade_document


def audit_v2_exclusions(paths: Iterable[str | Path]) -> dict:
    report = {
        "files_scanned": 0,
        "v2_files": 0,
        "total_excluded_from_task_edges": 0,
        "edges_with_local_e_spans": 0,
        "ambiguous_whole_edge_exclusions": 0,
        "ambiguous_edges": [],
        "errors": [],
    }
    for value in paths:
        path = Path(value)
        report["files_scanned"] += 1
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            report["errors"].append({"path": str(path), "error": str(exc)})
            continue
        if not isinstance(raw, dict):
            report["errors"].append({"path": str(path), "error": "annotation root must be a JSON object"})
            continue
        if not str(raw.get("schema_version", "1")).startswith("2") or not isinstance(raw.get("segments"), list):
            continue
        report["v2_files"] += 1
        document, _ = upgrade_document(raw)
        for segment in document.get("segments", []):
            if segment.get("excluded_from_task"):
                report["total_excluded_from_task_edges"] += 1
            task_spans = [
                span for span in segment.get("evidence_spans", []) if span.get("evidence") == "task_mismatch"
            ]
            if task_spans:
                report["edges_with_local_e_spans"] += 1
            if segment.get("legacy_exclusion_ambiguous"):
                report["ambiguous_whole_edge_exclusions"] += 1
                task_length = sum(float(span["end_s"]) - float(span["start_s"]) for span in task_spans)
                total = polyline_length(segment.get("points", []))
                report["ambiguous_edges"].append(
                    {
                        "path": str(path),
                        "edge_id": segment.get("edge_id", ""),
                        "task_mismatch_coverage": segment.get("legacy_exclusion_coverage", "partial"),
                        "task_mismatch_fraction": 0.0 if total <= 1e-9 else min(1.0, task_length / total),
                    }
                )
    return report
