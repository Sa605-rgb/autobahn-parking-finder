"""Opening screen. Road first, then a location, then the nearest stop."""

from collections.abc import Callable
from dataclasses import dataclass

from nicegui import ui

CITIES: tuple[tuple[str, float, float], ...] = (
    ("Berlin", 52.5200, 13.4050),
    ("Hamburg", 53.5511, 9.9937),
    ("Frankfurt", 50.1109, 8.6821),
    ("Cologne", 50.9375, 6.9603),
    ("Munich", 48.1351, 11.5820),
)

POPULAR_ROADS = ("A1", "A2", "A3", "A4", "A5", "A6", "A7")


@dataclass
class StartScreen:
    root: ui.element
    road: ui.select
    roads: dict
    lat: ui.number
    lng: ui.number
    status: ui.label


def build_start_screen(
    *,
    on_road: Callable,
    on_chip: Callable[[str], None],
    on_locate: Callable,
    on_city: Callable[[str, float, float], None],
    on_apply: Callable,
) -> StartScreen:
    """Full-screen first step. Hidden once a road and a location both exist."""
    road_buttons: dict = {}
    with ui.element("div").classes("start-screen") as root:
        with ui.element("div").classes("start-card"):
            ui.label("Find the nearest truck stop").classes("start-title")
            ui.label("Tap a road, then where you are. The nearest stop opens on the map.").classes("help")
            ui.label("1. Which Autobahn?").classes("step-label")
            with ui.row().classes("city-row"):
                for name in POPULAR_ROADS:
                    road_buttons[name] = ui.button(
                        name,
                        on_click=lambda name=name: on_chip(name),
                    ).props("outline")
            road = ui.select(
                options=[],
                label="Another road",
                with_input=True,
                on_change=on_road,
            ).classes("w-full").props('use-input fill-input hide-selected input-debounce="150"')
            ui.label("2. Where are you?").classes("step-label")
            ui.button("Use my location", icon="my_location", on_click=on_locate).classes("w-full")
            with ui.row().classes("city-row"):
                for name, lat, lng in CITIES:
                    ui.button(
                        name,
                        on_click=lambda name=name, lat=lat, lng=lng: on_city(name, lat, lng),
                    ).props("outline")
            with ui.row().classes("w-full"):
                lat_input = ui.number(label="Latitude", format="%.5f", min=-90, max=90, step=0.00001).classes("grow")
                lng_input = ui.number(label="Longitude", format="%.5f", min=-180, max=180, step=0.00001).classes("grow")
            ui.button("Use these coordinates", on_click=on_apply).props("outline").classes("w-full")
            status = ui.label("Tap any road from A1 to A7, then your location.").classes("rank-note")
    return StartScreen(root, road, road_buttons, lat_input, lng_input, status)
