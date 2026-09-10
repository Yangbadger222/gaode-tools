import hashlib
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from amap_tool.annotation_io import AnnotationWriteError, atomic_write_json
from amap_tool.app_state import AppStateStore
from amap_tool.dataset_index import scan_dataset


def image(path: Path, size=(32, 24), color=(30, 60, 90)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def v2(image_id="img001", width=32, height=24):
    return {
        "schema_version": 2,
        "image_id": image_id,
        "image": {"source_path": f"{image_id}.png", "width": width, "height": height},
        "annotation_status": "unreviewed",
        "segments": [],
    }


def test_only_png_folder_scans_without_creating_annotations(tmp_path):
    image(tmp_path / "a.png")
    result = scan_dataset(tmp_path)

    assert [record.image_id for record in result.records] == ["a"]
    assert not (tmp_path / "annotations_v2").exists()
    assert result.records[0].output_annotation_path == tmp_path / "annotations_v2" / "a.json"


def test_same_stem_json_pairs_automatically(tmp_path):
    image(tmp_path / "a.png")
    (tmp_path / "a.json").write_text(json.dumps(v2("a")), encoding="utf-8")

    result = scan_dataset(tmp_path)

    assert result.records[0].annotation_path == (tmp_path / "a.json").resolve()


def test_rgb_and_annotations_directories_pair_by_relative_path(tmp_path):
    image(tmp_path / "rgb" / "sub" / "a.png")
    label = tmp_path / "annotations" / "sub" / "a.json"
    label.parent.mkdir(parents=True)
    label.write_text(json.dumps(v2("sub/a")), encoding="utf-8")

    result = scan_dataset(tmp_path)

    assert result.image_root == (tmp_path / "rgb").resolve()
    assert result.records[0].annotation_path == label.resolve()


def test_recursive_same_filename_keeps_unique_relative_identity(tmp_path):
    image(tmp_path / "north" / "tile.png")
    image(tmp_path / "south" / "tile.png")

    result = scan_dataset(tmp_path)

    assert {record.image_id for record in result.records} == {"north/tile", "south/tile"}


def test_same_stem_different_image_formats_never_share_output(tmp_path):
    image(tmp_path / "tile.png")
    image(tmp_path / "tile.jpg")
    (tmp_path / "tile.json").write_text(json.dumps(v2("tile")), encoding="utf-8")

    result = scan_dataset(tmp_path)

    assert len({record.output_annotation_path for record in result.records}) == 2
    assert all(record.annotation_path is None for record in result.records)
    assert "ambiguous_annotation" in {issue.code for issue in result.issues}


def test_orphan_and_broken_json_are_reported_without_blocking_images(tmp_path):
    image(tmp_path / "a.png")
    (tmp_path / "orphan.json").write_text(json.dumps(v2("missing")), encoding="utf-8")
    (tmp_path / "broken.json").write_text("{no", encoding="utf-8")

    result = scan_dataset(tmp_path)
    codes = {issue.code for issue in result.issues}

    assert len(result.records) == 1
    assert "orphan_annotation" in codes
    assert "broken_json" in codes


def test_empty_folder_has_clear_issue(tmp_path):
    result = scan_dataset(tmp_path)

    assert result.records == []
    assert "no_images" in {issue.code for issue in result.issues}


def test_legacy_annotation_uses_separate_v2_output(tmp_path):
    image(tmp_path / "a.png")
    (tmp_path / "a.json").write_text(json.dumps({"schema_version": "1.1", "edges": []}), encoding="utf-8")

    record = scan_dataset(tmp_path).records[0]

    assert record.annotation_schema_version == "1.1"
    assert record.output_annotation_path == tmp_path / "annotations_v2" / "a.json"


def test_existing_v2_upgrade_is_preferred_without_overwriting_v1(tmp_path):
    image(tmp_path / "a.png")
    legacy = tmp_path / "a.json"
    legacy.write_text(json.dumps({"schema_version": "1.1", "edges": []}), encoding="utf-8")
    upgraded = tmp_path / "annotations_v2" / "a.json"
    upgraded.parent.mkdir()
    upgraded.write_text(json.dumps(v2("a")), encoding="utf-8")

    record = scan_dataset(tmp_path).records[0]

    assert record.annotation_path == upgraded.resolve()
    assert record.annotation_schema_version == "2"


def test_annotation_size_mismatch_is_reported(tmp_path):
    image(tmp_path / "a.png")
    (tmp_path / "a.json").write_text(json.dumps(v2("a", 10, 10)), encoding="utf-8")

    result = scan_dataset(tmp_path)

    assert "image_size_mismatch" in {issue.code for issue in result.issues}


def test_atomic_save_keeps_valid_backup(tmp_path):
    target = tmp_path / "label.json"
    atomic_write_json({"version": 1}, target)
    atomic_write_json({"version": 2}, target)

    assert json.loads(target.read_text())["version"] == 2
    assert json.loads((tmp_path / "label.json.bak").read_text())["version"] == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_scan_and_annotation_save_do_not_change_rgb_hash(tmp_path):
    rgb = tmp_path / "a.png"
    image(rgb)
    before = digest(rgb)
    result = scan_dataset(tmp_path)
    atomic_write_json(v2("a"), result.records[0].output_annotation_path)

    assert digest(rgb) == before


def test_output_path_that_is_a_file_is_reported_unwritable(tmp_path):
    image(tmp_path / "a.png")
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory")

    result = scan_dataset(tmp_path, output_root=blocked)

    assert "output_unwritable" in {issue.code for issue in result.issues}


def test_recent_folders_and_session_restore(tmp_path):
    state = AppStateStore(tmp_path / "state.json")
    folder = tmp_path / "dataset"
    folder.mkdir()
    state.add_recent(folder)
    state.save_session(folder, {"last_image_id": "a", "zoom": 4})

    restored = AppStateStore(tmp_path / "state.json")

    assert restored.recent_folders()[0]["path"] == str(folder.resolve())
    assert restored.session(folder) == {"last_image_id": "a", "zoom": 4}
    restored.remove_recent(folder)
    assert restored.recent_folders() == []


def test_crash_recovery_round_trip(tmp_path):
    state = AppStateStore(tmp_path / "state.json")
    state.save_recovery({"image_id": "a", "document": v2("a")})

    assert AppStateStore(tmp_path / "state.json").recovery()["image_id"] == "a"
    state.clear_recovery()
    assert state.recovery() is None
