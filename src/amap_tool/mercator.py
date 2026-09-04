from __future__ import annotations
import math

EARTH_RADIUS = 6378137.0
TILE_SIZE = 256

def world_size(zoom: int) -> float:
    return TILE_SIZE * (2 ** zoom)

def lon_to_x(lon: float, zoom: int) -> float:
    return (lon + 180.0) / 360.0 * world_size(zoom)

def lat_to_y(lat: float, zoom: int) -> float:
    lat = max(-85.05112878, min(85.05112878, lat))
    return (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * world_size(zoom)

def x_to_lon(x: float, zoom: int) -> float:
    return x / world_size(zoom) * 360.0 - 180.0

def y_to_lat(y: float, zoom: int) -> float:
    n = math.pi - 2 * math.pi * y / world_size(zoom)
    return math.degrees(math.atan(math.sinh(n)))

def meters_per_pixel(lat: float, zoom: int) -> float:
    return 156543.03392804097 * math.cos(math.radians(lat)) / (2 ** zoom)
