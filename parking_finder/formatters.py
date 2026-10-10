"""Display strings. Kept separate so the UI does not invent wording."""

import html

from parking_finder.models import GeoPoint, ParkingArea

NOT_PROVIDED = "Not provided"


def format_distance(km: float) -> str:
    if km < 1:
        return f"{max(1, round(km * 1000))} m"
    if km < 10:
        return f"{km:.1f} km"
    return f"{km:.0f} km"


def format_coordinates(point: GeoPoint | None) -> str:
    if point is None:
        return NOT_PROVIDED
    return f"{point.lat:.5f}, {point.lng:.5f}"


def google_maps_url(point: GeoPoint) -> str:
    """Driving directions to the stop. Google uses the device's real location as the start."""
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&destination={point.lat:.6f},{point.lng:.6f}&travelmode=driving"
    )


def ranking_message(*, has_origin: bool, missing_coordinates: int) -> str:
    if not has_origin:
        return (
            "Coordinates are unavailable, so parking areas are not ranked by distance. "
            "Allow location access or enter latitude and longitude."
        )
    text = (
        "Ranked by approximate straight-line distance. "
        "Proximity does not guarantee road access from your direction of travel."
    )
    if missing_coordinates:
        noun = "area has" if missing_coordinates == 1 else "areas have"
        text += f" {missing_coordinates} parking {noun} no coordinates and stay at the end of the list."
    return text


def show(value: str | None) -> str:
    if value is None or not str(value).strip():
        return NOT_PROVIDED
    return str(value).strip()


def popup_html(title: str, lines: list[str], maps_url: str | None) -> str:
    """Leaflet popup HTML. API text is escaped."""
    rows = "".join(f"<div>{html.escape(line)}</div>" for line in lines if line)
    link = ""
    if maps_url:
        safe = html.escape(maps_url, quote=True)
        link = (
            f'<div style="margin-top:8px"><a href="{safe}" target="_blank" '
            'rel="noopener noreferrer">Open in Google Maps</a></div>'
        )
    return (
        '<div style="min-width:190px;font-family:Barlow,Segoe UI,sans-serif">'
        f"<strong>{html.escape(title)}</strong>{rows}{link}</div>"
    )


def parking_popup(area: ParkingArea) -> str:
    lines = [
        f"Autobahn {area.road}",
        f"Direction: {show(area.direction)}",
        area.availability,
    ]
    if area.distance_km is not None:
        lines.append(format_distance(area.distance_km) + " away (straight line)")
    elif area.point is None:
        lines.append("Coordinates: Not provided")
    url = google_maps_url(area.point) if area.point else None
    return popup_html(area.name, lines, url)
