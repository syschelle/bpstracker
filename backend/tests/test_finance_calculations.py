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


def test_battery_analysis_uses_configured_roundtrip_efficiency():
    from app.routers.measurements import battery_analysis

    result = battery_analysis(
        exported_today_kwh=2.0,
        exported_total_kwh=10.0,
        kwh_price=0.30,
        battery_cost=1000.0,
        battery_capacity_kwh=2.0,
        battery_roundtrip_efficiency=0.80,
        remaining_bps_investment=0.0,
    )

    assert result["battery_savings_today_eur"] == 0.48
    assert result["battery_savings_total_potential_eur"] == 2.4


def test_battery_analysis_clamps_unrealistic_roundtrip_efficiency():
    from app.routers.measurements import battery_analysis

    result = battery_analysis(
        exported_today_kwh=1.0,
        exported_total_kwh=1.0,
        kwh_price=1.0,
        battery_cost=1000.0,
        battery_capacity_kwh=1.0,
        battery_roundtrip_efficiency=1.5,
        remaining_bps_investment=0.0,
    )

    assert result["battery_savings_today_eur"] == 1.0
