from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Device, DeviceType
from app.poller import poll_and_store_device
from app.shelly import NormalizedMeasurement, ShellyPollResult


class FakeShellyClient:
    async def poll(self, _config):
        now = datetime.now(timezone.utc)
        return ShellyPollResult(
            detected_type='shelly_pro_3em_gen2',
            generation='2',
            model='Shelly Pro 3EM',
            firmware='test-fw',
            raw={},
            measurements=[
                NormalizedMeasurement(
                    timestamp=now,
                    source_type='shelly_rpc_em_total',
                    channel=0,
                    phase='total',
                    power_w=123.0,
                    total_power_w=123.0,
                )
            ],
        )


@pytest.fixture()
def db_session():
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as db:
        yield db


@pytest.mark.asyncio
async def test_successful_auto_poll_persists_detected_device_type(db_session) -> None:
    device = Device(
        name='Hausanschluss',
        host='192.168.178.50',
        device_type=DeviceType.auto,
        is_active=True,
    )
    db_session.add(device)
    db_session.commit()
    db_session.refresh(device)

    await poll_and_store_device(db_session, device, FakeShellyClient())

    db_session.refresh(device)
    assert device.device_type == DeviceType.shelly_pro_3em_gen2
    assert device.status.online is True
    assert device.status.raw_info['detected_type'] == 'shelly_pro_3em_gen2'
