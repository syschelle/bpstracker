from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse

from ..kindle_display import is_kindle_display_enabled, kindle_display_service

router = APIRouter(prefix='/api/kindle', tags=['kindle'])


@router.get('/display.png')
async def kindle_display_png() -> FileResponse:
    """Return the latest cached Kindle display PNG.

    The route intentionally does not trigger sensor reads or rendering work. The
    background task generates the file once per minute; this endpoint only serves
    the last valid image so Kindle cron jobs get a fast response.
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
async def refresh_kindle_display() -> dict:
    if not is_kindle_display_enabled():
        raise HTTPException(status_code=503, detail='Kindle display generation is disabled in setup')
    await kindle_display_service.generate_once(force=True)
    return kindle_display_service.meta()


@router.get('/meta')
def kindle_display_meta() -> dict:
    return kindle_display_service.meta()
