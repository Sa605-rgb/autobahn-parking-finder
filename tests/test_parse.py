"""Parser tests use the shapes the live Autobahn API actually returns."""

from parking_finder.parse import (
    availability_text,
    extract_point,
    parse_closures,
    parse_parking,
    parse_roadworks,
    parse_warnings,
    parse_webcams,
    road_sort_key,
)


LIVE_PARKING = {
    "identifier": "DE-BY-000264",
    "icon": "314-50",
    "isBlocked": "false",
    "future": False,
    "display_type": "PARKING",
    "subtitle": "Rottachtal-West",
    "title": "A7 | undefined",
    "coordinate": {"type": "Point", "coordinates": [10.416492, 47.663936]},
    "description": ["PKW Stellplätze: 20", "LKW Stellplätze: 8"],
    "footer": ["Koordinaten: undefined"],
    "lorryParkingFeatureIcons": [
        {"icon": "almofont almo-restroom", "description": "Toilette vorhanden", "style": ""}
    ],
}


def test_road_sort_puts_a2_before_a10():
    roads = ["A10", "A2", "A1", "B9"]
    assert sorted(roads, key=road_sort_key) == ["A1", "A2", "A10", "B9"]


def test_live_parking_record_uses_subtitle_and_geojson():
    areas = parse_parking({"parking_lorry": [LIVE_PARKING]}, "A7")
    assert len(areas) == 1
    area = areas[0]
    assert area.name == "Rottachtal-West"
    assert area.road == "A7"
    assert area.location is None
    assert area.direction is None
    assert area.point is not None
    assert abs(area.point.lat - 47.663936) < 1e-6
    assert abs(area.point.lng - 10.416492) < 1e-6
    assert area.truck_spaces == 8
    assert area.car_spaces == 20
    assert area.availability == "Availability unknown"
    assert area.details == []
    assert area.features == ["Toilette vorhanden"]
    assert area.blocked is False


def test_capacity_is_not_treated_as_free_spaces():
    raw = {"description": ["LKW Stellplätze: 40"], "title": "Lot"}
    assert availability_text(raw) == "Availability unknown"


def test_occupancy_field_is_quoted_and_not_a_guarantee():
    text = availability_text({"freeSpaces": 3})
    assert text.startswith("Availability reported: 3")
    assert "not a guarantee" in text


def test_old_coordinate_object_and_direction():
    raw = {
        "title": "A 1 | Richtung Puttgarden",
        "subtitle": "(Ostseeblick S)",
        "coordinate": {"lat": "54.362572", "long": "10.979850"},
        "isBlocked": "true",
        "future": True,
    }
    area = parse_parking({"parking_lorry": [raw]}, "A1")[0]
    assert area.name == "(Ostseeblick S)"
    assert "Richtung" in area.direction
    assert area.blocked is True
    assert area.planned is True
    assert abs(area.point.lat - 54.362572) < 1e-6
    assert abs(area.point.lng - 10.97985) < 1e-5


def test_point_string_accepts_both_orders():
    lng_lat = extract_point({"point": "10.979850,54.362572"})
    lat_lng = extract_point({"point": "54.362572,10.979850"})
    assert lng_lat is not None and lat_lng is not None
    assert abs(lng_lat.lat - 54.362572) < 1e-5
    assert abs(lat_lng.lat - 54.362572) < 1e-5
    assert abs(lng_lat.lng - lat_lng.lng) < 1e-5


def test_extent_center_when_coordinate_missing():
    point = extract_point({"extent": "47.50,10.60,47.70,10.80"})
    assert point is not None
    assert abs(point.lat - 47.60) < 1e-6
    assert abs(point.lng - 10.70) < 1e-6


def test_bad_records_are_skipped_instead_of_raising():
    payload = {
        "parking_lorry": [
            "nope",
            None,
            {"coordinate": {"type": "Point", "coordinates": ["x", "y"]}, "subtitle": "West"},
            {"title": None},
        ]
    }
    areas = parse_parking(payload, "A7")
    assert len(areas) == 2
    assert areas[0].name == "West"
    assert areas[0].point is None
    assert areas[1].name == "Unnamed parking area"


def test_duplicate_ids_stay_unique():
    raw = {"identifier": "same", "subtitle": "One"}
    areas = parse_parking({"parking_lorry": [raw, dict(raw, subtitle="Two")]}, "A3")
    assert areas[0].id != areas[1].id


def test_traffic_and_webcam_shapes():
    roadworks = parse_roadworks(
        {
            "roadworks": [
                {
                    "title": "A7 | Tunnel",
                    "subtitle": " Füssen -> Ulm",
                    "future": True,
                    "description": ["Night closure"],
                    "coordinate": {"lat": 47.55, "long": 10.65},
                }
            ]
        },
        "A7",
    )
    warnings = parse_warnings({"warning": [{"title": "Queue", "future": False}]}, "A7")
    closures = parse_closures({"closure": []}, "A7")
    cameras = parse_webcams(
        {
            "webcam": [
                {
                    "title": "A1 | Köln",
                    "subtitle": "Blickrichtung Dortmund",
                    "imageurl": "https://example.test/cam.jpg",
                    "linkurl": "javascript:alert(1)",
                    "operator": "NRW",
                },
                {"title": "No media"},
            ]
        },
        "A1",
    )
    assert roadworks[0].kind == "roadwork"
    assert roadworks[0].planned is True
    assert roadworks[0].point is not None
    assert warnings[0].kind == "warning"
    assert closures == []
    assert cameras[0].image_url == "https://example.test/cam.jpg"
    assert cameras[0].link_url is None
    assert cameras[0].details[0] == "Operator: NRW"
    assert cameras[1].image_url is None
    assert cameras[1].link_url is None
