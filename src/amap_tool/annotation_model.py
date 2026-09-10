"""Undoable in-memory model for schema-v2 polyline annotations."""

from __future__ import annotations

import copy
import math
import re

from .annotation_schema import (
    VISIBILITY_ISSUES,
    assign_evidence_span,
    evidence_coverage,
    new_segment,
    point_at_s,
    polyline_length,
    polyline_slice,
    remap_evidence_spans,
    update_document_status,
    update_segment_review_status,
)


class AnnotationModel:
    def __init__(self, document: dict):
        self.data = copy.deepcopy(document)
        self.undo_stack: list[dict] = []
        self.redo_stack: list[dict] = []

    def snapshot(self) -> dict:
        return copy.deepcopy(self.data)

    def _commit(self, before: dict) -> None:
        self.undo_stack.append(before)
        self.redo_stack.clear()
        update_document_status(self.data)

    def restore(self, snapshot: dict) -> None:
        self.data = copy.deepcopy(snapshot)

    def undo_once(self) -> bool:
        if not self.undo_stack:
            return False
        self.redo_stack.append(self.snapshot())
        self.restore(self.undo_stack.pop())
        return True

    def redo_once(self) -> bool:
        if not self.redo_stack:
            return False
        self.undo_stack.append(self.snapshot())
        self.restore(self.redo_stack.pop())
        return True

    def segment(self, edge_id: str) -> dict:
        return next(segment for segment in self.data["segments"] if segment["edge_id"] == edge_id)

    def next_edge_id(self) -> str:
        values = []
        for segment in self.data.get("segments", []):
            match = re.fullmatch(r"e(\d+)", str(segment.get("edge_id", "")))
            if match:
                values.append(int(match.group(1)))
        return f"e{max(values, default=0) + 1:06d}"

    def add_segment(self, points, path_type: str = "pedestrian_path", source: str = "manual") -> str:
        if len(points) < 2:
            raise ValueError("a path needs at least two points")
        before = self.snapshot()
        edge_id = self.next_edge_id()
        self.data["segments"].append(new_segment(edge_id, points, path_type, source))
        self._commit(before)
        return edge_id

    def set_attr(self, edge_id: str, key: str, value) -> None:
        before = self.snapshot()
        segment = self.segment(edge_id)
        segment[key] = value
        if key == "excluded_from_task":
            segment["whole_path_exclusion_confirmed"] = bool(value)
            segment.pop("legacy_exclusion_ambiguous", None)
            segment.pop("legacy_exclusion_coverage", None)
        self._commit(before)

    def set_segment_excluded(self, edge_id: str, excluded: bool) -> None:
        """Set whole-path exclusion only after an explicit user action."""
        before = self.snapshot()
        segment = self.segment(edge_id)
        segment["excluded_from_task"] = bool(excluded)
        segment["whole_path_exclusion_confirmed"] = bool(excluded)
        segment.pop("legacy_exclusion_ambiguous", None)
        segment.pop("legacy_exclusion_coverage", None)
        self._commit(before)

    def set_review_scope(self, scope: str) -> None:
        if scope not in {"partial", "full_image"}:
            raise ValueError(f"unsupported review scope: {scope}")
        before = self.snapshot()
        self.data["review_scope"] = scope
        self._commit(before)

    def insert_point(self, edge_id: str, index: int, point) -> None:
        before = self.snapshot()
        segment = self.segment(edge_id)
        old_length = polyline_length(segment["points"])
        segment["points"].insert(index, [float(point[0]), float(point[1])])
        remap_evidence_spans(segment, old_length)
        self._commit(before)

    def move_point(self, edge_id: str, index: int, point) -> None:
        before = self.snapshot()
        self.move_point_live(edge_id, index, point)
        self._commit(before)

    def move_point_live(self, edge_id: str, index: int, point) -> None:
        segment = self.segment(edge_id)
        old_length = polyline_length(segment["points"])
        segment["points"][index] = [float(point[0]), float(point[1])]
        remap_evidence_spans(segment, old_length)
        self._sync_legacy_endpoint(segment, index)

    def _sync_legacy_endpoint(self, segment: dict, index: int) -> None:
        node_key = "start_node" if index == 0 else "end_node" if index == len(segment["points"]) - 1 else None
        node_id = segment.get(node_key, "") if node_key else ""
        if not node_id:
            return
        point = segment["points"][index]
        for node in self.data.get("legacy_nodes", []):
            if node.get("id") == node_id:
                node["x"], node["y"] = point
        for other in self.data.get("segments", []):
            if other is segment:
                continue
            if other.get("start_node") == node_id:
                other["points"][0] = list(point)
            if other.get("end_node") == node_id:
                other["points"][-1] = list(point)

    def delete_point(self, edge_id: str, index: int) -> bool:
        segment = self.segment(edge_id)
        if index <= 0 or index >= len(segment["points"]) - 1:
            return False
        before = self.snapshot()
        old_length = polyline_length(segment["points"])
        segment["points"].pop(index)
        remap_evidence_spans(segment, old_length)
        self._commit(before)
        return True

    def delete_segment(self, edge_id: str) -> None:
        before = self.snapshot()
        self.data["segments"] = [segment for segment in self.data["segments"] if segment["edge_id"] != edge_id]
        self._commit(before)

    def assign_evidence(
        self,
        edge_id: str,
        start_s: float,
        end_s: float,
        evidence: str,
        *,
        review_confidence: str = "medium",
        note: str = "",
        visibility_issue: str = "none",
    ) -> None:
        before = self.snapshot()
        assign_evidence_span(
            self.segment(edge_id),
            start_s,
            end_s,
            evidence,
            review_confidence=review_confidence,
            note=note,
            visibility_issue=visibility_issue,
        )
        self._commit(before)

    def set_evidence_span_attr(self, edge_id: str, start_s: float, end_s: float, key: str, value) -> None:
        if key not in {"review_confidence", "note", "visibility_issue"}:
            raise ValueError(f"unsupported evidence span field: {key}")
        segment = self.segment(edge_id)
        midpoint = (float(start_s) + float(end_s)) / 2.0
        target = next(
            (
                span
                for span in segment.get("evidence_spans", [])
                if float(span["start_s"]) - 1e-6 <= midpoint <= float(span["end_s"]) + 1e-6
            ),
            None,
        )
        if target is None:
            raise ValueError("selected evidence span no longer exists")
        if key == "visibility_issue":
            if value not in VISIBILITY_ISSUES:
                raise ValueError(f"unknown visibility issue: {value}")
            if target.get("evidence") != "weak_visual" and value != "none":
                raise ValueError("visibility_issue is only valid for weak_visual evidence")
        before = self.snapshot()
        if key == "visibility_issue" and value == "none":
            target.pop(key, None)
        else:
            target[key] = value
        self._commit(before)

    def mark_geometry_fixed(self, edge_id: str) -> None:
        before = self.snapshot()
        segment = self.segment(edge_id)
        segment["geometry_fixed"] = True
        segment["geometry_review_required"] = False
        segment["source"] = "manual"
        self._commit(before)

    def split_segment(self, edge_id: str, split_s: float) -> tuple[str, str]:
        segment = self.segment(edge_id)
        total = polyline_length(segment["points"])
        if split_s <= 1e-6 or split_s >= total - 1e-6:
            raise ValueError("split must be inside the path")
        before = self.snapshot()
        left = copy.deepcopy(segment)
        right = copy.deepcopy(segment)
        left["edge_id"] = self.next_edge_id()
        existing = {item["edge_id"] for item in self.data["segments"]} | {left["edge_id"]}
        number = int(left["edge_id"][1:]) + 1
        while f"e{number:06d}" in existing:
            number += 1
        right["edge_id"] = f"e{number:06d}"
        left["points"] = polyline_slice(segment["points"], 0.0, split_s)
        right["points"] = polyline_slice(segment["points"], split_s, total)
        left_spans, right_spans = [], []
        for span in segment.get("evidence_spans", []):
            if span["start_s"] < split_s:
                piece = copy.deepcopy(span)
                piece["end_s"] = min(piece["end_s"], split_s)
                if piece["end_s"] - piece["start_s"] > 1e-6:
                    left_spans.append(piece)
            if span["end_s"] > split_s:
                piece = copy.deepcopy(span)
                piece["start_s"] = max(piece["start_s"], split_s) - split_s
                piece["end_s"] -= split_s
                if piece["end_s"] - piece["start_s"] > 1e-6:
                    right_spans.append(piece)
        left["evidence_spans"], right["evidence_spans"] = left_spans, right_spans
        update_segment_review_status(left)
        update_segment_review_status(right)
        position = self.data["segments"].index(segment)
        self.data["segments"][position : position + 1] = [left, right]
        self._commit(before)
        return left["edge_id"], right["edge_id"]

    def merge_segments(self, first_id: str, second_id: str) -> str:
        if first_id == second_id:
            raise ValueError("choose a different path to merge")
        first, second = self.segment(first_id), self.segment(second_id)
        options = [
            (math.dist(first["points"][-1], second["points"][0]), first["points"], second["points"], False, False),
            (math.dist(first["points"][-1], second["points"][-1]), first["points"], second["points"], False, True),
            (math.dist(first["points"][0], second["points"][0]), first["points"], second["points"], True, False),
            (math.dist(first["points"][0], second["points"][-1]), first["points"], second["points"], True, True),
        ]
        distance, first_points, second_points, reverse_first, reverse_second = min(options, key=lambda item: item[0])
        if distance > 30.0:
            raise ValueError("path endpoints are too far apart to merge")
        before = self.snapshot()
        left = list(reversed(first_points)) if reverse_first else copy.deepcopy(first_points)
        right = list(reversed(second_points)) if reverse_second else copy.deepcopy(second_points)
        first_length = polyline_length(left)
        second_length = polyline_length(right)

        def orient_spans(segment: dict, length: float, reverse: bool, offset: float = 0.0) -> list[dict]:
            result = []
            for span in segment.get("evidence_spans", []):
                item = copy.deepcopy(span)
                if reverse:
                    item["start_s"], item["end_s"] = length - float(span["end_s"]), length - float(span["start_s"])
                item["start_s"] += offset
                item["end_s"] += offset
                result.append(item)
            return result

        merged = copy.deepcopy(first)
        bridge = distance if distance > 1e-6 else 0.0
        merged["points"] = left + (right if bridge else right[1:])
        merged["evidence_spans"] = orient_spans(first, first_length, reverse_first) + orient_spans(
            second, second_length, reverse_second, first_length + bridge
        )
        merged["excluded_from_task"] = bool(first.get("excluded_from_task") or second.get("excluded_from_task"))
        merged["whole_path_exclusion_confirmed"] = bool(
            first.get("whole_path_exclusion_confirmed") or second.get("whole_path_exclusion_confirmed")
        )
        merged["geometry_review_required"] = bool(first.get("geometry_review_required") or second.get("geometry_review_required"))
        merged.pop("start_node", None)
        merged.pop("end_node", None)
        update_segment_review_status(merged)
        positions = sorted((self.data["segments"].index(first), self.data["segments"].index(second)))
        removed = {first_id, second_id}
        self.data["segments"] = [item for item in self.data["segments"] if item["edge_id"] not in removed]
        self.data["segments"].insert(positions[0], merged)
        self._commit(before)
        return merged["edge_id"]

    def stats(self) -> dict:
        totals = {"total_px": 0.0, "reviewed_px": 0.0, "unreviewed_px": 0.0, "by_class_px": {}}
        for segment in self.data.get("segments", []):
            coverage = evidence_coverage(segment)
            for key in ("total_px", "reviewed_px", "unreviewed_px"):
                totals[key] += coverage[key]
            for evidence, length in coverage["by_class_px"].items():
                totals["by_class_px"][evidence] = totals["by_class_px"].get(evidence, 0.0) + length
        totals["percent"] = 100.0 if totals["total_px"] <= 1e-9 else totals["reviewed_px"] / totals["total_px"] * 100.0
        totals["path_count"] = len(self.data.get("segments", []))
        return totals
