from pathlib import Path

from app.kindle_display import KINDLE_OUTPUT_PATH, KindleDisplayService


def test_kindle_display_default_cache_path_uses_tmp() -> None:
    assert KINDLE_OUTPUT_PATH == Path('/tmp/bpstracker-kindle-display.png')


def test_kindle_meta_includes_output_mtime(tmp_path) -> None:
    output = tmp_path / 'kindle-display.png'
    output.write_bytes(b'not-a-real-png')
    service = KindleDisplayService(output)

    meta = service.meta()

    assert meta['path'] == str(output)
    assert meta['size_bytes'] == len(b'not-a-real-png')
    assert meta['updated_at'] is not None


import pytest


@pytest.mark.asyncio
async def test_kindle_meta_does_not_expose_exception_details(tmp_path, monkeypatch) -> None:
    output = tmp_path / 'kindle-display.png'
    service = KindleDisplayService(output)

    def fail_generation() -> None:
        raise RuntimeError('secret internal filesystem detail /tmp/private')

    monkeypatch.setattr(service, '_generate_sync', fail_generation)

    await service.generate_once(force=True)
    meta = service.meta()

    assert meta['last_error'] == 'Kindle display generation failed'
    assert 'secret internal filesystem detail' not in str(meta)
    assert 'last_error_detail' not in meta


def test_kindle_output_stale_detection(tmp_path) -> None:
    output = tmp_path / 'kindle-display.png'
    output.write_bytes(b'not-a-real-png')
    service = KindleDisplayService(output)

    assert service.is_output_stale(max_age_seconds=3600) is False


def test_kindle_missing_output_is_stale(tmp_path) -> None:
    service = KindleDisplayService(tmp_path / 'missing.png')

    assert service.is_output_stale() is True
