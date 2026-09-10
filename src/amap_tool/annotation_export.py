"""Export region-level path graphs into per-tile model-validation artifacts."""

from __future__ import annotations

from collections.abc import Iterable


def clip_segment_to_rect(start, end, width, height):
    """Clip a line segment to the inclusive image rectangle.

    Returns local pixel coordinates or ``None`` when the segment is outside.
    The implementation uses Liang-Barsky clipping so no geometry dependency is
    required by the small command-line exporter.
    """
    x0, y0 = map(float, start)
    x1, y1 = map(float, end)
    dx, dy = x1 - x0, y1 - y0
    p = (-dx, dx, -dy, dy)
    q = (x0, width - x0, y0, height - y0)
    lower, upper = 0.0, 1.0
    for delta, distance in zip(p, q):
        if delta == 0:
            if distance < 0:
                return None
            continue
        ratio = distance / delta
        if delta < 0:
            if ratio > upper:
                return None
            lower = max(lower, ratio)
        else:
            if ratio < lower:
                return None
            upper = min(upper, ratio)
    def clamp(point):
        return [
            min(float(width), max(0.0, point[0])),
            min(float(height), max(0.0, point[1])),
        ]

    return (
        clamp([x0 + lower * dx, y0 + lower * dy]),
        clamp([x0 + upper * dx, y0 + upper * dy]),
    )


def tile_edge_parts(edges: Iterable[dict], tile_x, tile_y, width, height):
    """Return edge fragments that are visible in one tile, in local pixels."""
    parts = []
    for edge in edges:
        points = edge.get("polyline", [])
        for segment_index, (start, end) in enumerate(zip(points, points[1:])):
            local_start = [start[0] - tile_x, start[1] - tile_y]
            local_end = [end[0] - tile_x, end[1] - tile_y]
            clipped = clip_segment_to_rect(local_start, local_end, width, height)
            if clipped is None:
                continue
            parts.append(
                {
                    "edge_id": edge["id"],
                    "segment_index": segment_index,
                    "points": [clipped[0], clipped[1]],
                    "path_type": edge.get("path_type", "unknown"),
                    "visibility": edge.get("visibility", "unknown"),
                    "confidence": edge.get("confidence", "unknown"),
                    "verification_source": edge.get("verification_source", "none"),
                }
            )
    return parts
