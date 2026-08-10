import json
import importlib.util
from datetime import datetime
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from pidisplay.web.handler import DashboardHandler, set_services
from pidisplay.services import sensor_reader as sensor_reader_module

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


def test_get_state_labels_known_macs_and_surfaces_unknown_sensors():
    service = module.SensorReader()

    service._handle_data(('F5:F5:9A:56:D1:4F', {
        'temperature': 12.3,
        'humidity': 41.2,
        'pressure': 1012.0,
        'battery': 88,
    }))
    service._handle_data(('AA:BB:CC:DD:EE:FF', {
        'temperature': 18.9,
        'humidity': 48.0,
        'pressure': 1004.4,
        'battery': 63,
    }))
    service._handle_data(('DC:7A:39:53:77:91', {
        'temperature': 9.1,
        'humidity': 55.0,
        'pressure': 1001.2,
        'battery': 74,
    }))

    with patch.object(sensor_reader_module, 'RUUVITAG_AVAILABLE', True):
        state = service.get_state()

    assert state['status'] == 'Live sensor'
    assert state['sensor_name'] == 'Makuuhuone'
    assert state['mac'] == 'F5:F5:9A:56:D1:4F'
    assert len(state['sensors']) == 4
    assert state['sensors'][0]['name'] == 'Makuuhuone'
    assert state['sensors'][0]['temperature'] == '12.3'
    assert state['sensors'][1]['name'] == 'Keittiö'
    assert state['sensors'][1]['temperature'] == '--'
    assert state['sensors'][2]['name'] == 'Terassi'
    assert state['sensors'][2]['temperature'] == '9.1'
    assert state['sensors'][3]['name'] == 'AA:BB:CC:DD:EE:FF'
    assert state['sensors'][3]['temperature'] == '18.9'


def test_get_state_marks_readings_stale_after_threshold():
    service = module.SensorReader(stale_after_seconds=30)

    service._handle_data(('F5:F5:9A:56:D1:4F', {
        'temperature': 12.3,
        'humidity': 41.2,
        'pressure': 1012.0,
        'battery': 88,
    }))
    with service._lock:
        service._latest['F5:F5:9A:56:D1:4F']['last_seen'] -= 60

    with patch.object(sensor_reader_module, 'RUUVITAG_AVAILABLE', True):
        state = service.get_state()

    assert state['status'] == 'Stale'
    makuuhuone_row = next(row for row in state['sensors'] if row['name'] == 'Makuuhuone')
    assert makuuhuone_row['temperature'] == '--'


def test_run_loop_retries_after_transient_error_and_recovers():
    service = module.SensorReader()
    attempts = {'count': 0}

    def fake_listen(callback):
        attempts['count'] += 1
        if attempts['count'] == 1:
            raise RuntimeError('org.bluez.Error.InProgress')
        callback(('F5:F5:9A:56:D1:4F', {
            'temperature': 21.0,
            'humidity': 40.0,
            'pressure': 1000.0,
            'battery': 90,
        }))

    original_handle_data = service._handle_data

    def handle_data_then_stop(found_data):
        original_handle_data(found_data)
        service._stop_event.set()

    service._handle_data = handle_data_then_stop

    with patch.object(sensor_reader_module, 'RuuviTagSensor', create=True) as ruuvi_sensor, \
            patch.object(sensor_reader_module, 'RUUVITAG_AVAILABLE', True), \
            patch.object(sensor_reader_module, '_MIN_BACKOFF_SECONDS', 0.0), \
            patch.object(sensor_reader_module, '_MAX_BACKOFF_SECONDS', 0.0):
        ruuvi_sensor.listen = fake_listen
        service._run_loop()

        assert attempts['count'] == 2
        state = service.get_state()

    assert state['status'] == 'Live sensor'
    assert state['sensors'][0]['temperature'] == '21.0'


def test_dashboard_page_uses_header_panel_without_signal_section():
    html = module.DashboardHandler._build_page()

    assert 'class="panel header-panel"' in html
    assert 'Signal' not in html
    assert 'id="clock"' in html
    assert 'id="date"' in html
    assert 'id="weather-forecast"' in html


def test_weather_service_extracts_current_and_next_three_hours():
    service = module.WeatherService()
    payload = {
        'daily_forecasts': [
            {
                'date': '2026-08-10',
                'hourly_forecasts': [
                    {'time': '2026-08-10 13:00', 'temperature': 18.0, 'chance_of_rain': 10.0},
                    {'time': '2026-08-10 14:00', 'temperature': 19.0, 'chance_of_rain': 20.0},
                    {'time': '2026-08-10 15:00', 'temperature': 20.0, 'chance_of_rain': 30.0},
                    {'time': '2026-08-10 16:00', 'temperature': 21.0, 'chance_of_rain': 40.0},
                    {'time': '2026-08-10 17:00', 'temperature': 22.0, 'chance_of_rain': 50.0},
                ],
            }
        ]
    }

    state = service._normalize_daily_forecast(payload, now=datetime(2026, 8, 10, 13, 0))

    assert [item['time'] for item in state['hours']] == ['13:00', '14:00', '15:00', '16:00']
    assert [item['temperature'] for item in state['hours']] == ['18°C', '19°C', '20°C', '21°C']
    assert [item['chance_of_rain'] for item in state['hours']] == ['10%', '20%', '30%', '40%']


def test_weather_service_picks_nearest_hour_not_last_passed_block():
    service = module.WeatherService()
    payload = {
        'daily_forecasts': [
            {
                'date': '2026-08-10',
                'hourly_forecasts': [
                    {'time': '2026-08-10 00:00', 'temperature': 10.0, 'chance_of_rain': 0.0},
                    {'time': '2026-08-10 03:00', 'temperature': 11.0, 'chance_of_rain': 0.0},
                    {'time': '2026-08-10 18:00', 'temperature': 19.0, 'chance_of_rain': 15.0},
                    {'time': '2026-08-10 21:00', 'temperature': 17.0, 'chance_of_rain': 25.0},
                ],
            },
            {
                'date': '2026-08-11',
                'hourly_forecasts': [
                    {'time': '2026-08-11 00:00', 'temperature': 15.0, 'chance_of_rain': 5.0},
                    {'time': '2026-08-11 03:00', 'temperature': 14.0, 'chance_of_rain': 5.0},
                ],
            },
        ]
    }

    # 20:00 is 2 hours after the 18:00 block but only 1 hour before 21:00, so 21:00 wins.
    state = service._normalize_daily_forecast(payload, now=datetime(2026, 8, 10, 20, 0))

    assert [item['time'] for item in state['hours']] == ['21:00', '00:00', '03:00']
    assert [item['chance_of_rain'] for item in state['hours']] == ['10%', '20%', '30%', '40%']


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

    class FakeWeatherService:
        def get_state(self):
            return {
                'hours': [
                    {'time': '15:00', 'temperature': '20°C', 'chance_of_rain': '30%'},
                ],
                'status': 'Live',
            }

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

    set_services(FakeDashboardService(), FakeTransitService(), FakeWeatherService())

    handler = TestHandler()
    handler.do_GET()

    payload = json.loads(handler.wfile.getvalue().decode('utf-8'))

    assert handler.response_code == 200
    assert payload['status'] == 'Live sensor'
    assert payload['sensors'][0]['name'] == 'Makuuhuone'
    assert payload['sensors'][0]['temperature'] == '21.5'
    assert payload['weather']['status'] == 'Live'
    assert payload['weather']['hours'][0]['time'] == '15:00'
