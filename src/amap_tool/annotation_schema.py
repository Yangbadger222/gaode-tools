"""Annotation schema v2 and arc-length evidence span utilities.

The source RGB is deliberately outside this module.  All coordinates are native
image/canvas pixels and evidence is stored along the polyline's arc length.
"""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Iterable, Sequence

Point = Sequence[float]

SCHEMA_VERSION = 2
EVIDENCE_BY_KEY = {
    "A": "clear_visual",
    "B": "weak_visual",
    "C": "context_only",
    "D": "draft_misalignment",
    "E": "task_mismatch",
    "U": "uncertain",
}
EVIDENCE_LABELS = {
    "clear_visual": "Clear",
    "weak_visual": "Weak Visual",
    "context_only": "Context Only",
    "draft_misalignment": "Draft Misaligned",
    "task_mismatch": "Exclude / Task Mismatch",
    "uncertain": "Unsure",
}
EVIDENCE_COLORS = {
    "clear_visual": "#5f8f68",
    "weak_visual": "#c28b34",
    "context_only": "#81758f",
    "draft_misalignment": "#b8514f",
    "task_mismatch": "#777775",
    "uncertain": "#607d8b",
}


def polyline_length(points: Iterable[Point]) -> float:
    pts = list(points)
    return sum(
        math.hypot(float(b[0]) - float(a[0]), float(b[1]) - float(a[1]))
        for a, b in zip(pts, pts[1:])
    )


def project_onto_polyline(point: Point, points: Iterable[Point]) -> dict | None:
    """Project *point* to a polyline and return its native arc-length position."""
    pts = list(points)
    if len(pts) < 2:
        return None
    px, py = float(point[0]), float(point[1])
    walked = 0.0
    best = None
    for index, (a, b) in enumerate(zip(pts, pts[1:])):
        ax, ay = float(a[0]), float(a[1])
        bx, by = float(b[0]), float(b[1])
        dx, dy = bx - ax, by - ay
        segment_length = math.hypot(dx, dy)
        if segment_length <= 1e-12:
            t = 0.0
            qx, qy = ax, ay
        else:
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (segment_length**2)))
            qx, qy = ax + t * dx, ay + t * dy
        candidate = {
            "s": walked + t * segment_length,
            "point": [qx, qy],
            "distance": math.hypot(px - qx, py - qy),
            "segment_index": index,
            "t": t,
        }
        if best is None or candidate["distance"] < best["distance"]:
            best = candidate
        walked += segment_length
    return best


def point_at_s(points: Iterable[Point], s: float) -> list[float]:
    pts = [[float(p[0]), float(p[1])] for p in points]
    if not pts:
        raise ValueError("polyline has no points")
    if len(pts) == 1:
        return pts[0]
    remaining = max(0.0, min(float(s), polyline_length(pts)))
    for a, b in zip(pts, pts[1:]):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        if remaining <= length or length <= 1e-12:
            t = 0.0 if length <= 1e-12 else remaining / length
            return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
        remaining -= length
    return pts[-1]


def polyline_slice(points: Iterable[Point], start_s: float, end_s: float) -> list[list[float]]:
    """Return the continuous piece between two arc-length coordinates."""
    pts = [[float(p[0]), float(p[1])] for p in points]
    if len(pts) < 2:
        return pts
    total = polyline_length(pts)
    start, end = sorted((max(0.0, min(float(start_s), total)), max(0.0, min(float(end_s), total))))
    if end - start <= 1e-9:
        return [point_at_s(pts, start)]
    output = [point_at_s(pts, start)]
    walked = 0.0
    for point, next_point in zip(pts, pts[1:]):
        length = math.hypot(next_point[0] - point[0], next_point[1] - point[1])
        walked += length
        if start + 1e-9 < walked < end - 1e-9:
            output.append(list(next_point))
    output.append(point_at_s(pts, end))
    deduped = [output[0]]
    for point in output[1:]:
        if math.hypot(point[0] - deduped[-1][0], point[1] - deduped[-1][1]) > 1e-9:
            deduped.append(point)
    return deduped


def _normalise_span(span: dict, total: float) -> dict | None:
    start, end = sorted((float(span.get("start_s", 0.0)), float(span.get("end_s", 0.0))))
    start, end = max(0.0, start), min(total, end)
    if end - start <= 1e-6:
        return None
    result = copy.deepcopy(span)
    result["start_s"], result["end_s"] = start, end
    result.setdefault("review_confidence", "medium")
    result.setdefault("note", "")
    return result


def normalise_spans(spans: Iterable[dict], total: float) -> list[dict]:
    cleaned = [candidate for span in spans if (candidate := _normalise_span(span, total))]
    cleaned.sort(key=lambda span: (span["start_s"], span["end_s"]))
    merged: list[dict] = []
    for span in cleaned:
        if (
            merged
            and abs(merged[-1]["end_s"] - span["start_s"]) <= 1e-6
            and all(merged[-1].get(key) == span.get(key) for key in ("evidence", "review_confidence", "note"))
        ):
            merged[-1]["end_s"] = span["end_s"]
        else:
            merged.append(span)
    return merged


def assign_evidence_span(
    segment: dict,
    start_s: float,
    end_s: float,
    evidence: str,
    *,
    review_confidence: str = "medium",
    note: str = "",
) -> None:
    """Replace evidence over one local interval without splitting visible geometry."""
    if evidence not in EVIDENCE_LABELS:
        raise ValueError(f"unknown evidence class: {evidence}")
    total = polyline_length(segment.get("points", []))
    start, end = sorted((max(0.0, min(float(start_s), total)), max(0.0, min(float(end_s), total))))
    if end - start <= 1e-6:
        raise ValueError("evidence span must have a positive length")
    replacement = {
        "start_s": start,
        "end_s": end,
        "evidence": evidence,
        "review_confidence": review_confidence,
        "note": note,
    }
    remaining = []
    for old in normalise_spans(segment.get("evidence_spans", []), total):
        if old["end_s"] <= start or old["start_s"] >= end:
            remaining.append(old)
            continue
        if old["start_s"] < start:
            left = copy.deepcopy(old)
            left["end_s"] = start
            remaining.append(left)
        if old["end_s"] > end:
            right = copy.deepcopy(old)
            right["start_s"] = end
            remaining.append(right)
    segment["evidence_spans"] = normalise_spans([*remaining, replacement], total)
    if evidence == "draft_misalignment":
        segment["geometry_review_required"] = True
        segment["geometry_fixed"] = False
    if evidence == "task_mismatch":
        segment["excluded_from_task"] = True
    update_segment_review_status(segment)


def remap_evidence_spans(segment: dict, old_length: float) -> None:
    """Keep span positions proportional after inserting or moving a control point."""
    new_length = polyline_length(segment.get("points", []))
    if old_length <= 1e-9 or new_length <= 1e-9:
        segment["evidence_spans"] = []
        segment["review_status"] = "unreviewed"
        return
    scale = new_length / old_length
    remapped = []
    for span in segment.get("evidence_spans", []):
        candidate = copy.deepcopy(span)
        candidate["start_s"] = float(candidate.get("start_s", 0.0)) * scale
        candidate["end_s"] = float(candidate.get("end_s", 0.0)) * scale
        remapped.append(candidate)
    segment["evidence_spans"] = normalise_spans(remapped, new_length)
    update_segment_review_status(segment)


def evidence_coverage(segment: dict) -> dict:
    total = polyline_length(segment.get("points", []))
    by_class = {key: 0.0 for key in EVIDENCE_LABELS}
    reviewed = 0.0
    for span in normalise_spans(segment.get("evidence_spans", []), total):
        length = span["end_s"] - span["start_s"]
        by_class[span.get("evidence", "uncertain")] = by_class.get(span.get("evidence", "uncertain"), 0.0) + length
        reviewed += length
    return {
        "total_px": total,
        "reviewed_px": min(total, reviewed),
        "unreviewed_px": max(0.0, total - reviewed),
        "percent": 100.0 if total <= 1e-9 else min(100.0, reviewed / total * 100.0),
        "by_class_px": by_class,
    }


def update_segment_review_status(segment: dict) -> None:
    coverage = evidence_coverage(segment)
    segment["review_status"] = "reviewed" if coverage["unreviewed_px"] <= 0.5 else "unreviewed"


def new_segment(edge_id: str, points: Iterable[Point], path_type: str = "pedestrian_path", source: str = "manual") -> dict:
    return {
        "edge_id": edge_id,
        "path_type": path_type,
        "points": [[float(p[0]), float(p[1])] for p in points],
        "source": source,
        "evidence_spans": [],
        "excluded_from_task": False,
        "geometry_review_required": False,
        "geometry_fixed": False,
        "review_status": "unreviewed",
    }


def empty_document(image_id: str, source_path: str, width: int, height: int, *, region: str = "") -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "image_id": image_id,
        "image": {
            "source_path": source_path,
            "width": int(width),
            "height": int(height),
            "region": region,
        },
        "annotation_status": "unreviewed",
        "segments": [],
        "ignore_regions": [],
    }


def upgrade_document(
    data: dict,
    *,
    image_id: str | None = None,
    source_path: str = "",
    width: int = 0,
    height: int = 0,
) -> tuple[dict, bool]:
    """Return a canonical v2 document and whether the source was legacy."""
    original = copy.deepcopy(data)
    source_version = str(original.get("schema_version", "1"))
    is_v2 = source_version.startswith("2") and isinstance(original.get("segments"), list)
    if is_v2:
        document = original
        document["schema_version"] = SCHEMA_VERSION
        document.setdefault("annotation_status", "unreviewed")
        document.setdefault("ignore_regions", [])
    else:
        region_data = original.get("region", {})
        inferred_image_id = image_id or original.get("image_id") or region_data.get("region_id") or Path(source_path).stem
        document = empty_document(inferred_image_id, source_path, width, height, region=region_data.get("region_id", ""))
        document["source_schema_version"] = source_version
        if region_data:
            document["region"] = copy.deepcopy(region_data)
        if original.get("nodes") is not None:
            document["legacy_nodes"] = copy.deepcopy(original.get("nodes", []))
        document["ignore_regions"] = copy.deepcopy(original.get("ignore_regions", []))
        draft = bool(
            region_data.get("draft_source")
            or region_data.get("draft_warning")
            or str(original.get("annotation_status", "")).lower() in {"draft", "draft_ready"}
        )
        legacy_segments = original.get("edges")
        if not isinstance(legacy_segments, list) or not legacy_segments:
            legacy_segments = original.get("segments", [])
        used_ids: set[str] = set()
        for position, edge in enumerate(legacy_segments):
            base_id = str(edge.get("id") or edge.get("edge_id") or f"e{position + 1:06d}")
            edge_id = base_id
            if edge_id in used_ids:
                suffix = edge.get("segment_index", position)
                edge_id = f"{base_id}_s{suffix}"
            used_ids.add(edge_id)
            segment = new_segment(
                edge_id,
                edge.get("polyline", edge.get("points", [])),
                edge.get("path_type", "pedestrian_path"),
                "draft" if draft else "manual",
            )
            for key in ("start_node", "end_node", "visibility", "confidence", "verification_source"):
                if key in edge:
                    segment[key] = copy.deepcopy(edge[key])
            document["segments"].append(segment)
    document.setdefault("image_id", image_id or Path(source_path).stem)
    image = document.setdefault("image", {})
    image.setdefault("source_path", source_path)
    image.setdefault("width", int(width))
    image.setdefault("height", int(height))
    image.setdefault("region", "")
    for index, segment in enumerate(document.setdefault("segments", []), start=1):
        if "points" not in segment and "polyline" in segment:
            segment["points"] = segment.pop("polyline")
        segment.setdefault("edge_id", segment.pop("id", f"e{index:06d}"))
        segment.setdefault("path_type", "pedestrian_path")
        segment.setdefault("source", "manual")
        segment.setdefault("evidence_spans", [])
        segment.setdefault("excluded_from_task", False)
        segment.setdefault("geometry_review_required", False)
        segment.setdefault("geometry_fixed", False)
        segment.setdefault("review_status", "unreviewed")
        segment["points"] = [[float(p[0]), float(p[1])] for p in segment.get("points", [])]
        segment["evidence_spans"] = normalise_spans(segment["evidence_spans"], polyline_length(segment["points"]))
        update_segment_review_status(segment)
    return document, not is_v2


def update_document_status(document: dict) -> None:
    segments = document.get("segments", [])
    if segments:
        document["annotation_status"] = (
            "reviewed" if all(segment.get("review_status") == "reviewed" for segment in segments) else "unreviewed"
        )
    elif document.get("annotation_status") != "reviewed":
        document["annotation_status"] = "unreviewed"


def _unreviewed_intervals(total: float, spans: Iterable[dict]) -> list[tuple[float, float]]:
    cursor = 0.0
    intervals = []
    for span in normalise_spans(spans, total):
        if span["start_s"] > cursor + 1e-6:
            intervals.append((cursor, span["start_s"]))
        cursor = max(cursor, span["end_s"])
    if cursor < total - 1e-6:
        intervals.append((cursor, total))
    return intervals


def export_derived(document: dict, *, trusted_only: bool = False) -> dict:
    """Build a non-destructive training/evaluation export from schema v2."""
    output = {
        "schema_version": SCHEMA_VERSION,
        "source_image_id": document.get("image_id", ""),
        "export_type": "trusted_evaluation" if trusted_only else "training",
        "valid_positive_polyline": [],
        "ignore_spans": [],
        "excluded_edges": [],
        "warning": "Unlabelled image area is not reliable background ground truth.",
    }
    for segment in document.get("segments", []):
        edge_id = segment.get("edge_id", "")
        points = segment.get("points", [])
        total = polyline_length(points)
        if segment.get("excluded_from_task"):
            output["excluded_edges"].append({"edge_id": edge_id, "reason": "task_mismatch", "points": copy.deepcopy(points)})
            continue
        for span in normalise_spans(segment.get("evidence_spans", []), total):
            evidence = span.get("evidence")
            record = {
                "edge_id": edge_id,
                "path_type": segment.get("path_type", "pedestrian_path"),
                "evidence": evidence,
                "start_s": span["start_s"],
                "end_s": span["end_s"],
                "points": polyline_slice(points, span["start_s"], span["end_s"]),
            }
            if evidence in ("clear_visual", "weak_visual"):
                output["valid_positive_polyline"].append(record)
            elif evidence == "task_mismatch":
                output["excluded_edges"].append(record)
            elif not trusted_only:
                output["ignore_spans"].append(record)
        if not trusted_only:
            for start, end in _unreviewed_intervals(total, segment.get("evidence_spans", [])):
                output["ignore_spans"].append(
                    {
                        "edge_id": edge_id,
                        "path_type": segment.get("path_type", "pedestrian_path"),
                        "evidence": "unreviewed",
                        "start_s": start,
                        "end_s": end,
                        "points": polyline_slice(points, start, end),
                    }
                )
    return output
