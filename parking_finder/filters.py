"""In-memory filters and distance ranking. Nothing is stored."""

from parking_finder.geo import haversine_km
from parking_finder.models import GeoPoint, ParkingArea, TrafficItem, Webcam


def rank_parking(areas: list[ParkingArea], origin: GeoPoint | None) -> list[ParkingArea]:
    """Sort by straight-line distance when an origin exists, otherwise by name."""
    if origin is None:
        for area in areas:
            area.distance_km = None
        return sorted(areas, key=lambda area: area.name.casefold())

    for area in areas:
        if area.point is None:
            area.distance_km = None
        else:
            area.distance_km = haversine_km(origin.lat, origin.lng, area.point.lat, area.point.lng)
    return sorted(
        areas,
        key=lambda area: (
            area.distance_km is None,
            area.distance_km if area.distance_km is not None else 0,
            area.name.casefold(),
        ),
    )


def filter_parking(areas: list[ParkingArea], query: str) -> list[ParkingArea]:
    needle = query.strip().casefold()
    if not needle:
        return list(areas)
    matched: list[ParkingArea] = []
    for area in areas:
        blob = " ".join(
            [
                area.name,
                area.road,
                area.location or "",
                area.direction or "",
                " ".join(area.details),
                " ".join(area.features),
            ]
        ).casefold()
        if needle in blob:
            matched.append(area)
    return matched


def filter_traffic(items: list[TrafficItem], *, kind: str, when: str, query: str) -> list[TrafficItem]:
    needle = query.strip().casefold()
    matched: list[TrafficItem] = []
    for item in items:
        if kind != "all" and item.kind != kind:
            continue
        if when == "active" and item.planned:
            continue
        if when == "planned" and not item.planned:
            continue
        if needle:
            blob = " ".join([item.title, item.subtitle or "", " ".join(item.details)]).casefold()
            if needle not in blob:
                continue
        matched.append(item)
    return matched


def filter_webcams(cameras: list[Webcam], query: str) -> list[Webcam]:
    needle = query.strip().casefold()
    if not needle:
        return list(cameras)
    return [
        camera
        for camera in cameras
        if needle in " ".join([camera.title, camera.subtitle or "", " ".join(camera.details)]).casefold()
    ]
