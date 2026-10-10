"""Coordinate parsing and straight-line distance."""

from math import asin, cos, radians, sin, sqrt

from parking_finder.models import GeoPoint

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Approximate distance in kilometres. This is not a driving route."""
    phi1, phi2 = radians(lat1), radians(lat2)
    d_phi = radians(lat2 - lat1)
    d_lng = radians(lng2 - lng1)
    a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def as_float(value: object) -> float | None:
    """Parse a single coordinate value. Reject bools and non-numeric text."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
    else:
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def valid_point(lat: float, lng: float) -> GeoPoint | None:
    if -90 <= lat <= 90 and -180 <= lng <= 180:
        return GeoPoint(lat, lng)
    return None


def order_pair(first: float, second: float) -> GeoPoint | None:
    """Decide which number is latitude for an unlabeled pair.

    The live API sends ``lat,lng``. Older samples sent ``lng,lat``.
    In Germany latitude is about 47–55 and longitude about 6–15, so the
    larger number is latitude when one value is clearly a European latitude.
    """
    if abs(first) > 90 and abs(second) <= 90:
        return valid_point(second, first)
    if abs(second) > 90 and abs(first) <= 90:
        return valid_point(first, second)
    if abs(first) > 90 or abs(second) > 180:
        return None
    if first > 35 and abs(second) <= 35:
        return valid_point(first, second)
    if second > 35 and abs(first) <= 35:
        return valid_point(second, first)
    return valid_point(first, second)


def from_lng_lat(lng: object, lat: object) -> GeoPoint | None:
    """Build a point from an explicit longitude, latitude pair (GeoJSON order)."""
    lng_f = as_float(lng)
    lat_f = as_float(lat)
    if lng_f is None or lat_f is None:
        return None
    return valid_point(lat_f, lng_f)
