import asyncio
import json
import importlib.util
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from pidisplay.web.handler import DashboardHandler, set_services
from pidisplay.services import dashboard_service as dashboard_service_module

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


def test_collect_ruuvi_state_reads_visible_sensors_and_labels_known_macs():
    service = module.DashboardService()
    calls = []

    async def fake_get_data_async(macs):
        calls.append(macs)
        yield ('F5:F5:9A:56:D1:4F', {
            'temperature': 12.3,
            'humidity': 41.2,
            'pressure': 1012.0,
            'battery': 88,
        })
        yield ('AA:BB:CC:DD:EE:FF', {
            'temperature': 18.9,
            'humidity': 48.0,
            'pressure': 1004.4,
            'battery': 63,
        })
        yield ('DC:7A:39:53:77:91', {
            'temperature': 9.1,
            'humidity': 55.0,
            'pressure': 1001.2,
            'battery': 74,
        })

    with patch.object(dashboard_service_module, 'RuuviTagSensor', create=True) as ruuvi_sensor:
        ruuvi_sensor.get_data_async = fake_get_data_async
        state = asyncio.run(service._collect_ruuvi_state())

    assert calls == [[]]
    assert state['status'] == 'Live sensor'
    assert state['sensor_name'] == 'Makuuhuone'
    assert state['mac'] == 'F5:F5:9A:56:D1:4F'
    assert len(state['sensors']) == 3
    assert state['sensors'][0]['name'] == 'Makuuhuone'
    assert state['sensors'][1]['name'] == 'Terassi'
    assert state['sensors'][1]['temperature'] == '9.1'
    assert state['sensors'][2]['name'] == 'AA:BB:CC:DD:EE:FF'
    assert state['sensors'][2]['temperature'] == '18.9'


def test_dashboard_page_uses_header_panel_without_signal_section():
    html = module.DashboardHandler._build_page()

    assert 'class="panel header-panel"' in html
    assert 'Signal' not in html
    assert 'id="clock"' in html
    assert 'id="date"' in html


def test_api_data_returns_current_sensor_state():
    class FakeDashboardService:
        def get_state(self):
            return {
                'status': 'Live sensor',
                'source': 'ruuvi',
                'timestamp': '12:34:56',
                'date': '10.08.2026',
                'temperature': '--',
                'humidity': '--',
                'pressure': '--',
                'battery': '--',
                'signal': 'OK',
                'sensor_name': '--',
                'sensors': [
                    {
                        'name': 'Makuuhuone',
                        'temperature': '21.5',
                        'humidity': '45.0',
                        'pressure': '1008.5',
                        'battery': '96.0',
                        'mac': 'F5:F5:9A:56:D1:4F',
                    }
                ],
            }

    class FakeTransitService:
        def get_departures(self):
            return []

        def get_status(self):
            return ''

    class TestHandler(DashboardHandler):
        def __init__(self):
            self.path = '/api/data'
            self.wfile = BytesIO()
            self.response_code = None
            self.response_headers = []

        def send_response(self, code, message=None):
            self.response_code = code

        def send_header(self, key, value):
            self.response_headers.append((key, value))

        def end_headers(self):
            return None

    set_services(FakeDashboardService(), FakeTransitService())

    handler = TestHandler()
    handler.do_GET()

    payload = json.loads(handler.wfile.getvalue().decode('utf-8'))

    assert handler.response_code == 200
    assert payload['status'] == 'Live sensor'
    assert payload['sensors'][0]['name'] == 'Makuuhuone'
    assert payload['sensors'][0]['temperature'] == '21.5'
