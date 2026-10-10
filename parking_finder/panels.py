"""Card, list, and map rendering. Containers are cleared and rebuilt."""

from collections.abc import Callable

from nicegui import ui

from parking_finder.formatters import (
    format_coordinates,
    format_distance,
    google_maps_url,
    parking_popup,
    popup_html,
    show,
)
from parking_finder.models import ParkingArea, TrafficItem, Webcam

KIND_LABEL = {
    "roadwork": "Roadwork",
    "warning": "Warning",
    "closure": "Closure",
}

MARKER_STYLE = {
    "parking": {"color": "#0c2340", "fillColor": "#ffcc00", "radius": 8},
    "roadwork": {"color": "#9a3412", "fillColor": "#fb923c", "radius": 6},
    "warning": {"color": "#991b1b", "fillColor": "#f87171", "radius": 6},
    "closure": {"color": "#5b21b6", "fillColor": "#c4b5fd", "radius": 6},
    "webcam": {"color": "#075985", "fillColor": "#38bdf8", "radius": 6},
    "you": {"color": "#065f46", "fillColor": "#34d399", "radius": 9},
}


def _field(label: str, value: str) -> None:
    with ui.row().classes("w-full items-start gap-2"):
        ui.label(label).classes("field-label")
        ui.label(value).classes("field-value")


def _maps_link(point) -> None:
    if point is None:
        ui.label("Navigation unavailable — the API did not send coordinates.").classes("fine-print")
        return
    ui.link("Open in Google Maps", google_maps_url(point), new_tab=True).classes("nav-link")


def render_summary(box, session) -> None:
    box.clear()
    with box:
        if session.road is None:
            ui.label("No Autobahn selected yet").classes("stat")
            return
        ui.label(f"{session.road}").classes("stat")
        ui.label(f"{len(session.parking)} parking").classes("stat")
        ui.label(f"{sum(1 for item in session.traffic if item.kind == 'roadwork')} roadworks").classes("stat")
        ui.label(f"{sum(1 for item in session.traffic if item.kind == 'warning')} warnings").classes("stat")
        ui.label(f"{sum(1 for item in session.traffic if item.kind == 'closure')} closures").classes("stat")
        ui.label(f"{len(session.webcams)} webcams").classes("stat")


def render_parking(
    box,
    session,
    areas: list[ParkingArea],
    *,
    on_focus: Callable[[ParkingArea], None],
    on_more: Callable[[], None],
) -> None:
    box.clear()
    with box:
        if session.parking_error and not session.parking:
            ui.label(session.parking_error).classes("section-error")
            return
        if session.road is None:
            ui.label("Choose an Autobahn to load truck parking areas.").classes("empty-copy")
            return
        if not session.parking:
            ui.label(f"No truck parking areas were returned for {session.road}.").classes("empty-copy")
            return
        if not areas:
            ui.label("Nothing matches that filter.").classes("empty-copy")
            return

        shown = areas[: session.limit]
        ui.label(f"Showing {len(shown)} of {len(areas)}").classes("fine-print")
        with ui.element("div").classes("card-grid"):
            for index, area in enumerate(shown):
                _parking_card(area, nearest=index == 0 and area.distance_km is not None, on_focus=on_focus)
        if len(areas) > session.limit:
            remaining = len(areas) - session.limit
            ui.button(f"Show more ({remaining} left)", on_click=on_more).props("outline")


def _parking_card(area: ParkingArea, *, nearest: bool, on_focus: Callable[[ParkingArea], None]) -> None:
    with ui.element("article").classes("spot-card"):
        with ui.row().classes("w-full items-start justify-between"):
            ui.label(area.name).classes("spot-name")
            if area.distance_km is not None:
                ui.label(format_distance(area.distance_km)).classes("distance-pill")
        with ui.row().classes("gap-1"):
            if nearest:
                ui.badge("Nearest").props("color=primary")
            if area.blocked:
                ui.badge("Marked blocked").props("color=negative")
            if area.planned:
                ui.badge("Planned").props("color=warning")
        _field("Autobahn", area.road)
        _field("Location", show(area.location))
        _field("Direction", show(area.direction))
        _field("Availability", area.availability)
        if area.truck_spaces is not None:
            _field("Truck spaces", f"{area.truck_spaces} listed (capacity, not free)")
        else:
            _field("Truck spaces", "Not provided")
        if area.car_spaces is not None:
            _field("Car spaces", f"{area.car_spaces} listed (capacity, not free)")
        _field("Coordinates", format_coordinates(area.point))
        if area.features:
            ui.label(", ".join(area.features)).classes("fine-print")
        if area.details or area.api_id:
            with ui.expansion("More from the API").classes("w-full"):
                for line in area.details:
                    ui.label(line).classes("fine-print")
                if area.api_id:
                    ui.label(f"API id: {area.api_id}").classes("fine-print")
        with ui.row().classes("items-center gap-2"):
            ui.button("Show on map", on_click=lambda area=area: on_focus(area)).props("flat color=primary")
        _maps_link(area.point)


def render_traffic(
    box,
    session,
    items: list[TrafficItem],
    *,
    on_focus: Callable[[TrafficItem], None],
    on_more: Callable[[], None],
) -> None:
    box.clear()
    with box:
        if session.traffic_error and not session.traffic:
            ui.label(session.traffic_error).classes("section-error")
            return
        if session.road is None:
            ui.label("Roadworks, warnings, and closures load with the selected Autobahn.").classes("empty-copy")
            return
        if not session.traffic:
            ui.label(f"No roadworks, warnings, or closures were returned for {session.road}.").classes("empty-copy")
            return
        if not items:
            ui.label("Nothing matches that filter.").classes("empty-copy")
            return
        shown = items[: session.traffic_limit]
        ui.label(f"Showing {len(shown)} of {len(items)} messages").classes("fine-print")
        for item in shown:
            _traffic_card(item, on_focus)
        if len(items) > session.traffic_limit:
            remaining = len(items) - session.traffic_limit
            ui.button(f"Show more ({remaining} left)", on_click=on_more).props("outline")


def _traffic_card(item: TrafficItem, on_focus: Callable[[TrafficItem], None]) -> None:
    with ui.card().classes("w-full"):
        with ui.row().classes("items-center gap-2"):
            ui.badge(KIND_LABEL.get(item.kind, item.kind))
            ui.badge("Planned" if item.planned else "Active")
            if item.blocked:
                ui.badge("Blocked flag").props("color=negative")
        ui.label(item.title).classes("text-base font-bold")
        _field("Direction", show(item.subtitle))
        _field("Coordinates", format_coordinates(item.point))
        if item.details:
            ui.label(item.details[0]).classes("fine-print")
            if len(item.details) > 1:
                with ui.expansion("Full message").classes("w-full"):
                    for line in item.details:
                        ui.label(line).classes("fine-print")
        with ui.row().classes("items-center"):
            ui.button("Show on map", on_click=lambda item=item: on_focus(item)).props("flat color=primary")
        _maps_link(item.point)


def render_webcams(box, session, cameras: list[Webcam], *, on_focus: Callable[[Webcam], None]) -> None:
    box.clear()
    with box:
        if session.webcam_error and not session.webcams:
            ui.label(session.webcam_error).classes("section-error")
            return
        if session.road is None:
            ui.label("Cameras load with the selected Autobahn.").classes("empty-copy")
            return
        if not session.webcams:
            ui.label(
                f"No webcams were returned for {session.road}. "
                "When the API sends an image or a link, it shows up here."
            ).classes("empty-copy")
            return
        if not cameras:
            ui.label("Nothing matches that filter.").classes("empty-copy")
            return
        with ui.element("div").classes("card-grid"):
            for camera in cameras:
                _webcam_card(camera, on_focus)


def _webcam_card(camera: Webcam, on_focus: Callable[[Webcam], None]) -> None:
    with ui.element("article").classes("spot-card"):
        ui.label(camera.title).classes("spot-name")
        ui.label(show(camera.subtitle)).classes("fine-print")
        if camera.image_url:
            ui.image(camera.image_url).classes("webcam-shot")
            ui.label("If the preview stays blank, the camera host blocked it.").classes("fine-print")
        else:
            ui.label("No preview image from the API.").classes("fine-print")
        if camera.link_url:
            ui.link("Open camera link", camera.link_url, new_tab=True).classes("ghost-link")
        else:
            ui.label("No camera link from the API.").classes("fine-print")
        for line in camera.details[:3]:
            ui.label(line).classes("fine-print")
        ui.button("Show on map", on_click=lambda camera=camera: on_focus(camera)).props("flat color=primary")
        _maps_link(camera.point)


def clear_data_layers(leaflet, layers: list) -> None:
    for layer in list(layers):
        try:
            leaflet.remove_layer(layer)
        except ValueError:
            continue
    layers.clear()


def render_map(session, parking: list[ParkingArea], traffic: list[TrafficItem], webcams: list[Webcam], *, fit: bool) -> None:
    """Draw the current layers. The base map tiles are left in place."""
    leaflet = session.leaflet
    if leaflet is None or not session.map_ready:
        return
    clear_data_layers(leaflet, session.data_layers)
    session.marker_ids = {}
    points: list[tuple[float, float]] = []

    if session.show_parking:
        for area in parking:
            if area.point is None:
                continue
            layer = _dot(leaflet, area.point.lat, area.point.lng, "parking", parking_popup(area))
            session.data_layers.append(layer)
            session.marker_ids[area.id] = layer.id
            points.append((area.point.lat, area.point.lng))

    if session.show_roadworks or session.show_warnings or session.show_closures:
        for item in traffic:
            visible = (
                (item.kind == "roadwork" and session.show_roadworks)
                or (item.kind == "warning" and session.show_warnings)
                or (item.kind == "closure" and session.show_closures)
            )
            if not visible or item.point is None:
                continue
            lines = [KIND_LABEL.get(item.kind, item.kind), show(item.subtitle)]
            if item.details:
                lines.append(item.details[0])
            url = google_maps_url(item.point)
            layer = _dot(leaflet, item.point.lat, item.point.lng, item.kind, popup_html(item.title, lines, url))
            session.data_layers.append(layer)
            session.marker_ids[item.id] = layer.id
            points.append((item.point.lat, item.point.lng))

    if session.show_webcams:
        for camera in webcams:
            if camera.point is None:
                continue
            lines = [show(camera.subtitle)]
            if camera.link_url:
                lines.append("Camera link available on the card")
            url = google_maps_url(camera.point)
            layer = _dot(leaflet, camera.point.lat, camera.point.lng, "webcam", popup_html(camera.title, lines, url))
            session.data_layers.append(layer)
            session.marker_ids[camera.id] = layer.id
            points.append((camera.point.lat, camera.point.lng))

    if session.origin is not None:
        origin = session.origin
        layer = _dot(
            leaflet,
            origin.lat,
            origin.lng,
            "you",
            popup_html("Your position", ["Used only to rank distance"], None),
        )
        session.data_layers.append(layer)
        points.append((origin.lat, origin.lng))

    if not fit:
        return
    if len(points) == 1:
        leaflet.set_center(points[0])
        leaflet.set_zoom(11)
    elif len(points) > 1:
        leaflet.run_map_method(
            "fitBounds",
            [[lat, lng] for lat, lng in points],
            {"padding": [28, 28], "maxZoom": 11},
        )


def _dot(leaflet, lat: float, lng: float, kind: str, popup: str):
    style = MARKER_STYLE[kind]
    layer = leaflet.generic_layer(
        name="circleMarker",
        args=[[lat, lng], {**style, "weight": 2, "fillOpacity": 0.95}],
    )
    layer.run_method("bindPopup", popup)
    return layer
