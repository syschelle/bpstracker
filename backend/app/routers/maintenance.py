from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AppSetting, AuditLog, DailyEnergySummary, Measurement, User
from ..security import require_admin

router = APIRouter(prefix='/api/maintenance', tags=['maintenance'])


class ResetValuesRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=32)


class ResetValuesResponse(BaseModel):
    ok: bool
    deleted_measurements: int
    deleted_daily_summaries: int
    message: str


@router.post('/reset-values', response_model=ResetValuesResponse)
def reset_values(
    payload: ResetValuesRequest,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ResetValuesResponse:
    if payload.confirmation.strip().lower() != 'reset':
        raise HTTPException(status_code=400, detail='Type "reset" to confirm deleting all measured values')

    deleted_measurements = db.query(Measurement).delete(synchronize_session=False)
    deleted_daily = db.query(DailyEnergySummary).delete(synchronize_session=False)

    # Remove volatile value caches. Keep user/device/setup configuration.
    for key in ('air_sensor_cache', 'simulation_cache'):
        row = db.get(AppSetting, key)
        if row is not None:
            db.delete(row)

    # Clear generated Kindle images/cache. The next run regenerates them if enabled.
    backend_data = Path('/app/data')
    for candidate in ('kindle', 'kindle_display.png', 'kindle-display.png'):
        path = backend_data / candidate
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink(missing_ok=True)

    db.add(AuditLog(
        actor_user_id=actor.id,
        action='maintenance.reset_values',
        details={'deleted_measurements': deleted_measurements, 'deleted_daily_summaries': deleted_daily},
    ))
    db.commit()

    return ResetValuesResponse(
        ok=True,
        deleted_measurements=deleted_measurements,
        deleted_daily_summaries=deleted_daily,
        message='All measured values and daily totals have been deleted.',
    )
