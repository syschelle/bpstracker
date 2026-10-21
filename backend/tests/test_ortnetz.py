from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import AppSetting, Device, DevicePurpose, DeviceStatus, DeviceType, Measurement
from app.ortnetz import build_ortnetz_payload


def _db():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_build_payload_uses_same_three_phase_sample_without_estimating_optional_values():
    db = _db()
    device = Device(name='Grid', host='192.168.1.5', device_type=DeviceType.shelly_pro_3em_gen2, purpose=DevicePurpose.grid.value, is_active=True)
    db.add(device); db.flush()
    db.add(DeviceStatus(device_id=device.id, online=True, detected_model='Shelly Pro 3EM'))
    db.add(AppSetting(key='ortnetz', value={'enabled': True, 'device_id': device.id, 'latitude': 50.1, 'longitude': 12.2, 'plant_capacity_kwp': 0.8}))
    ts = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
    for phase, voltage, current, frequency in [('L1',230.1,1.1,50.01),('L2',229.9,1.2,50.02),('L3',230.4,1.3,50.00)]:
        db.add(Measurement(timestamp=ts, device_id=device.id, source_type='shelly_rpc_em', channel=0, phase=phase, voltage_v=voltage, current_a=current, frequency_hz=frequency, total_power_w=-350.0))
    db.commit()
    payload = build_ortnetz_payload(db, datetime(2026, 10, 21, 9, 5, tzinfo=timezone.utc))
    assert payload['l1_v'] == 230.1 and payload['l2_v'] == 229.9 and payload['l3_v'] == 230.4
    assert payload['grid_power_w'] == -350.0
    assert payload['smartmeter_model'] == 'Shelly Pro 3EM'
    assert payload['plant_capacity_kwp'] == 0.8
    assert payload['grid_frequency_hz'] == 50.01
    assert 'power_factor' not in payload


def test_simulation_disables_payload():
    db = _db()
    db.add(AppSetting(key='ortnetz', value={'enabled': True, 'device_id': 1, 'latitude': 50.1, 'longitude': 12.2}))
    db.add(AppSetting(key='simulation', value={'enabled': True}))
    db.commit()
    assert build_ortnetz_payload(db) is None
