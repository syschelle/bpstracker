from datetime import datetime, timezone

from app.models import Measurement
from app.routers.measurements import _is_grid_row
from app.energy_retention import delta_energy


def test_auto_grid_energy_rows_are_included_in_dashboard_balances() -> None:
    now = datetime.now(timezone.utc)
    rows = [
        Measurement(timestamp=now, device_id=1, source_type='shelly_rpc_emdata', channel=0, phase='total', energy_import_wh=1000),
        Measurement(timestamp=now, device_id=1, source_type='shelly_rpc_emdata', channel=0, phase='total', energy_import_wh=1350),
        Measurement(timestamp=now, device_id=2, source_type='shelly_3em_gen1_emeter', channel=0, phase='L1', energy_import_wh=5000),
        Measurement(timestamp=now, device_id=2, source_type='shelly_3em_gen1_emeter', channel=0, phase='L1', energy_import_wh=5400),
    ]
    purposes = {1: 'auto', 2: 'auto'}

    grid_rows = [row for row in rows if _is_grid_row(row, purposes)]

    assert len(grid_rows) == 4
    assert delta_energy(grid_rows, 'energy_import_wh', None) == 750


def test_ignored_grid_energy_rows_are_excluded_from_dashboard_balances() -> None:
    row = Measurement(source_type='shelly_rpc_emdata', device_id=1, channel=0, phase='total', energy_import_wh=1000)

    assert _is_grid_row(row, {1: 'ignored'}) is False
