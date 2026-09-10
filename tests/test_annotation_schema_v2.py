import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from amap_tool.annotation_io import atomic_write_json
from amap_tool.annotation_model import AnnotationModel
from amap_tool.annotation_schema import (
    assign_evidence_span,
    empty_document,
    evidence_coverage,
    export_derived,
    new_segment,
    polyline_length,
    upgrade_document,
)


def legacy():
    return {
        "schema_version": "1.1",
        "region": {"region_id": "legacy", "draft_source": "osm"},
        "nodes": [],
        "edges": [
            {
                "id": "e1",
                "start_node": "n1",
                "end_node": "n2",
                "polyline": [[0, 0], [100, 0]],
                "path_type": "pedestrian_path",
            }
        ],
        "ignore_regions": [],
    }


def document():
    data = empty_document("image", "rgb/image.png", 1024, 1024)
    data["segments"].append(new_segment("e1", [[0, 0], [50, 0], [100, 0]]))
    return data


def test_old_annotation_loads_unreviewed_without_assuming_clear():
    upgraded, was_legacy = upgrade_document(legacy(), width=1024, height=1024)

    assert was_legacy
    assert upgraded["schema_version"] == 2
    assert upgraded["segments"][0]["evidence_spans"] == []
    assert upgraded["segments"][0]["review_status"] == "unreviewed"
    assert upgraded["segments"][0]["source"] == "draft"


def test_schema_v2_round_trip(tmp_path):
    source = document()
    assign_evidence_span(source["segments"][0], 0, 40, "clear_visual")
    output = tmp_path / "label.json"
    atomic_write_json(source, output)

    loaded, was_legacy = upgrade_document(json.loads(output.read_text(encoding="utf-8")))

    assert not was_legacy
    assert loaded == source


def test_middle_span_assignment_uses_arc_length_and_preserves_geometry():
    segment = new_segment("e1", [[0, 0], [100, 0]])
    points = list(segment["points"])

    assign_evidence_span(segment, 25, 75, "weak_visual")

    assert segment["points"] == points
    assert segment["evidence_spans"][0]["start_s"] == 25
    assert segment["evidence_spans"][0]["end_s"] == 75
    assert evidence_coverage(segment)["percent"] == 50


def test_repainting_middle_of_span_splits_only_evidence_intervals():
    segment = new_segment("e1", [[0, 0], [100, 0]])
    assign_evidence_span(segment, 0, 100, "clear_visual")
    assign_evidence_span(segment, 25, 75, "context_only")

    assert [(s["start_s"], s["end_s"], s["evidence"]) for s in segment["evidence_spans"]] == [
        (0, 25, "clear_visual"),
        (25, 75, "context_only"),
        (75, 100, "clear_visual"),
    ]


def test_insert_control_point_keeps_evidence_fraction():
    model = AnnotationModel(document())
    model.assign_evidence("e1", 20, 80, "weak_visual")
    model.insert_point("e1", 1, [25, 30])
    total = polyline_length(model.segment("e1")["points"])
    span = model.segment("e1")["evidence_spans"][0]

    assert math.isclose(span["start_s"] / total, 0.2)
    assert math.isclose(span["end_s"] / total, 0.8)


def test_move_control_point_remaps_arc_length_reasonably():
    model = AnnotationModel(document())
    model.assign_evidence("e1", 25, 75, "clear_visual")
    old_total = polyline_length(model.segment("e1")["points"])
    model.move_point("e1", 1, [50, 50])
    new_total = polyline_length(model.segment("e1")["points"])
    span = model.segment("e1")["evidence_spans"][0]

    assert new_total > old_total
    assert math.isclose(span["start_s"] / new_total, 0.25)
    assert math.isclose(span["end_s"] / new_total, 0.75)


def test_evidence_undo_and_redo():
    model = AnnotationModel(document())
    model.assign_evidence("e1", 10, 90, "weak_visual")
    assert model.segment("e1")["evidence_spans"]

    assert model.undo_once()
    assert model.segment("e1")["evidence_spans"] == []
    assert model.redo_once()
    assert model.segment("e1")["evidence_spans"][0]["evidence"] == "weak_visual"


def test_selected_span_note_and_confidence_are_undoable():
    model = AnnotationModel(document())
    model.assign_evidence("e1", 10, 90, "weak_visual")
    model.set_evidence_span_attr("e1", 10, 90, "review_confidence", "high")
    model.set_evidence_span_attr("e1", 10, 90, "note", "tree canopy")

    assert model.segment("e1")["evidence_spans"][0]["note"] == "tree canopy"
    assert model.undo_once()
    assert model.segment("e1")["evidence_spans"][0]["note"] == ""


def test_excluding_edge_does_not_delete_geometry():
    model = AnnotationModel(document())
    original = list(model.segment("e1")["points"])
    model.set_attr("e1", "excluded_from_task", True)

    assert model.segment("e1")["points"] == original
    assert len(model.data["segments"]) == 1


def test_training_export_routes_classes_correctly():
    data = document()
    segment = data["segments"][0]
    assign_evidence_span(segment, 0, 20, "clear_visual")
    assign_evidence_span(segment, 20, 40, "weak_visual")
    assign_evidence_span(segment, 40, 60, "context_only")
    assign_evidence_span(segment, 60, 80, "draft_misalignment")
    assign_evidence_span(segment, 80, 100, "uncertain")

    exported = export_derived(data)

    assert [item["evidence"] for item in exported["valid_positive_polyline"]] == ["clear_visual", "weak_visual"]
    assert {item["evidence"] for item in exported["ignore_spans"]} == {
        "context_only",
        "draft_misalignment",
        "uncertain",
    }


def test_trusted_export_contains_only_a_and_b():
    data = document()
    segment = data["segments"][0]
    assign_evidence_span(segment, 0, 50, "clear_visual")
    assign_evidence_span(segment, 50, 100, "context_only")

    exported = export_derived(data, trusted_only=True)

    assert len(exported["valid_positive_polyline"]) == 1
    assert exported["valid_positive_polyline"][0]["evidence"] == "clear_visual"
    assert exported["ignore_spans"] == []


def test_draft_misalignment_requires_geometry_review():
    model = AnnotationModel(document())
    model.assign_evidence("e1", 0, 100, "draft_misalignment")

    assert model.segment("e1")["geometry_review_required"]
    assert export_derived(model.data)["valid_positive_polyline"] == []


def test_empty_image_can_be_explicitly_reviewed():
    model = AnnotationModel(empty_document("empty", "empty.png", 10, 10))
    before = model.snapshot()
    model.data["annotation_status"] = "reviewed"
    model._commit(before)

    assert model.data["annotation_status"] == "reviewed"
