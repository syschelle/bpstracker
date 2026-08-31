from fastapi.routing import APIRoute
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import AppSetting
from app.routers import current_values
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
    from app.routers.settings import DEFAULT_WEATHER_UNDERGROUND_UPLOAD_TEMPLATE, LEGACY_WEATHER_UNDERGROUND_UPLOAD_TEMPLATE_NO_DEWPOINT, _apply_weather_underground_api_key_update, _normalize_air_sensor_value

    settings = _normalize_air_sensor_value({
        'enabled': True,
        'host': '192.168.178.60',
        'weather_underground_enabled': True,
        'weather_underground_station_id': ' idortmun123 ',
        'weather_underground_api_key_ciphertext': 'encrypted-value',
    })

    assert settings.weather_underground_enabled is True
    assert settings.altitude_m is None
    assert settings.weather_underground_station_id == 'IDORTMUN123'
    assert settings.weather_underground_api_key is None
    assert settings.weather_underground_api_key_set is True
    assert settings.weather_underground_upload_url == DEFAULT_WEATHER_UNDERGROUND_UPLOAD_TEMPLATE
    migrated = _normalize_air_sensor_value({'weather_underground_upload_url': LEGACY_WEATHER_UNDERGROUND_UPLOAD_TEMPLATE_NO_DEWPOINT})
    assert migrated.weather_underground_upload_url == DEFAULT_WEATHER_UNDERGROUND_UPLOAD_TEMPLATE

    raw_value = {'weather_underground_api_key': '', 'weather_underground_api_key_set': True}
    changed = _apply_weather_underground_api_key_update(raw_value, {'weather_underground_api_key_ciphertext': 'encrypted-value'})
    assert changed is False
    assert raw_value['weather_underground_api_key_ciphertext'] == 'encrypted-value'
    assert 'weather_underground_api_key' not in raw_value
    assert 'weather_underground_api_key_set' not in raw_value


def test_weather_underground_params_include_air_sensor_values() -> None:
    from app.routers.settings import _dew_point_c, _pressure_hpa_from_value, _sea_level_pressure_hpa, _weather_underground_params, _weather_underground_status, _weather_underground_upload_url, _normalize_air_sensor_value

    settings = _normalize_air_sensor_value({
        'weather_underground_enabled': True,
        'weather_underground_station_id': 'IDORTMUN123',
        'altitude_m': 300,
    })
    current = AirSensorCurrent(
        temperature_c=20.0,
        humidity_percent=54.4,
        dew_point_c=_dew_point_c(20.0, 54.4),
        pressure_hpa=1013.25,
        pressure_sea_level_hpa=_sea_level_pressure_hpa(1013.25, settings.altitude_m),
        sds_p1=12.345,
        sds_p2=6.789,
    )

    params = _weather_underground_params(settings, current, 'secret-key', datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc))

    assert params['ID'] == 'IDORTMUN123'
    assert params['PASSWORD'] == 'secret-key'
    assert params['dateutc'] == '2026-08-23 12:00:00'
    assert params['tempf'] == '68.00'
    assert params['humidity'] == '54'
    assert current.dew_point_c == 10.5
    assert params['dewptf'] == '50.9'
    assert current.pressure_sea_level_hpa == 1050.1
    assert params['baromin'] == '31.01'
    assert params['AqPM10'] == '12.35'
    assert params['AqPM2.5'] == '6.79'
    assert params['action'] == 'updateraw'

    upload_url = _weather_underground_upload_url(settings, current, 'secret-key', datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc))
    assert 'ID=IDORTMUN123' in upload_url
    assert 'PASSWORD=secret-key' in upload_url
    assert 'dateutc=2026-08-23+12%3A00%3A00' in upload_url
    assert 'dewptf=50.9' in upload_url
    assert 'baromin=31.01' in upload_url
    assert _pressure_hpa_from_value('98607') == 986.07
    assert _sea_level_pressure_hpa(1013.25, None) == 1013.2

    status = _weather_underground_status(False, datetime(2026, 8, 23, 12, 1, tzinfo=timezone.utc), status=401, response='Unauthorized')
    assert status['weather_underground_last_ok'] is False
    assert status['weather_underground_last_status'] == 401
    assert status['weather_underground_last_response'] == 'Unauthorized'


def test_current_values_api_includes_enabled_air_sensor_cache() -> None:
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    last_success_at = datetime.now(timezone.utc).isoformat()

    with SessionLocal() as db:
        db.add(AppSetting(key='current_values_api', value={'enabled': True}))
        db.add(AppSetting(key='air_sensor', value={'enabled': True, 'host': '192.168.178.60', 'altitude_m': 100}))
        db.add(AppSetting(key='air_sensor_cache', value={
            'temperature_c': 21.4,
            'humidity_percent': 48.2,
            'dew_point_c': 10.2,
            'pressure_hpa': 1001.5,
            'sds_p1': 8.12,
            'sds_p2': 3.45,
            'age_seconds': 42,
            'software_version': 'NRZ-test',
            'last_success_at': last_success_at,
        }))
        db.commit()

    def override_get_db():
        with SessionLocal() as db:
            yield db

    test_app = FastAPI()
    test_app.dependency_overrides[get_db] = override_get_db
    test_app.include_router(current_values.router)
    response = TestClient(test_app).get('/api/current-values')

    assert response.status_code == 200
    data = response.json()
    assert data['air_sensor']['enabled'] is True
    assert data['air_sensor']['configured'] is True
    assert data['air_sensor']['ok'] is True
    assert data['air_sensor']['temperature_c'] == 21.4
    assert data['air_sensor']['humidity_percent'] == 48.2
    assert data['air_sensor']['pressure_hpa'] == 1001.5
    assert data['air_sensor']['sds_p1'] == 8.12
    assert data['air_sensor']['sds_p2'] == 3.45
    assert 'host' not in data['air_sensor']
    assert 'weather_underground_api_key' not in data['air_sensor']


def test_current_values_api_does_not_block_on_air_sensor_fetch(monkeypatch) -> None:
    from app.routers import settings

    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    stale_success_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

    with SessionLocal() as db:
        db.add(AppSetting(key='current_values_api', value={'enabled': True}))
        db.add(AppSetting(key='air_sensor', value={'enabled': True, 'host': '192.0.2.10'}))
        db.add(AppSetting(key='air_sensor_cache', value={
            'temperature_c': 20.1,
            'humidity_percent': 50.0,
            'last_success_at': stale_success_at,
        }))
        db.commit()

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError('current values API must not perform live air sensor fetches')

    monkeypatch.setattr(settings, 'fetch_air_sensor_current', fail_if_called)

    def override_get_db():
        with SessionLocal() as db:
            yield db

    test_app = FastAPI()
    test_app.dependency_overrides[get_db] = override_get_db
    test_app.include_router(current_values.router)
    response = TestClient(test_app).get('/api/current-values')

    assert response.status_code == 200
    data = response.json()
    assert data['air_sensor']['cached'] is True
    assert data['air_sensor']['ok'] is True
    assert data['air_sensor']['temperature_c'] == 20.1
