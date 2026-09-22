"""Dashboard and current-values API still combine immutable history with live today."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.kindle_display import _today_energy_mix
from app.models import AppSetting, DailyEnergySummary, Device, DeviceType, Measurement
from app.routers import current_values, measurements


def test_total_balances_include_stored_history_and_live_day_without_rewriting_past():
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    make_session = sessionmaker(bind=engine)
    today = datetime.now(timezone.utc).replace(hour=2, minute=0, second=0, microsecond=0)

    with make_session() as db:
        db.add_all([
            AppSetting(key='ui', value={'timezone': 'UTC', 'language': 'de'}),
            AppSetting(key='current_values_api', value={'enabled': True}),
            DailyEnergySummary(date=(today - timedelta(days=1)).date(), imported_kwh=12, exported_kwh=1, solar_kwh=7),
        ])
        grid = Device(name='Grid', host='192.0.2.1', device_type=DeviceType.shelly_pro_3em_gen2, purpose='grid')
        solar = Device(name='Solar', host='192.0.2.2', device_type=DeviceType.shelly_2pm_gen4, purpose='solar')
        db.add_all([grid, solar])
        db.flush()
        db.add_all([
            Measurement(timestamp=today, device_id=grid.id, source_type='shelly_rpc_emdata',
                        channel=0, phase='total', energy_import_wh=8000, energy_export_wh=300),
            Measurement(timestamp=today + timedelta(minutes=15), device_id=grid.id, source_type='shelly_rpc_emdata',
                        channel=0, phase='total', energy_import_wh=8900, energy_export_wh=400),
            Measurement(timestamp=today, device_id=solar.id, source_type='shelly_rpc_switch', channel=0,
                        energy_import_wh=5000),
            Measurement(timestamp=today + timedelta(minutes=15), device_id=solar.id, source_type='shelly_rpc_switch',
                        channel=0, energy_import_wh=6400),
            # A retained reading from yesterday MUST NOT trigger recalculation.
            Measurement(timestamp=today - timedelta(days=1), device_id=grid.id,
                        source_type='shelly_rpc_emdata', channel=0, phase='total', energy_import_wh=999999),
        ])
        db.commit()

    def override_get_db():
        with make_session() as session:
            yield session

    app = FastAPI()
    app.dependency_overrides[get_db] = override_get_db
    app.include_router(current_values.router)
    response = TestClient(app).get('/api/current-values')
    assert response.status_code == 200
    data = response.json()
    assert data['daily_grid_import_kwh'] == pytest.approx(0.9)
    assert data['daily_grid_export_kwh'] == pytest.approx(0.1)
    assert data['daily_solar_production_kwh'] == pytest.approx(1.4)
    assert data['total_grid_import_kwh'] == pytest.approx(12.9)
    assert data['total_grid_export_kwh'] == pytest.approx(1.1)
    assert data['total_solar_production_kwh'] == pytest.approx(8.4)

    with make_session() as db:
        summary = measurements.summary(None, db)
        assert summary.imported_today_kwh == pytest.approx(0.9)
        assert summary.exported_today_kwh == pytest.approx(0.1)
        assert summary.solar_today_kwh == pytest.approx(1.4)
        assert summary.imported_total_kwh == pytest.approx(12.9)
        assert summary.exported_total_kwh == pytest.approx(1.1)
        assert summary.solar_total_kwh == pytest.approx(8.4)
        kindle_import, kindle_solar = _today_energy_mix(db, 'UTC')
        assert kindle_import == pytest.approx(0.9)
        assert kindle_solar == pytest.approx(1.4)
        historical = db.query(DailyEnergySummary).one()
        assert (historical.imported_kwh, historical.exported_kwh, historical.solar_kwh) == (12, 1, 7)
    engine.dispose()
