import asyncio
import importlib.util
from pathlib import Path
from unittest.mock import patch

module_path = Path(__file__).resolve().parents[1] / 'weather_display_pi_server.py'
spec = importlib.util.spec_from_file_location('weather_display_pi_server', module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_ruuvi_sensor_configs_include_all_expected_sensors():
    assert module.RUUVITAG_SENSORS == [
        ('Makuuhuone', 'F5:F5:9A:56:D1:4F'),
        ('Keittiö', 'C1:33:99:C1:3E:79'),
        ('Terassi', 'DC:7A:39:53:77:91'),
    ]


def test_collect_ruuvi_state_uses_sensor_label_and_mac():
    service = module.DashboardService()

    async def fake_get_data_async(macs):
        assert macs == [mac for _, mac in module.RUUVITAG_SENSORS]
        yield ('C1:33:99:C1:3E:79', {
            'temperature': 12.3,
            'humidity': 41.2,
            'pressure': 1012.0,
            'battery': 88,
        })

    with patch.object(module, 'RuuviTagSensor', create=True) as ruuvi_sensor:
        ruuvi_sensor.get_data_async = fake_get_data_async
        state = asyncio.run(service._collect_ruuvi_state())

    assert state['status'] == 'Live sensor'
    assert state['sensor_name'] == 'Keittiö'
    assert state['mac'] == 'C1:33:99:C1:3E:79'


def test_dashboard_page_uses_header_panel_without_signal_section():
    html = module.DashboardHandler._build_page()

    assert 'class="panel header-panel"' in html
    assert 'Signal' not in html
    assert 'id="clock"' in html
    assert 'id="date"' in html
