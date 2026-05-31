from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from ..config import get_settings
from ..database import get_db
from ..models import AuditLog, Device, DeviceType, User
from ..poller import poll_and_store_device
from ..schemas import DeviceCreate, DeviceRead, DeviceUpdate, TestDeviceResponse
from ..security import decrypt_secret, encrypt_secret, get_current_user, require_admin
from ..network_security import OutboundHostError
from ..shelly import ShellyClient, ShellyCredentials, ShellyDeviceConfig, ShellyClientError, detected_device_type, normalize_shelly_host

router = APIRouter(prefix='/api/devices', tags=['devices'])


def _normalize_device_host_or_400(host: str | None) -> str:
    try:
        normalized = normalize_shelly_host(host)
    except OutboundHostError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Host darf nicht leer sein.')
    return normalized

@router.get('', response_model=list[DeviceRead])
def list_devices(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Device]:
    return db.query(Device).options(joinedload(Device.status)).order_by(Device.name).all()


@router.post('', response_model=DeviceRead)
async def create_device(payload: DeviceCreate, user: User = Depends(require_admin), db: Session = Depends(get_db)) -> Device:
    host = _normalize_device_host_or_400(payload.host)
    device_type = payload.device_type
    detected_type_value: str | None = None
    if payload.device_type == DeviceType.auto:
        client = ShellyClient(timeout_seconds=get_settings().shelly_timeout_seconds)
        config = ShellyDeviceConfig(
            host=host,
            device_type=DeviceType.auto,
            channel=payload.channel,
            credentials=ShellyCredentials(username=payload.username, password=payload.password),
        )
        try:
            result = await client.poll(config)
            detected_type_value = result.detected_type
            detected = detected_device_type(result.detected_type, result.generation)
            if detected is not None:
                device_type = detected
        except ShellyClientError:
            # Keep manual recovery possible for temporarily unreachable devices.
            # Successful background/manual polls will persist the detected type later.
            pass

    device = Device(
        name=payload.name,
        device_type=device_type,
        purpose=payload.purpose.value if hasattr(payload.purpose, 'value') else payload.purpose,
        host=host,
        username=payload.username,
        password_ciphertext=encrypt_secret(payload.password),
        is_active=payload.is_active,
        poll_interval_seconds=payload.poll_interval_seconds,
        channel=payload.channel,
    )
    db.add(device)
    details = {'name': payload.name, 'host': host}
    if detected_type_value:
        details['detected_type'] = detected_type_value
        details['persisted_type'] = device_type.value if hasattr(device_type, 'value') else str(device_type)
    db.add(AuditLog(actor_user_id=user.id, action='device.create', details=details))
    db.commit()
    db.refresh(device)
    return db.query(Device).options(joinedload(Device.status)).filter(Device.id == device.id).one()


@router.get('/{device_id}', response_model=DeviceRead)
def get_device(device_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Device:
    device = db.query(Device).options(joinedload(Device.status)).filter(Device.id == device_id).one_or_none()
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Device not found')
    return device


@router.patch('/{device_id}', response_model=DeviceRead)
def update_device(device_id: int, payload: DeviceUpdate, user: User = Depends(require_admin), db: Session = Depends(get_db)) -> Device:
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Device not found')

    update = payload.model_dump(exclude_unset=True)
    if 'host' in update:
        update['host'] = _normalize_device_host_or_400(update.get('host'))
    clear_password = update.pop('clear_password', False)
    password = update.pop('password', None)
    for key, value in update.items():
        setattr(device, key, value)
    if clear_password:
        device.password_ciphertext = None
    elif password is not None:
        device.password_ciphertext = encrypt_secret(password)

    db.add(AuditLog(actor_user_id=user.id, action='device.update', details={'device_id': device_id}))
    db.commit()
    return db.query(Device).options(joinedload(Device.status)).filter(Device.id == device_id).one()


@router.delete('/{device_id}')
def delete_device(device_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, bool]:
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Device not found')
    db.delete(device)
    db.add(AuditLog(actor_user_id=user.id, action='device.delete', details={'device_id': device_id}))
    db.commit()
    return {'ok': True}


@router.post('/{device_id}/test', response_model=TestDeviceResponse)
async def test_device(device_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> TestDeviceResponse:
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Device not found')
    client = ShellyClient(timeout_seconds=get_settings().shelly_timeout_seconds)
    config = ShellyDeviceConfig(
        host=device.host,
        device_type=device.device_type,
        channel=device.channel,
        credentials=ShellyCredentials(username=device.username, password=decrypt_secret(device.password_ciphertext)),
    )
    try:
        result = await client.poll(config)
    except ShellyClientError as exc:
        return TestDeviceResponse(ok=False, message=str(exc))
    return TestDeviceResponse(
        ok=True,
        detected_type=result.detected_type,
        generation=result.generation,
        model=result.model,
        message=f'OK: {len(result.measurements)} Messpunkte erkannt',
        raw=result.raw,
    )


@router.post('/{device_id}/poll', response_model=DeviceRead)
async def poll_now(device_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> Device:
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Device not found')
    await poll_and_store_device(db, device)
    return db.query(Device).options(joinedload(Device.status)).filter(Device.id == device_id).one()
