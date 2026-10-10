"""Plain data objects shared by the API parser and the UI."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GeoPoint:
    """A WGS84 position. Latitude first, then longitude."""

    lat: float
    lng: float


@dataclass
class ParkingArea:
    """One truck parking area, already normalized for display."""

    id: str
    name: str
    road: str
    location: str | None
    direction: str | None
    point: GeoPoint | None
    availability: str
    truck_spaces: int | None
    car_spaces: int | None
    features: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)
    blocked: bool = False
    planned: bool = False
    api_id: str = ""
    distance_km: float | None = None


@dataclass
class TrafficItem:
    """A roadwork, warning, or closure on one Autobahn."""

    id: str
    kind: str
    title: str
    subtitle: str | None
    details: list[str]
    point: GeoPoint | None
    planned: bool
    blocked: bool
    api_id: str = ""


@dataclass
class Webcam:
    """A traffic camera. Image and link may both be missing."""

    id: str
    title: str
    subtitle: str | None
    image_url: str | None
    link_url: str | None
    point: GeoPoint | None
    details: list[str] = field(default_factory=list)
    api_id: str = ""
