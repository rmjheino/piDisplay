import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

from pidisplay.services.sensor_reader import SensorReader
from pidisplay.services.transit_service import TransitService
from pidisplay.services.weather_service import WeatherService
from pidisplay.web.template import build_dashboard_page

_service: SensorReader | None = None
_transit_service: TransitService | None = None
_weather_service: WeatherService | None = None


def set_services(service: SensorReader, transit_service: TransitService, weather_service: WeatherService | None = None) -> None:
    global _service, _transit_service, _weather_service
    _service = service
    _transit_service = transit_service
    _weather_service = weather_service


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)

        if _service is None or _transit_service is None:
            self.send_response(503)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Services not initialized")
            return

        if parsed.path == "/api/data":
            payload = _service.get_state()
            if _weather_service is not None:
                payload["weather"] = _weather_service.get_state()
            self._send_json(payload)
        elif parsed.path == "/api/transit":
            self._send_json({
                "departures": _transit_service.get_departures(),
                "has_alerts": _transit_service.get_has_alerts(),
                "status": _transit_service.get_status(),
            })
        else:
            self._send_html(self._build_page())

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _send_json(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _build_page() -> str:
        return build_dashboard_page()
