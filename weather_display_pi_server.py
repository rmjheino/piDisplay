import os
from http.server import ThreadingHTTPServer

from pidisplay.config import RUUVITAG_AVAILABLE, RUUVITAG_SENSORS, RuuviTagSensor
from pidisplay.services.dashboard_service import DashboardService
from pidisplay.services.transit_service import TransitService
from pidisplay.web.handler import DashboardHandler, set_services


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), DashboardHandler)
    print(f"Dashboard server running on http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dashboard server")
    finally:
        server.server_close()


service = DashboardService()
transit_service = TransitService(
    stop_id=os.environ.get("TRANSIT_STOP_ID", ""),
    api_key=os.environ.get("DIGITRANSIT_API_KEY", ""),
)
set_services(service, transit_service)


if __name__ == "__main__":
    service.start()
    transit_service.start()
    main()
