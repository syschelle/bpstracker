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
