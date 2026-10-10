"""Turn raw Autobahn JSON into display models. Bad records are skipped."""

import re

from parking_finder.geo import as_float, from_lng_lat, order_pair
from parking_finder.models import GeoPoint, ParkingArea, TrafficItem, Webcam

_TRUCK = re.compile(r"LKW[\s\-]*Stellpl(?:ätze|aetze)\s*:?\s*(\d+)", re.IGNORECASE)
_CAR = re.compile(r"PKW[\s\-]*Stellpl(?:ätze|aetze)\s*:?\s*(\d+)", re.IGNORECASE)
_ROAD_KEY = re.compile(r"^([A-Za-z]+)(\d+)(.*)$")
_DIRECTION = re.compile(r"(->|→|\brichtung\b)", re.IGNORECASE)

_OCCUPANCY_KEYS = (
    "occupancy",
    "occupation",
    "occupationRate",
    "vacancy",
    "vacant",
    "free",
    "freeSpaces",
    "free_spaces",
    "available",
    "availableSpaces",
    "belegung",
)


def road_sort_key(road: str) -> tuple:
    """Sort A2 before A10."""
    match = _ROAD_KEY.match(road.strip())
    if not match:
        return (road, 0, "")
    return (match.group(1), int(match.group(2)), match.group(3))


def clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"undefined", "none", "null", "nan"}:
        return None
    if text.lower().endswith("| undefined"):
        text = text.rsplit("|", 1)[0].strip(" |")
    if not text or text.lower() == "undefined":
        return None
    return text


def text_lines(value: object) -> list[str]:
    if isinstance(value, str):
        chunks = [value]
    elif isinstance(value, list):
        chunks = [item for item in value if isinstance(item, str)]
    else:
        return []
    lines: list[str] = []
    for chunk in chunks:
        for piece in chunk.splitlines():
            text = piece.strip()
            if not text or text.lower() == "undefined":
                continue
            if re.fullmatch(r"Koordinaten:\s*undefined", text, flags=re.IGNORECASE):
                continue
            lines.append(text)
    return lines


def extract_point(raw: dict) -> GeoPoint | None:
    """Read a position from coordinate, point, or the extent rectangle."""
    if not isinstance(raw, dict):
        return None
    point = _from_coordinate(raw.get("coordinate"))
    if point:
        return point
    point = _from_point_string(raw.get("point"))
    if point:
        return point
    return _from_extent(raw.get("extent"))


def _from_coordinate(coord: object) -> GeoPoint | None:
    if not isinstance(coord, dict):
        return None
    coordinates = coord.get("coordinates")
    if isinstance(coordinates, (list, tuple)) and len(coordinates) >= 2:
        # GeoJSON positions are longitude, latitude.
        return from_lng_lat(coordinates[0], coordinates[1])
    lat = as_float(coord.get("lat", coord.get("latitude")))
    lng = coord.get("long", coord.get("lng", coord.get("lon")))
    if lng is None:
        lng = coord.get("longitude")
    lng_f = as_float(lng)
    if lat is None or lng_f is None:
        return None
    if -90 <= lat <= 90 and -180 <= lng_f <= 180:
        return GeoPoint(lat, lng_f)
    return None


def _from_point_string(value: object) -> GeoPoint | None:
    if not isinstance(value, str) or "," not in value:
        return None
    parts = [part.strip() for part in value.split(",")]
    if len(parts) < 2:
        return None
    first, second = as_float(parts[0]), as_float(parts[1])
    if first is None or second is None:
        return None
    return order_pair(first, second)


def _from_extent(value: object) -> GeoPoint | None:
    if not isinstance(value, str):
        return None
    parts = [as_float(part) for part in value.split(",")]
    if len(parts) != 4 or any(part is None for part in parts):
        return None
    first = order_pair(parts[0], parts[1])
    second = order_pair(parts[2], parts[3])
    if first is None or second is None:
        return None
    return GeoPoint((first.lat + second.lat) / 2, (first.lng + second.lng) / 2)


def _records(payload: dict, key: str) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get(key, payload.get("items", []))
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _flag(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def availability_text(raw: dict) -> str:
    """Live free-space counts are usually absent. Never invent them.

    Listed stall counts are capacity, not occupancy, so they do not count.
    """
    for key in _OCCUPANCY_KEYS:
        if key not in raw:
            continue
        value = raw.get(key)
        if value in (None, "", [], {}):
            continue
        return f"Availability reported: {value} (not a guarantee — check on site)"
    return "Availability unknown"


def _capacity(lines: list[str], pattern: re.Pattern[str]) -> int | None:
    for line in lines:
        match = pattern.search(line)
        if match:
            return int(match.group(1))
    return None


def _is_capacity_line(line: str) -> bool:
    return bool(_TRUCK.search(line) or _CAR.search(line))


def _looks_like_direction(text: str | None) -> bool:
    return bool(text and _DIRECTION.search(text))


def parking_name(raw: dict, road: str) -> str:
    subtitle = clean_text(raw.get("subtitle"))
    title = clean_text(raw.get("title"))
    if subtitle and not _looks_like_direction(subtitle):
        return subtitle
    if title:
        stripped = re.sub(rf"^{re.escape(road)}\s*\|?\s*", "", title, flags=re.IGNORECASE).strip(" |")
        if stripped and stripped.lower() not in {road.lower(), "undefined"}:
            return stripped
    if subtitle:
        return subtitle
    if title and title.lower() != road.lower():
        return title
    return "Unnamed parking area"


def parking_direction(raw: dict) -> str | None:
    for key in ("subtitle", "title"):
        text = clean_text(raw.get(key))
        if _looks_like_direction(text):
            return text
    for line in text_lines(raw.get("description")):
        if _looks_like_direction(line):
            return line
    return None


def location_label(raw: dict, road: str, name: str) -> str | None:
    title = clean_text(raw.get("title"))
    if not title:
        return None
    if title.lower() in {road.lower(), name.lower()}:
        return None
    return title


def _features(raw: dict) -> list[str]:
    icons = raw.get("lorryParkingFeatureIcons") or []
    if not isinstance(icons, list):
        return []
    names: list[str] = []
    for icon in icons:
        if not isinstance(icon, dict):
            continue
        description = clean_text(icon.get("description"))
        if description and description not in names:
            names.append(description)
    return names


def _unique_id(raw: dict, fallback: str, seen: set[str]) -> str:
    base = clean_text(raw.get("identifier")) or fallback
    candidate = base
    suffix = 2
    while candidate in seen:
        candidate = f"{base}-{suffix}"
        suffix += 1
    seen.add(candidate)
    return candidate


def parse_parking(payload: dict, road: str) -> list[ParkingArea]:
    seen: set[str] = set()
    areas: list[ParkingArea] = []
    for index, raw in enumerate(_records(payload, "parking_lorry")):
        try:
            lines = text_lines(raw.get("description")) + text_lines(raw.get("footer"))
            name = parking_name(raw, road)
            area = ParkingArea(
                id=_unique_id(raw, f"{road}-parking-{index}", seen),
                name=name,
                road=road,
                location=location_label(raw, road, name),
                direction=parking_direction(raw),
                point=extract_point(raw),
                availability=availability_text(raw),
                truck_spaces=_capacity(lines, _TRUCK),
                car_spaces=_capacity(lines, _CAR),
                features=_features(raw),
                details=[line for line in lines if not _is_capacity_line(line)],
                blocked=_flag(raw.get("isBlocked")),
                planned=_flag(raw.get("future")),
                api_id=clean_text(raw.get("identifier")) or "",
            )
        except (TypeError, ValueError):
            continue
        areas.append(area)
    return areas


def _parse_events(payload: dict, road: str, key: str, kind: str) -> list[TrafficItem]:
    seen: set[str] = set()
    items: list[TrafficItem] = []
    for index, raw in enumerate(_records(payload, key)):
        try:
            title = clean_text(raw.get("title")) or f"Untitled {kind}"
            item = TrafficItem(
                id=_unique_id(raw, f"{road}-{kind}-{index}", seen),
                kind=kind,
                title=title,
                subtitle=clean_text(raw.get("subtitle")),
                details=text_lines(raw.get("description")) + text_lines(raw.get("footer")),
                point=extract_point(raw),
                planned=_flag(raw.get("future")),
                blocked=_flag(raw.get("isBlocked")),
                api_id=clean_text(raw.get("identifier")) or "",
            )
        except (TypeError, ValueError):
            continue
        items.append(item)
    return items


def parse_roadworks(payload: dict, road: str) -> list[TrafficItem]:
    return _parse_events(payload, road, "roadworks", "roadwork")


def parse_warnings(payload: dict, road: str) -> list[TrafficItem]:
    return _parse_events(payload, road, "warning", "warning")


def parse_closures(payload: dict, road: str) -> list[TrafficItem]:
    return _parse_events(payload, road, "closure", "closure")


def _http_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.startswith(("http://", "https://")):
        return text
    return None


def parse_webcams(payload: dict, road: str) -> list[Webcam]:
    seen: set[str] = set()
    cameras: list[Webcam] = []
    for index, raw in enumerate(_records(payload, "webcam")):
        try:
            details = text_lines(raw.get("description")) + text_lines(raw.get("footer"))
            operator = clean_text(raw.get("operator"))
            if operator:
                details = [f"Operator: {operator}", *details]
            camera = Webcam(
                id=_unique_id(raw, f"{road}-webcam-{index}", seen),
                title=clean_text(raw.get("title")) or "Webcam",
                subtitle=clean_text(raw.get("subtitle")),
                image_url=_http_url(raw.get("imageurl") or raw.get("imageUrl")),
                link_url=_http_url(raw.get("linkurl") or raw.get("linkUrl")),
                point=extract_point(raw),
                details=details,
                api_id=clean_text(raw.get("identifier")) or "",
            )
        except (TypeError, ValueError):
            continue
        cameras.append(camera)
    return cameras
