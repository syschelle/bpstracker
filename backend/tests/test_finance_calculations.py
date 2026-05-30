from datetime import datetime, timezone

from app.models import Measurement
from app.routers.measurements import delta_energy


def test_delta_energy_filters_source_types():
    now = datetime.now(timezone.utc)
    rows = [
        Measurement(timestamp=now, device_id=1, source_type="shelly_rpc_switch", channel=0, energy_import_wh=1000),
        Measurement(timestamp=now, device_id=1, source_type="shelly_rpc_switch", channel=0, energy_import_wh=1250),
        Measurement(timestamp=now, device_id=2, source_type="shelly_3em_gen1_emeter", channel=0, phase="L1", energy_import_wh=5000),
        Measurement(timestamp=now, device_id=2, source_type="shelly_3em_gen1_emeter", channel=0, phase="L1", energy_import_wh=5300),
    ]

    assert delta_energy(rows, "energy_import_wh", {"shelly_rpc_switch"}) == 250
    assert delta_energy(rows, "energy_import_wh", {"shelly_3em_gen1_emeter"}) == 300
