from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ..kindle_display import is_kindle_display_enabled, kindle_display_service
from ..models import User
from ..security import require_admin

router = APIRouter(prefix='/api/kindle', tags=['kindle'])


@router.get('/display.png')
async def kindle_display_png() -> FileResponse:
    """Return the latest cached Kindle display PNG.

    This endpoint intentionally remains unauthenticated when Kindle display
    generation is enabled, because Kindle cron/image fetch workflows generally
    cannot attach bearer tokens. It does not trigger sensor reads or rendering
    work except for the initial missing-file bootstrap. Control endpoints below
    are admin-only.
    """
    if not is_kindle_display_enabled():
        raise HTTPException(status_code=503, detail='Kindle display generation is disabled in setup')
    path = kindle_display_service.output_path
    if not path.exists():
        await kindle_display_service.generate_once()
    if not path.exists():
        raise HTTPException(status_code=503, detail='Kindle display image is not available yet')
    return FileResponse(
        path,
        media_type='image/png',
        filename='bpstracker-kindle-display.png',
        headers={
            # Feste Kindle-URL ohne Query-Parameter verwenden:
            #   http://<ipadresse>:5173/api/kindle/display.png
            # Die Header verhindern Browser-/Proxy-Caching, damit keine Cache-Busting-Parameter nötig sind.
            'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
            'Pragma': 'no-cache',
            'Expires': '0',
            'Content-Disposition': 'inline; filename=bpstracker-kindle-display.png',
            'X-BPSTracker-Kindle': 'display',
        },
    )


@router.post('/refresh')
async def refresh_kindle_display(_: User = Depends(require_admin)) -> dict:
    if not is_kindle_display_enabled():
        raise HTTPException(status_code=503, detail='Kindle display generation is disabled in setup')
    await kindle_display_service.generate_once(force=True)
    return kindle_display_service.meta()


@router.get('/meta')
def kindle_display_meta(_: User = Depends(require_admin)) -> dict:
    return kindle_display_service.meta()
