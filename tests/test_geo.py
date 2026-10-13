from parking_finder.filters import filter_parking, filter_traffic, rank_parking
from parking_finder.formatters import format_distance, google_maps_url, popup_html, ranking_message
from parking_finder.geo import haversine_km
from parking_finder.models import GeoPoint, ParkingArea, TrafficItem


def _area(name: str, lat: float | None, lng: float | None) -> ParkingArea:
    point = None if lat is None else GeoPoint(lat, lng)  # type: ignore[arg-type]
    return ParkingArea(
        id=name,
        name=name,
        road="A7",
        location=None,
        direction=None,
        point=point,
        availability="Availability unknown",
        truck_spaces=None,
        car_spaces=None,
    )


def test_haversine_berlin_munich_is_about_500_km():
    km = haversine_km(52.52, 13.405, 48.137, 11.575)
    assert 490 < km < 520


def test_rank_without_origin_is_alphabetical_and_clears_distance():
    areas = rank_parking([_area("Zed", 48.0, 11.0), _area("Ada", 53.0, 10.0)], None)
    assert [area.name for area in areas] == ["Ada", "Zed"]
    assert areas[0].distance_km is None


def test_rank_puts_nearest_first_and_missing_coordinates_last():
    origin = GeoPoint(52.52, 13.405)
    near = _area("Near", 52.53, 13.41)
    far = _area("Far", 48.14, 11.58)
    missing = _area("Nowhere", None, None)
    ranked = rank_parking([far, missing, near], origin)
    assert [area.name for area in ranked] == ["Near", "Far", "Nowhere"]
    assert ranked[0].distance_km < ranked[1].distance_km
    assert ranked[2].distance_km is None


def test_filter_parking_matches_name_only():
    areas = [_area("Grundbergsee", 53.0, 9.0), _area("Other", 52.0, 10.0)]
    assert [area.name for area in filter_parking(areas, "grund")] == ["Grundbergsee"]
    assert len(filter_parking(areas, "  ")) == 2


def test_filter_traffic_kind_and_planned():
    items = [
        TrafficItem("1", "roadwork", "Night", "North", [], None, True, False),
        TrafficItem("2", "warning", "Queue", "South", ["stockend"], None, False, False),
    ]
    assert len(filter_traffic(items, kind="warning", when="all", query="")) == 1
    assert len(filter_traffic(items, kind="all", when="planned", query="")) == 1
    assert len(filter_traffic(items, kind="all", when="active", query="queue")) == 1
    assert filter_traffic(items, kind="all", when="all", query="missing") == []


def test_distance_and_maps_url():
    assert format_distance(0.24) == "240 m"
    assert format_distance(3.26) == "3.3 km"
    url = google_maps_url(GeoPoint(52.5, 13.4))
    assert url.startswith("https://www.google.com/maps/dir/")
    assert "destination=52.500000,13.400000" in url
    assert "origin=" not in url
    assert "travelmode=driving" in url
    routed = google_maps_url(GeoPoint(52.5, 13.4), GeoPoint(52.52, 13.405))
    assert "origin=52.520000,13.405000" in routed
    assert "destination=52.500000,13.400000" in routed


def test_popup_escapes_api_text():
    html = popup_html("<script>", ["a&b"], "https://example.test/?q=1&x=2")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "a&amp;b" in html
    assert "https://example.test/?q=1&amp;x=2" in html


def test_ranking_message_when_coordinates_missing():
    text = ranking_message(has_origin=False, missing_coordinates=0)
    assert "Coordinates are unavailable" in text
    ranked = ranking_message(has_origin=True, missing_coordinates=2)
    assert "straight-line" in ranked
    assert "2 parking areas" in ranked
