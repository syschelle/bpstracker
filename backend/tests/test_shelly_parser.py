from datetime import datetime, timezone

from app.models import DeviceType
from app.shelly import parse_rpc_status, parse_switch_status, parse_em_status


def test_parse_switch_status():
    now = datetime.now(timezone.utc)
    measurements = parse_switch_status({'apower': 123.4, 'voltage': 230, 'current': 0.54, 'aenergy': {'total': 1000}}, now, 0)
    assert len(measurements) == 1
    assert measurements[0].power_w == 123.4
    assert measurements[0].energy_import_wh == 1000


def test_parse_rpc_status_switch_filter():
    now = datetime.now(timezone.utc)
    status = {
        'switch:0': {'apower': 10},
        'switch:1': {'apower': 20},
    }
    measurements = parse_rpc_status(status, now, requested_channel=1)
    assert len(measurements) == 1
    assert measurements[0].channel == 1
    assert measurements[0].power_w == 20


def test_parse_em_status_phase_objects():
    now = datetime.now(timezone.utc)
    measurements = parse_em_status(
        {
            'a': {'active_power': 1, 'voltage': 230, 'current': 0.1, 'pf': 0.9},
            'b': {'active_power': 2, 'voltage': 231, 'current': 0.2, 'pf': 0.8},
            'c': {'active_power': 3, 'voltage': 232, 'current': 0.3, 'pf': 0.7},
            'total_act_power': 6,
        },
        now,
        channel=0,
    )
    assert len(measurements) == 4
    assert measurements[-1].total_power_w == 6
