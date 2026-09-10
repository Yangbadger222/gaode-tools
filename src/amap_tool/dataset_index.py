"""Scan ordinary image folders into a safe, annotation-ready dataset index."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, UnidentifiedImageError

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}
IMAGE_DIR_NAMES = ("rgb", "images", "image", "imgs")
ANNOTATION_DIR_NAMES = ("annotations", "annotations_v2", "labels", "json", "annotation")
OUTPUT_DIR_NAME = "annotations_v2"


@dataclass
class ScanIssue:
    code: str
    message: str
    path: str = ""
    severity: str = "warning"


@dataclass
class ImageRecord:
    image_id: str
    source_path: Path
    relative_path: Path
    width: int
    height: int
    modified_time: float
    region: str
    annotation_path: Path | None = None
    output_annotation_path: Path | None = None
    annotation_schema_version: str = ""
    review_status: str = "unreviewed"
    review_scope: str = "partial"
    path_count: int = 0
    evidence_percent: float = 0.0
    evidence_flags: set[str] = field(default_factory=set)
    missing: bool = False

    @property
    def annotated(self) -> bool:
        return self.annotation_path is not None


@dataclass
class DatasetIndex:
    root: Path
    image_root: Path
    annotation_root: Path | None
    output_root: Path
    records: list[ImageRecord]
    issues: list[ScanIssue]
    recursive: bool = True
    read_only: bool = False

    def record_by_id(self, image_id: str) -> ImageRecord | None:
        return next((record for record in self.records if record.image_id == image_id), None)

    @property
    def reviewed_count(self) -> int:
        return sum(record.review_status == "reviewed" for record in self.records)

    @property
    def annotated_count(self) -> int:
        return sum(record.annotated for record in self.records)

    @property
    def full_image_reviewed_count(self) -> int:
        return sum(record.review_scope == "full_image" for record in self.records)


def _files(root: Path, extensions: set[str], recursive: bool) -> list[Path]:
    iterator = root.rglob("*") if recursive else root.glob("*")
    return sorted(path for path in iterator if path.is_file() and path.suffix.lower() in extensions)


def _directory_candidates(root: Path, names: tuple[str, ...], extensions: set[str]) -> list[Path]:
    candidates = []
    for child in root.iterdir() if root.exists() else []:
        if child.is_dir() and child.name.lower() in names and any(
            path.is_file() and path.suffix.lower() in extensions for path in child.rglob("*")
        ):
            candidates.append(child)
    return sorted(candidates)


def _read_annotation_summary(path: Path) -> tuple[dict | None, ScanIssue | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, ScanIssue("broken_json", f"Cannot read annotation JSON: {exc}", str(path))
    if not isinstance(data, dict):
        return None, ScanIssue("unsupported_schema", "Annotation root must be a JSON object", str(path))
    return data, None


def _schema_version(data: dict) -> str:
    return str(data.get("schema_version", "1"))


def _annotation_image_keys(data: dict) -> set[str]:
    values = {
        str(data.get("image_id", "")),
        str(data.get("image", {}).get("filename", "")) if isinstance(data.get("image"), dict) else "",
        str(data.get("image", {}).get("source_path", "")) if isinstance(data.get("image"), dict) else "",
    }
    return {value for value in values if value}


def _evidence_summary(data: dict) -> tuple[int, float, set[str]]:
    segments = data.get("segments")
    if not isinstance(segments, list):
        segments = data.get("edges", [])
    total = reviewed = 0.0
    flags: set[str] = set()
    for segment in segments:
        points = segment.get("points", segment.get("polyline", []))
        length = sum(
            ((float(b[0]) - float(a[0])) ** 2 + (float(b[1]) - float(a[1])) ** 2) ** 0.5
            for a, b in zip(points, points[1:])
        )
        total += length
        for span in segment.get("evidence_spans", []):
            reviewed += max(0.0, float(span.get("end_s", 0)) - float(span.get("start_s", 0)))
            evidence = span.get("evidence", "")
            if evidence:
                flags.add(evidence)
    percent = 100.0 if total <= 1e-9 and segments else min(100.0, reviewed / total * 100.0) if total else 0.0
    return len(segments), percent, flags


def _can_write_directory(path: Path) -> bool:
    existing = path
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    return existing.is_dir() and os.access(existing, os.W_OK)


def scan_dataset(
    root: str | Path,
    *,
    recursive: bool = True,
    image_root: str | Path | None = None,
    annotation_root: str | Path | None = None,
    output_root: str | Path | None = None,
    read_only: bool = False,
) -> DatasetIndex:
    root_path = Path(root).expanduser().resolve()
    issues: list[ScanIssue] = []
    if not root_path.exists() or not root_path.is_dir():
        return DatasetIndex(root_path, root_path, None, root_path / OUTPUT_DIR_NAME, [], [ScanIssue("missing_folder", "Folder does not exist", str(root_path), "error")], recursive, read_only)

    image_candidates = _directory_candidates(root_path, IMAGE_DIR_NAMES, IMAGE_EXTENSIONS)
    if image_root is None:
        if len(image_candidates) == 1:
            selected_image_root = image_candidates[0]
        else:
            selected_image_root = root_path
            if len(image_candidates) > 1:
                issues.append(ScanIssue("ambiguous_image_folder", "Multiple image folders found; recursive root scan is being used", str(root_path)))
    else:
        selected_image_root = Path(image_root).expanduser().resolve()

    annotation_candidates = _directory_candidates(root_path, ANNOTATION_DIR_NAMES, {".json"})
    if annotation_root is None:
        upgraded_candidates = [candidate for candidate in annotation_candidates if candidate.name.lower() == OUTPUT_DIR_NAME]
        if len(upgraded_candidates) == 1:
            selected_annotation_root = upgraded_candidates[0]
        else:
            selected_annotation_root = annotation_candidates[0] if len(annotation_candidates) == 1 else None
        if len(annotation_candidates) > 1 and selected_annotation_root is None:
            issues.append(ScanIssue("ambiguous_annotation_folder", "Multiple annotation folders found; same-file matching only", str(root_path)))
    else:
        selected_annotation_root = Path(annotation_root).expanduser().resolve()
    selected_output_root = Path(output_root).expanduser().resolve() if output_root else root_path / OUTPUT_DIR_NAME

    excluded_roots = {candidate.resolve() for candidate in annotation_candidates}
    excluded_roots.add(selected_output_root.resolve())
    if selected_image_root == root_path:
        image_paths = [
            path
            for path in _files(selected_image_root, IMAGE_EXTENSIONS, recursive)
            if not any(excluded == path.resolve() or excluded in path.resolve().parents for excluded in excluded_roots)
        ]
    else:
        image_paths = _files(selected_image_root, IMAGE_EXTENSIONS, recursive)

    records: list[ImageRecord] = []
    id_to_record: dict[str, ImageRecord] = {}
    stem_to_records: dict[str, list[ImageRecord]] = {}
    for image_path in image_paths:
        try:
            with Image.open(image_path) as image:
                width, height = image.size
                image.verify()
        except (OSError, UnidentifiedImageError, ValueError) as exc:
            issues.append(ScanIssue("broken_image", f"Cannot open image: {exc}", str(image_path)))
            continue
        relative = image_path.relative_to(selected_image_root)
        image_id = relative.with_suffix("").as_posix()
        if image_id in id_to_record:
            issues.append(ScanIssue("duplicate_image_id", f"Duplicate image id: {image_id}", str(image_path), "error"))
            image_id = relative.as_posix()
        record = ImageRecord(
            image_id=image_id,
            source_path=image_path.resolve(),
            relative_path=relative,
            width=int(width),
            height=int(height),
            modified_time=image_path.stat().st_mtime,
            region=relative.parent.as_posix() if relative.parent != Path(".") else "",
        )
        records.append(record)
        id_to_record[image_id] = record
        stem_to_records.setdefault(image_path.stem, []).append(record)

    json_roots = [root_path]
    if selected_annotation_root and selected_annotation_root != root_path:
        json_roots.append(selected_annotation_root)
    json_paths: list[Path] = []
    for json_root in json_roots:
        json_paths.extend(_files(json_root, {".json"}, recursive))
    json_paths = sorted(
        {
            path.resolve()
            for path in json_paths
            if path.name not in {".dataset_index.json", ".annotation_tool_v2_session.json"}
            and (
                selected_annotation_root is not None
                and selected_annotation_root.resolve() == selected_output_root.resolve()
                or selected_output_root.resolve() not in path.resolve().parents
            )
        }
    )
    parsed: dict[Path, dict] = {}
    for path in json_paths:
        data, issue = _read_annotation_summary(path)
        if issue:
            issues.append(issue)
        elif data is not None:
            parsed[path] = data

    used_annotations: set[Path] = set()
    sidecar_counts: dict[Path, int] = {}
    separated_counts: dict[Path, int] = {}
    for record in records:
        sidecar = record.source_path.with_suffix(".json").resolve()
        sidecar_counts[sidecar] = sidecar_counts.get(sidecar, 0) + 1
        if selected_annotation_root:
            separated = (selected_annotation_root / record.relative_path).with_suffix(".json").resolve()
            separated_counts[separated] = separated_counts.get(separated, 0) + 1
    for record in records:
        same_directory = record.source_path.with_suffix(".json").resolve()
        separated = None
        if selected_annotation_root:
            separated = (selected_annotation_root / record.relative_path).with_suffix(".json").resolve()
        if same_directory in parsed and sidecar_counts[same_directory] > 1:
            issues.append(
                ScanIssue(
                    "ambiguous_annotation",
                    f"Multiple image formats share annotation stem {same_directory.stem}",
                    str(same_directory),
                    "error",
                )
            )
        elif separated in parsed and separated_counts.get(separated, 0) > 1:
            issues.append(
                ScanIssue(
                    "ambiguous_annotation",
                    f"Multiple images map to {separated.name}",
                    str(separated),
                    "error",
                )
            )
        elif separated in parsed and selected_annotation_root.name.lower() == OUTPUT_DIR_NAME:
            # An explicit v2 upgrade is the continuation of the earlier session;
            # the untouched same-directory v1 remains only as source provenance.
            record.annotation_path = separated
        elif same_directory in parsed:
            record.annotation_path = same_directory
        elif separated in parsed:
            record.annotation_path = separated

    for annotation_path, data in parsed.items():
        if annotation_path in {record.annotation_path for record in records if record.annotation_path}:
            continue
        matched: set[str] = set()
        for key in _annotation_image_keys(data):
            key_path = Path(key)
            possible_ids = {key, key_path.with_suffix("").as_posix(), key_path.stem}
            for possible in possible_ids:
                if possible in id_to_record:
                    matched.add(id_to_record[possible].image_id)
                for record in stem_to_records.get(possible, []):
                    matched.add(record.image_id)
        if len(matched) == 1:
            record = id_to_record[next(iter(matched))]
            if record.annotation_path is None:
                record.annotation_path = annotation_path
            else:
                issues.append(ScanIssue("ambiguous_annotation", f"A second annotation matches {record.image_id}", str(annotation_path), "error"))
        elif len(matched) > 1:
            issues.append(ScanIssue("ambiguous_annotation", "Annotation metadata matches more than one image", str(annotation_path), "error"))

    for record in records:
        standard_id = record.relative_path.with_suffix("").as_posix()
        output_relative = (
            record.relative_path.with_suffix(".json")
            if record.image_id == standard_id
            else Path(record.relative_path.as_posix() + ".json")
        )
        if record.annotation_path:
            used_annotations.add(record.annotation_path.resolve())
            data = parsed.get(record.annotation_path.resolve(), {})
            version = _schema_version(data)
            record.annotation_schema_version = version
            record.review_status = str(data.get("annotation_status") or data.get("region", {}).get("review_status") or "unreviewed")
            record.review_scope = str(data.get("review_scope", "partial"))
            record.path_count, record.evidence_percent, record.evidence_flags = _evidence_summary(data)
            image_meta = data.get("image", {}) if isinstance(data.get("image"), dict) else {}
            saved_width, saved_height = image_meta.get("width"), image_meta.get("height")
            if saved_width and saved_height and (int(saved_width), int(saved_height)) != (record.width, record.height):
                issues.append(
                    ScanIssue(
                        "image_size_mismatch",
                        f"Annotation size {saved_width}×{saved_height} does not match image {record.width}×{record.height}",
                        str(record.annotation_path),
                    )
                )
            if version.startswith("2"):
                record.output_annotation_path = record.annotation_path
            else:
                record.output_annotation_path = selected_output_root / output_relative
        else:
            record.output_annotation_path = selected_output_root / output_relative

        direct_legacy = record.source_path.with_suffix(".json").resolve()
        if (
            record.annotation_path
            and selected_annotation_root
            and selected_annotation_root.name.lower() == OUTPUT_DIR_NAME
            and direct_legacy in parsed
        ):
            used_annotations.add(direct_legacy)

    for annotation_path in parsed:
        if annotation_path.resolve() not in used_annotations:
            issues.append(ScanIssue("orphan_annotation", "Annotation has no exact image match", str(annotation_path)))
    if not records:
        issues.append(ScanIssue("no_images", "No supported, readable images found", str(selected_image_root), "error"))
    if not read_only and not _can_write_directory(selected_output_root):
        issues.append(ScanIssue("output_unwritable", "Annotation output folder is not writable", str(selected_output_root), "error"))

    return DatasetIndex(
        root=root_path,
        image_root=selected_image_root,
        annotation_root=selected_annotation_root,
        output_root=selected_output_root,
        records=records,
        issues=issues,
        recursive=recursive,
        read_only=read_only,
    )


def dataset_from_files(files: list[str | Path], output_root: str | Path) -> DatasetIndex:
    """Create a temporary dataset from explicitly dropped image files."""
    paths = [Path(path).expanduser().resolve() for path in files]
    common = Path(os.path.commonpath([str(path.parent) for path in paths])) if paths else Path.cwd()
    output = Path(output_root).expanduser().resolve()
    records: list[ImageRecord] = []
    issues: list[ScanIssue] = []
    used_ids: set[str] = set()
    for path in paths:
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            issues.append(ScanIssue("unsupported_image", "Unsupported image format", str(path)))
            continue
        try:
            with Image.open(path) as image:
                width, height = image.size
                image.verify()
        except (OSError, UnidentifiedImageError, ValueError) as exc:
            issues.append(ScanIssue("broken_image", f"Cannot open image: {exc}", str(path)))
            continue
        relative = path.relative_to(common)
        image_id = relative.with_suffix("").as_posix()
        if image_id in used_ids:
            image_id = relative.as_posix()
        used_ids.add(image_id)
        records.append(
            ImageRecord(
                image_id=image_id,
                source_path=path,
                relative_path=relative,
                width=width,
                height=height,
                modified_time=path.stat().st_mtime,
                region=relative.parent.as_posix() if relative.parent != Path(".") else "",
                output_annotation_path=(output / relative).with_suffix(".json"),
            )
        )
    return DatasetIndex(common, common, None, output, records, issues, True, False)
