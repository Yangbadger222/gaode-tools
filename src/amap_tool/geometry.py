from __future__ import annotations

import math
from typing import Iterable, Sequence

Point = Sequence[float]


def closest_point_on_segment(point: Point, a: Point, b: Point) -> tuple[list[float], float]:
    """Return the projected point and its segment parameter ``t`` in [0, 1]."""
    px, py = float(point[0]), float(point[1])
    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-18:
        return [ax, ay], 0.0
    t = ((px - ax) * dx + (py - ay) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    return [ax + t * dx, ay + t * dy], t


def distance_point_to_segment(point: Point, a: Point, b: Point) -> float:
    projected, _ = closest_point_on_segment(point, a, b)
    return math.hypot(float(point[0]) - projected[0], float(point[1]) - projected[1])


def nearest_polyline_segment(point: Point, polyline: Iterable[Point]) -> dict | None:
    points = list(polyline)
    if len(points) < 2:
        return None
    best = None
    for index, (a, b) in enumerate(zip(points, points[1:])):
        projected, t = closest_point_on_segment(point, a, b)
        distance = math.hypot(float(point[0]) - projected[0], float(point[1]) - projected[1])
        candidate = {
            "segment_index": index,
            "projected_point": projected,
            "distance": distance,
            "t": t,
        }
        if best is None or distance < best["distance"]:
            best = candidate
    return best


def nearest_edge_segment(point: Point, edges: Iterable[dict]) -> dict | None:
    """Find the closest segment across edge dictionaries."""
    best = None
    for edge in edges:
        hit = nearest_polyline_segment(point, edge.get("polyline", []))
        if hit is None:
            continue
        candidate = dict(hit)
        candidate["edge_id"] = edge.get("id")
        if best is None or candidate["distance"] < best["distance"]:
            best = candidate
    return best


def orientation(a: Point, b: Point, c: Point, epsilon: float = 1e-9) -> int:
    value = (float(b[0]) - float(a[0])) * (float(c[1]) - float(a[1])) - (
        float(b[1]) - float(a[1])
    ) * (float(c[0]) - float(a[0]))
    if abs(value) <= epsilon:
        return 0
    return 1 if value > 0 else -1


def _on_segment(a: Point, b: Point, p: Point, epsilon: float = 1e-9) -> bool:
    return (
        min(float(a[0]), float(b[0])) - epsilon <= float(p[0]) <= max(float(a[0]), float(b[0])) + epsilon
        and min(float(a[1]), float(b[1])) - epsilon <= float(p[1]) <= max(float(a[1]), float(b[1])) + epsilon
    )


def segments_intersect(a: Point, b: Point, c: Point, d: Point, epsilon: float = 1e-9) -> bool:
    o1, o2, o3, o4 = orientation(a, b, c, epsilon), orientation(a, b, d, epsilon), orientation(c, d, a, epsilon), orientation(c, d, b, epsilon)
    if o1 != o2 and o3 != o4:
        return True
    return (o1 == 0 and _on_segment(a, b, c, epsilon)) or (o2 == 0 and _on_segment(a, b, d, epsilon)) or (o3 == 0 and _on_segment(c, d, a, epsilon)) or (o4 == 0 and _on_segment(c, d, b, epsilon))


def point_in_polygon(point: Point, polygon: Iterable[Point]) -> bool:
    points = list(polygon)
    if len(points) < 3:
        return False
    x, y = float(point[0]), float(point[1])
    inside = False
    for a, b in zip(points, points[1:] + points[:1]):
        if distance_point_to_segment((x, y), a, b) <= 1e-9:
            return True
        if (float(a[1]) > y) != (float(b[1]) > y):
            cross_x = (float(b[0]) - float(a[0])) * (y - float(a[1])) / (float(b[1]) - float(a[1])) + float(a[0])
            if x < cross_x:
                inside = not inside
    return inside
