from fastapi.routing import APIRoute
from datetime import datetime, timezone

from app.main import app
from app.security import require_admin
from app.schemas import AirSensorCurrent


def test_sensitive_public_endpoints_are_not_registered() -> None:
    paths = {route.path for route in app.routes}

    assert '/api/devices/public/status' not in paths
    assert '/api/measurements/public/latest' not in paths
    assert '/api/measurements/public/summary' in paths


def _route(path: str, method: str) -> APIRoute:
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and method in route.methods:
            return route
    raise AssertionError(f'route not found: {method} {path}')


def test_kindle_control_endpoints_are_admin_only() -> None:
    for path, method in [('/api/kindle/refresh', 'POST'), ('/api/kindle/meta', 'GET')]:
        route = _route(path, method)
        assert any(dependency.call is require_admin for dependency in route.dependant.dependencies)


def test_kindle_display_png_remains_public_cache_only_endpoint() -> None:
    route = _route('/api/kindle/display.png', 'GET')
        
    assert not any(dependency.call is require_admin for dependency in route.dependant.dependencies)


def test_public_dashboard_settings_normalizes_meter_number() -> None:
    from app.routers.settings import _normalize_public_dashboard_value

    settings = _normalize_public_dashboard_value({'enabled': True, 'meter_number': '  DE-2026-001337  '})

    assert settings.enabled is True
    assert settings.meter_number == 'DE-2026-001337'


def test_public_dashboard_settings_allows_empty_meter_number() -> None:
    from app.routers.settings import _normalize_public_dashboard_value

    settings = _normalize_public_dashboard_value({'enabled': True, 'meter_number': '   '})

    assert settings.enabled is True
    assert settings.meter_number is None


def test_air_sensor_weather_underground_key_is_not_exposed() -> None:
    from app.routers.settings import DEFAULT_WEATHER_UNDERGROUND_UPLOAD_TEMPLATE, _normalize_air_sensor_value

    settings = _normalize_air_sensor_value({
        'enabled': True,
        'host': '192.168.178.60',
        'weather_underground_enabled': True,
        'weather_underground_station_id': ' idortmun123 ',
        'weather_underground_api_key_ciphertext': 'encrypted-value',
    })

    assert settings.weather_underground_enabled is True
    assert settings.weather_underground_station_id == 'IDORTMUN123'
    assert settings.weather_underground_api_key is None
    assert settings.weather_underground_api_key_set is True
    assert settings.weather_underground_upload_url == DEFAULT_WEATHER_UNDERGROUND_UPLOAD_TEMPLATE


def test_weather_underground_params_include_air_sensor_values() -> None:
    from app.routers.settings import _weather_underground_params, _weather_underground_upload_url, _normalize_air_sensor_value

    settings = _normalize_air_sensor_value({
        'weather_underground_enabled': True,
        'weather_underground_station_id': 'IDORTMUN123',
    })
    current = AirSensorCurrent(
        temperature_c=20.0,
        humidity_percent=54.4,
        pressure_hpa=1013.25,
        sds_p1=12.345,
        sds_p2=6.789,
    )

    params = _weather_underground_params(settings, current, 'secret-key', datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc))

    assert params['ID'] == 'IDORTMUN123'
    assert params['PASSWORD'] == 'secret-key'
    assert params['dateutc'] == '2026-08-23 12:00:00'
    assert params['tempf'] == '68.00'
    assert params['humidity'] == '54'
    assert params['baromin'] == '29.92'
    assert params['AqPM10'] == '12.35'
    assert params['AqPM2.5'] == '6.79'
    assert params['action'] == 'updateraw'

    upload_url = _weather_underground_upload_url(settings, current, 'secret-key', datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc))
    assert 'ID=IDORTMUN123' in upload_url
    assert 'PASSWORD=secret-key' in upload_url
    assert 'dateutc=2026-08-23+12%3A00%3A00' in upload_url
    assert 'baromin=29.92' in upload_url
