"""Page layout and user actions for one browser session."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from nicegui import ui

from parking_finder.api import AutobahnClient, AutobahnError
from parking_finder.filters import filter_parking, filter_traffic, filter_webcams, rank_parking
from parking_finder.formatters import ranking_message
from parking_finder.models import GeoPoint, ParkingArea, TrafficItem, Webcam
from parking_finder.panels import render_map, render_parking, render_summary, render_traffic, render_webcams
from parking_finder.parse import parse_closures, parse_parking, parse_roadworks, parse_warnings, parse_webcams

logger = logging.getLogger("parking_finder")
_CSS = (Path(__file__).with_name("static") / "app.css").read_text(encoding="utf-8")

_FONT = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700'
    '&family=Barlow:wght@400;500;600;700&display=swap" rel="stylesheet">'
)

_GEO_JS = """
return await new Promise((resolve) => {
  if (!navigator.geolocation) {
    resolve({ok: false, error: "This browser does not support location access."});
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => resolve({ok: true, lat: pos.coords.latitude, lng: pos.coords.longitude}),
    (err) => resolve({ok: false, error: (err && err.message) ? err.message : "Location permission was denied."}),
    {enableHighAccuracy: false, timeout: 12000, maximumAge: 120000}
  );
});
"""


@dataclass
class Session:
    road: str | None = None
    origin: GeoPoint | None = None
    parking: list[ParkingArea] = field(default_factory=list)
    traffic: list[TrafficItem] = field(default_factory=list)
    webcams: list[Webcam] = field(default_factory=list)
    parking_error: str | None = None
    traffic_error: str | None = None
    webcam_error: str | None = None
    query: str = ""
    traffic_kind: str = "all"
    traffic_when: str = "all"
    traffic_query: str = ""
    webcam_query: str = ""
    show_parking: bool = True
    show_roadworks: bool = False
    show_warnings: bool = False
    show_closures: bool = False
    show_webcams: bool = False
    limit: int = 12
    traffic_limit: int = 20
    map_ready: bool = False
    leaflet: object | None = None
    data_layers: list = field(default_factory=list)
    marker_ids: dict = field(default_factory=dict)
    loaded_at: datetime | None = None
    token: int = 0


class Dashboard:
    def __init__(self, client: AutobahnClient) -> None:
        self.client = client
        self.session = Session()
        self._suppress = False
        self._checks: dict = {}
        self._loads = 0

    def build(self) -> None:
        ui.add_head_html(_FONT)
        ui.add_css(_CSS)
        self._header()
        with ui.element("div").classes("page-wrap"):
            self._sidebar()
            self._main()
        ui.label(
            "Source: Autobahn GmbH des Bundes · https://verkehr.autobahn.de/o/autobahn · "
            "No database · Straight-line distance only · Not an official navigation device."
        ).classes("footer-note")
        ui.timer(0.1, self._boot, once=True)

    def _header(self) -> None:
        with ui.element("header").classes("app-header"):
            with ui.element("div").classes("brand"):
                with ui.element("div").classes("mark"):
                    ui.icon("local_shipping").style("font-size: 28px; color: #0c2340")
                with ui.column().classes("gap-0"):
                    ui.label("TRUCK STOP").classes("eyebrow")
                    ui.label("Autobahn Parking Finder").classes("app-title")
            ui.label("Live parking, roadworks, warnings, closures, and cameras for German Autobahns.").classes("tagline")
        ui.html(
            "<div class='notice'><strong>Availability unknown</strong> unless a card quotes an occupancy "
            "field from the API. Stall counts are capacity, not free spaces. A nearby pin does not mean "
            "the lot is open from your direction of travel.</div>",
            sanitize=False,
        )

    def _sidebar(self) -> None:
        with ui.column().classes("sidebar gap-3"):
            ui.label("Find a stop").classes("panel-title")
            self.road_select = ui.select(
                options=[],
                label="Autobahn",
                with_input=True,
                on_change=self._on_road,
            ).classes("w-full").props('use-input fill-input hide-selected input-debounce="150"')
            self.road_status = ui.label("Loading the Autobahn list…").classes("help")
            with ui.row().classes("w-full"):
                self.load_button = ui.button("Reload", icon="refresh", on_click=self._reload).props("outline").classes("grow")
            ui.separator()
            ui.label("Your position").classes("panel-title")
            ui.label("Used only in this browser session to sort parking by straight-line distance.").classes("help")
            ui.button("Use my location", icon="my_location", on_click=self._use_browser_location).classes("w-full")
            self.location_status = ui.label("").classes("help")
            with ui.row().classes("w-full"):
                self.lat_input = ui.number(label="Latitude", format="%.5f", min=-90, max=90, step=0.00001).classes("grow")
                self.lng_input = ui.number(label="Longitude", format="%.5f", min=-180, max=180, step=0.00001).classes("grow")
            with ui.row().classes("w-full"):
                ui.button("Apply coordinates", on_click=self._apply_manual).props("outline").classes("grow")
                ui.button("Clear", on_click=self._clear_location).props("flat")
            self.rank_note = ui.label("").classes("rank-note")
            self._update_rank_note()
            ui.separator()
            ui.label("Filter parking").classes("panel-title")
            ui.input(
                label="Name or place",
                placeholder="e.g. Grundbergsee",
                on_change=self._on_query,
            ).classes("w-full")
            ui.label("Map layers").classes("panel-title")
            self._layer_box("Parking", "show_parking", True)
            self._layer_box("Roadworks", "show_roadworks", False)
            self._layer_box("Warnings", "show_warnings", False)
            self._layer_box("Closures", "show_closures", False)
            self._layer_box("Webcams", "show_webcams", False)
            self.banner = ui.label("").classes("banner")
            self.banner.set_visibility(False)

    def _layer_box(self, label: str, attr: str, value: bool) -> None:
        def changed(event, attr=attr) -> None:
            if self._suppress:
                return
            setattr(self.session, attr, bool(event.value))
            self._draw(fit=True)

        self._checks[attr] = ui.checkbox(label, value=value, on_change=changed)

    def _main(self) -> None:
        with ui.column().classes("main-col"):
            self.summary_box = ui.element("div").classes("stats")
            self.loading_row = ui.row().classes("items-center gap-2")
            with self.loading_row:
                ui.spinner(size="sm", color="primary")
                ui.label("Loading live Autobahn data…")
            self.loading_row.set_visibility(False)
            self.leaflet = ui.leaflet(
                center=(51.1657, 10.4515),
                zoom=6,
                options={"scrollWheelZoom": True},
            ).classes("map-frame")
            self.session.leaflet = self.leaflet
            with ui.row().classes("legend"):
                for label, color in (
                    ("You", "#34d399"),
                    ("Parking", "#ffcc00"),
                    ("Roadwork", "#fb923c"),
                    ("Warning", "#f87171"),
                    ("Closure", "#c4b5fd"),
                    ("Webcam", "#38bdf8"),
                ):
                    with ui.row().classes("items-center no-wrap gap-0"):
                        ui.element("span").classes("dot").style(f"background:{color}")
                        ui.label(label)
            with ui.tabs().classes("w-full") as tabs:
                parking_tab = ui.tab("Parking", icon="local_parking")
                traffic_tab = ui.tab("Traffic", icon="warning")
                webcam_tab = ui.tab("Webcams", icon="videocam")
            with ui.tab_panels(tabs, value=parking_tab).classes("w-full"):
                with ui.tab_panel(parking_tab):
                    self.parking_box = ui.column().classes("w-full")
                with ui.tab_panel(traffic_tab):
                    with ui.row().classes("w-full items-end gap-2"):
                        ui.select(
                            {"all": "All types", "roadwork": "Roadworks", "warning": "Warnings", "closure": "Closures"},
                            value="all",
                            label="Type",
                            on_change=self._on_kind,
                        ).classes("grow")
                        ui.select(
                            {"all": "Active and planned", "active": "Active only", "planned": "Planned only"},
                            value="all",
                            label="Status",
                            on_change=self._on_when,
                        ).classes("grow")
                    ui.input(label="Filter messages", on_change=self._on_traffic_query).classes("w-full")
                    self.traffic_box = ui.column().classes("w-full")
                with ui.tab_panel(webcam_tab):
                    ui.input(label="Filter cameras", on_change=self._on_webcam_query).classes("w-full")
                    self.webcam_box = ui.column().classes("w-full")
        self._paint_lists()

    async def _boot(self) -> None:
        await self.leaflet.initialized()
        self.session.map_ready = True
        self.leaflet.run_map_method("invalidateSize")
        await self._load_roads()

    async def _load_roads(self) -> None:
        self.road_status.set_text("Loading the Autobahn list…")
        try:
            roads = await self.client.list_roads()
        except AutobahnError as exc:
            self.road_status.set_text(str(exc))
            self._show_banner(str(exc))
            return
        if not roads:
            self.road_status.set_text("The API returned an empty road list.")
            self._show_banner("The Autobahn list was empty. Try Reload.")
            return
        self._suppress = True
        self.road_select.options = roads
        self.road_select.update()
        self._suppress = False
        self.road_status.set_text(f"{len(roads)} roads loaded. Pick one, for example A7.")
        self._hide_banner()

    async def _on_road(self, event) -> None:
        if self._suppress or not event.value:
            return
        await ui.run_javascript("document.activeElement && document.activeElement.blur()")
        await self._load_selected(event.value)

    async def _reload(self) -> None:
        if not self.road_select.options:
            await self._load_roads()
            return
        road = self.road_select.value
        if not road:
            ui.notify("Choose an Autobahn first.", type="warning")
            return
        await self._load_selected(road)

    async def _load_selected(self, road: str) -> None:
        self.session.token += 1
        token = self.session.token
        self.session.road = road
        self._loads += 1
        self.loading_row.set_visibility(True)
        self.load_button.disable()
        try:
            bundle = await self.client.load_road(road)
            if token != self.session.token:
                return
            self._apply_bundle(road, bundle)
        except Exception:
            logger.exception("Failed to load %s", road)
            if token == self.session.token:
                self._show_banner("Something unexpected went wrong while loading this Autobahn. Try Reload.")
        finally:
            self._loads = max(0, self._loads - 1)
            if self._loads == 0:
                self.loading_row.set_visibility(False)
                self.load_button.enable()

    def _apply_bundle(self, road: str, bundle: dict) -> None:
        parking_payload, parking_error = bundle["parking"]
        roadworks_payload, roadworks_error = bundle["roadworks"]
        warnings_payload, warnings_error = bundle["warnings"]
        closures_payload, closures_error = bundle["closures"]
        webcam_payload, webcam_error = bundle["webcams"]

        self.session.parking = rank_parking(parse_parking(parking_payload, road), self.session.origin)
        self.session.parking_error = parking_error
        traffic = (
            parse_roadworks(roadworks_payload, road)
            + parse_warnings(warnings_payload, road)
            + parse_closures(closures_payload, road)
        )
        self.session.traffic = traffic
        traffic_errors = [text for text in (roadworks_error, warnings_error, closures_error) if text]
        self.session.traffic_error = traffic_errors[0] if traffic_errors and not traffic else None
        self.session.webcams = parse_webcams(webcam_payload, road)
        self.session.webcam_error = webcam_error
        self.session.limit = 12
        self.session.traffic_limit = 20
        self.session.loaded_at = datetime.now()

        fatal = [text for text in (parking_error, *traffic_errors, webcam_error) if text]
        if fatal and not self.session.parking and not self.session.traffic and not self.session.webcams:
            self._show_banner(fatal[0])
        else:
            self._hide_banner()
        if fatal and (self.session.parking or self.session.traffic or self.session.webcams):
            self.road_status.set_text(f"Showing {road}, but one section failed. {fatal[0]}")
        else:
            self.road_status.set_text(f"Showing {road}. Loaded {self.session.loaded_at:%H:%M:%S}.")
        self._update_rank_note()
        self._paint_lists()
        self._draw(fit=True)

    async def _use_browser_location(self) -> None:
        self.location_status.set_text("Asking the browser for your location…")
        try:
            result = await ui.run_javascript(_GEO_JS, timeout=16.0)
        except Exception:
            result = {"ok": False, "error": "The location request timed out."}
        if isinstance(result, str):
            import json
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                result = {"ok": False, "error": "The browser returned an unreadable position."}
        if not isinstance(result, dict) or not result.get("ok"):
            message = result.get("error") if isinstance(result, dict) else None
            message = message or "Location permission was denied or is unavailable."
            self.location_status.set_text(f"{message} Enter latitude and longitude instead.")
            ui.notify(message, type="warning")
            return
        try:
            lat = float(result["lat"])
            lng = float(result["lng"])
        except (KeyError, TypeError, ValueError):
            self.location_status.set_text("The browser returned an unreadable position. Enter coordinates manually.")
            return
        self.lat_input.set_value(lat)
        self.lng_input.set_value(lng)
        self._set_origin(GeoPoint(lat, lng), f"Browser location {lat:.5f}, {lng:.5f}")

    def _apply_manual(self) -> None:
        lat = self.lat_input.value
        lng = self.lng_input.value
        if lat is None or lng is None:
            ui.notify("Enter both latitude and longitude.", type="warning")
            self.location_status.set_text("Coordinates are incomplete. Distance ranking stays unchanged.")
            return
        if not (-90 <= float(lat) <= 90 and -180 <= float(lng) <= 180):
            ui.notify("Latitude must be between -90 and 90, and longitude between -180 and 180.", type="warning")
            return
        point = GeoPoint(float(lat), float(lng))
        self._set_origin(point, f"Manual point {point.lat:.5f}, {point.lng:.5f}")

    def _clear_location(self) -> None:
        self.lat_input.set_value(None)
        self.lng_input.set_value(None)
        self.session.origin = None
        self.location_status.set_text("Location cleared.")
        self._rerank()

    def _set_origin(self, point: GeoPoint, label: str) -> None:
        self.session.origin = point
        self.location_status.set_text(label)
        self._rerank()

    def _rerank(self) -> None:
        self.session.parking = rank_parking(self.session.parking, self.session.origin)
        self.session.limit = 12
        self._update_rank_note()
        self._paint_lists()
        self._draw(fit=True)

    def _update_rank_note(self) -> None:
        missing = sum(1 for area in self.session.parking if area.point is None)
        self.rank_note.set_text(
            ranking_message(has_origin=self.session.origin is not None, missing_coordinates=missing)
        )

    def _on_query(self, event) -> None:
        self.session.query = event.value or ""
        self.session.limit = 12
        self._paint_parking()
        self._draw(fit=False)

    def _on_kind(self, event) -> None:
        self.session.traffic_kind = event.value or "all"
        self.session.traffic_limit = 20
        self._paint_traffic()
        self._draw(fit=False)

    def _on_when(self, event) -> None:
        self.session.traffic_when = event.value or "all"
        self.session.traffic_limit = 20
        self._paint_traffic()
        self._draw(fit=False)

    def _on_traffic_query(self, event) -> None:
        self.session.traffic_query = event.value or ""
        self.session.traffic_limit = 20
        self._paint_traffic()
        self._draw(fit=False)

    def _show_more_traffic(self) -> None:
        self.session.traffic_limit += 20
        self._paint_traffic()

    def _on_webcam_query(self, event) -> None:
        self.session.webcam_query = event.value or ""
        self._paint_webcams()
        self._draw(fit=False)

    def _show_more(self) -> None:
        self.session.limit += 12
        self._paint_parking()

    def _filtered_parking(self) -> list[ParkingArea]:
        return filter_parking(self.session.parking, self.session.query)

    def _filtered_traffic(self) -> list[TrafficItem]:
        return filter_traffic(
            self.session.traffic,
            kind=self.session.traffic_kind,
            when=self.session.traffic_when,
            query=self.session.traffic_query,
        )

    def _filtered_webcams(self) -> list[Webcam]:
        return filter_webcams(self.session.webcams, self.session.webcam_query)

    def _paint_lists(self) -> None:
        render_summary(self.summary_box, self.session)
        self._paint_parking()
        self._paint_traffic()
        self._paint_webcams()

    def _paint_parking(self) -> None:
        render_parking(
            self.parking_box,
            self.session,
            self._filtered_parking(),
            on_focus=self._focus,
            on_more=self._show_more,
        )

    def _paint_traffic(self) -> None:
        render_traffic(
            self.traffic_box,
            self.session,
            self._filtered_traffic(),
            on_focus=self._focus,
            on_more=self._show_more_traffic,
        )

    def _paint_webcams(self) -> None:
        render_webcams(self.webcam_box, self.session, self._filtered_webcams(), on_focus=self._focus)

    def _draw(self, *, fit: bool) -> None:
        render_map(
            self.session,
            self._filtered_parking(),
            self._filtered_traffic(),
            self._filtered_webcams(),
            fit=fit,
        )

    def _focus(self, item) -> None:
        point = item.point
        if point is None:
            ui.notify("This record has no coordinates, so it cannot be placed on the map.", type="warning")
            return
        self._enable_layer_for(item)
        self.leaflet.set_center((point.lat, point.lng))
        self.leaflet.set_zoom(13)
        self._draw(fit=False)
        layer_id = self.session.marker_ids.get(item.id)
        if layer_id:
            self.leaflet.run_layer_method(layer_id, "openPopup")
        ui.run_javascript(
            'document.querySelector(".nicegui-leaflet")?.scrollIntoView({behavior:"smooth", block:"center"})'
        )

    def _enable_layer_for(self, item) -> None:
        if isinstance(item, ParkingArea):
            attr = "show_parking"
        elif isinstance(item, TrafficItem):
            attr = {"roadwork": "show_roadworks", "warning": "show_warnings", "closure": "show_closures"}.get(item.kind)
        elif isinstance(item, Webcam):
            attr = "show_webcams"
        else:
            attr = None
        if not attr or getattr(self.session, attr):
            return
        setattr(self.session, attr, True)
        checkbox = self._checks.get(attr)
        if checkbox is None:
            return
        self._suppress = True
        checkbox.set_value(True)
        self._suppress = False

    def _show_banner(self, message: str) -> None:
        self.banner.set_text(message)
        self.banner.set_visibility(True)
        ui.notify(message, type="negative", timeout=6000)

    def _hide_banner(self) -> None:
        self.banner.set_visibility(False)
