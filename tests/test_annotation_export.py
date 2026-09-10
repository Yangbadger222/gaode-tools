from amap_tool.annotation_export import clip_segment_to_rect, tile_edge_parts


def test_clip_segment_to_rect_returns_tile_local_endpoints():
    assert clip_segment_to_rect((-5, 10), (15, 10), 10, 20) == ([0.0, 10.0], [10.0, 10.0])
    assert clip_segment_to_rect((-5, -5), (-1, -1), 10, 10) is None


def test_tile_edge_parts_clips_global_graph_to_one_tile():
    edges = [{"id": "e1", "polyline": [[90, 50], [120, 50]], "path_type": "pedestrian_path"}]
    parts = tile_edge_parts(edges, tile_x=100, tile_y=0, width=20, height=100)
    assert parts == [{
        "edge_id": "e1", "segment_index": 0, "points": [[0.0, 50.0], [20.0, 50.0]],
        "path_type": "pedestrian_path", "visibility": "unknown", "confidence": "unknown",
        "verification_source": "none",
    }]
