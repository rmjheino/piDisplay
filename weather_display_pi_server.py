
import asyncio
import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlencode, urlparse

try:
    import ruuvitag_sensor.log
    from ruuvitag_sensor.ruuvi import RuuviTagSensor

    ruuvitag_sensor.log.enable_console()
    RUUVITAG_AVAILABLE = True
except Exception:  # pragma: no cover - depends on runtime environment
    RUUVITAG_AVAILABLE = False


RUUVITAG_SENSORS = [
    ("Makuuhuone", "F5:F5:9A:56:D1:4F"),
    ("Keittiö", "C1:33:99:C1:3E:79"),
    ("Terassi", "DC:7A:39:53:77:91"),
]


class DashboardService:
    def __init__(self, refresh_seconds: int = 3) -> None:
        self.refresh_seconds = refresh_seconds
        self._state = {
            "status": "Starting",
            "source": "demo",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "date": datetime.now().strftime("%d.%m.%Y"),
            "temperature": "--",
            "humidity": "--",
            "pressure": "--",
            "battery": "--",
            "signal": "--",
            "sensor_name": "--",
            "sensors": [],
        }
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def get_state(self) -> dict:
        with self._lock:
            return dict(self._state)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self._refresh_state()
            self._stop_event.wait(self.refresh_seconds)

    def _refresh_state(self) -> None:
        if RUUVITAG_AVAILABLE:
            try:
                state = asyncio.run(self._collect_ruuvi_state())
                if state:
                    self._set_state(state)
                    return
            except Exception:
                pass

        self._set_state(self._build_demo_state())

    def _set_state(self, state: dict) -> None:
        with self._lock:
            now = datetime.now()
            state["timestamp"] = now.strftime("%H:%M:%S")
            state["date"] = now.strftime("%d.%m.%Y")
            self._state = state

    async def _collect_ruuvi_state(self) -> dict:
        found_sensors = []
        try:
            macs = [mac for _, mac in RUUVITAG_SENSORS]
            async for found_data in RuuviTagSensor.get_data_async(macs):
                mac, payload = found_data
                sensor_name = next(
                    (name for name, configured_mac in RUUVITAG_SENSORS if configured_mac == mac),
                    "Unknown",
                )
                found_sensors.append(
                    {
                        "name": sensor_name,
                        "mac": mac,
                        "temperature": payload.get("temperature", "--"),
                        "humidity": payload.get("humidity", "--"),
                        "pressure": payload.get("pressure", "--"),
                        "battery": payload.get("battery", "--"),
                    }
                )
        except Exception:
            return {}

        if not found_sensors:
            return {}

        sensors = []
        for name, mac in RUUVITAG_SENSORS:
            sensor = next((item for item in found_sensors if item.get("mac") == mac), None)
            sensors.append(
                {
                    "name": name,
                    "temperature": self._format_value(sensor.get("temperature")) if sensor else "--",
                    "humidity": self._format_value(sensor.get("humidity")) if sensor else "--",
                    "pressure": self._format_value(sensor.get("pressure")) if sensor else "--",
                    "battery": self._format_value(sensor.get("battery")) if sensor else "--",
                    "mac": sensor.get("mac", mac) if sensor else mac,
                }
            )

        return {
            "status": "Live sensor",
            "source": "ruuvi",
            "temperature": "--",
            "humidity": "--",
            "pressure": "--",
            "battery": "--",
            "signal": "OK",
            "mac": "--",
            "sensor_name": "--",
            "sensors": sensors,
        }

    def _build_demo_state(self) -> dict:
        now = datetime.now()
        seconds = int(now.strftime("%S"))
        sensors = []
        for index, (name, mac) in enumerate(RUUVITAG_SENSORS):
            temperature = 21.4 + ((seconds + index) % 7 - 3) * 0.2
            humidity = 45.0 + ((seconds + index) % 5 - 2) * 1.2
            pressure = 1008.5 + ((seconds + index) % 3 - 1) * 0.4
            battery = 96.0 - ((seconds + index) % 6)
            sensors.append(
                {
                    "name": name,
                    "temperature": f"{temperature:.1f} °C",
                    "humidity": f"{humidity:.1f} %",
                    "pressure": f"{pressure:.1f} hPa",
                    "battery": f"{battery:.0f} %",
                    "mac": mac,
                }
            )
        return {
            "status": "Demo mode",
            "source": "demo",
            "temperature": "--",
            "humidity": "--",
            "pressure": "--",
            "battery": "--",
            "signal": "Simulated",
            "mac": "--",
            "sensor_name": "--",
            "sensors": sensors,
        }

    @staticmethod
    def _format_value(value: object) -> str:
        if value in (None, "", "--"):
            return "--"
        if isinstance(value, float):
            return f"{value:.1f}"
        return str(value)


class TransitService:
    _API_URL = "https://api.digitransit.fi/routing/v2/hsl/gtfs/v1"
    _STOP_NAME = "Merisotilaantori"

    def __init__(self, stop_id: str, api_key: str, refresh_seconds: int = 300) -> None:
        self._stop_id = stop_id
        self._api_key = api_key
        self._refresh_seconds = refresh_seconds
        self._departures: list = []
        self._status: str = ""
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def get_departures(self) -> list:
        with self._lock:
            return list(self._departures)

    def get_status(self) -> str:
        with self._lock:
            return self._status

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self._refresh()
            self._stop_event.wait(self._refresh_seconds)

    def _refresh(self) -> None:
        if not self._api_key:
            with self._lock:
                self._status = "No API key set (DIGITRANSIT_API_KEY)"
            return

        try:
            if not self._stop_id:
                self._stop_id = self._resolve_stop_id()
            if self._stop_id:
                departures = self._fetch_departures()
                with self._lock:
                    self._departures = departures
                    self._status = ""
        except Exception as exc:
            print(f"[TransitService] {exc}", flush=True)
            with self._lock:
                self._status = str(exc)

    def _resolve_stop_id(self) -> str:
        """Queries the stop name to find its gtfsId on first run."""
        query = '{ stops(name: "%s") { gtfsId name } }' % self._STOP_NAME
        data = self._graphql(query)
        stops = data.get("data", {}).get("stops", [])
        for stop in stops:
            if stop.get("name", "").lower() == self._STOP_NAME.lower():
                return stop["gtfsId"]
        return stops[0]["gtfsId"] if stops else ""

    def _fetch_departures(self) -> list:
        query = (
            '{ stop(id: "%s") { stoptimesWithoutPatterns(numberOfDepartures: 3) {'
        " serviceDay scheduledDeparture realtimeDeparture realtime } } }"
        ) % self._stop_id
        data = self._graphql(query)
        stoptimes = data.get("data", {}).get("stop", {}).get("stoptimesWithoutPatterns", [])
        return [
            {
          "scheduled": self._epoch_hhmm(st["serviceDay"] + st["scheduledDeparture"]),
          "realtime": self._epoch_hhmm(st["serviceDay"] + st["realtimeDeparture"]),
                "is_realtime": st.get("realtime", False),
            }
            for st in stoptimes
        ]

    def _graphql(self, query: str) -> dict:
        payload = json.dumps({"query": query}).encode("utf-8")
        # Include the key as query parameter as documented, in addition to header,
        # to avoid intermediaries that may strip non-standard headers.
        endpoint = f"{self._API_URL}?{urlencode({'digitransit-subscription-key': self._api_key})}"
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "PIDisplay/1.0",
                "digitransit-subscription-key": self._api_key,
                "Ocp-Apim-Subscription-Key": self._api_key,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("errors"):
                details = "; ".join(err.get("message", "Unknown GraphQL error") for err in data["errors"])
                raise RuntimeError(f"Transit GraphQL error: {details}")
            return data
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace").strip()
            except Exception:
                body = ""

            message = f"Transit API HTTP {exc.code}: {exc.reason}"
            if exc.code in (401, 403, 429, 503):
                message += " (verify DIGITRANSIT_API_KEY subscription and quota)"
            if body:
                message += f" - {body[:180]}"
            raise RuntimeError(message) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Transit API connection error: {exc.reason}") from exc

    @staticmethod
    def _epoch_hhmm(epoch: int) -> str:
        return datetime.fromtimestamp(epoch).strftime("%H:%M")


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/data":
            self._send_json(service.get_state())
        elif parsed.path == "/api/transit":
            self._send_json({"departures": transit_service.get_departures(), "status": transit_service.get_status()})
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
        return """
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>PIDisplay Dashboard</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #050816;
      --panel: rgba(12, 24, 48, 0.92);
      --border: rgba(255, 255, 255, 0.16);
      --text: #f7f9ff;
      --muted: #8fa1c8;
      --accent: #5fd0ff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: linear-gradient(145deg, var(--bg), #101b35);
      color: var(--text);
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    .shell {
      min-height: 100vh;
      padding: 2.2vh 2.2vw;
      display: flex;
      align-items: stretch;
      justify-content: center;
    }
    .grid {
      width: min(100%, 1400px);
      height: min(100%, 1920px);
      display: grid;
      grid-template-columns: 1fr;
      grid-template-rows: auto auto auto;
      gap: 1.5rem;
      flex: 1;
    }
    .header-panel {
      grid-column: 1;
      grid-row: 1;
      min-height: 220px;
      justify-content: center;
      align-items: flex-start;
      padding: 2rem 2.4rem;
    }
    .sensor-panel {
      grid-column: 1;
      grid-row: 3;
    }
    .departures-panel {
      grid-column: 1;
      grid-row: 2;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 24px;
      box-shadow: 0 18px 45px rgba(0, 0, 0, 0.35);
      padding: 1.6rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      overflow: hidden;
    }
    .panel h1, .panel h2, .panel h3 {
      margin: 0;
      font-weight: 600;
    }
    .tag {
      color: var(--accent);
      font-size: 0.95rem;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      margin-bottom: 0.5rem;
    }
    .value {
      font-size: clamp(2rem, 4.8vw, 3.6rem);
      font-weight: 700;
      line-height: 1.1;
      margin-top: 0.6rem;
    }
    .muted {
      color: var(--muted);
      font-size: clamp(0.95rem, 1.7vw, 1.2rem);
      line-height: 1.5;
    }
    .time-box {
      display: flex;
      flex-direction: column;
      gap: 0.6rem;
    }
    .clock {
      font-size: clamp(5.2rem, 10vw, 9.6rem);
      font-weight: 700;
      line-height: 1;
    }
    .date {
      font-size: clamp(2.1rem, 3.8vw, 3.1rem);
      color: var(--muted);
    }
    .list {
      display: grid;
      gap: 0.8rem;
      margin-top: 1rem;
    }
    .list div {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-top: 0.4rem;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      font-size: clamp(1rem, 1.7vw, 1.2rem);
    }
    .sensor-table {
      display: grid;
      gap: 0.65rem;
      margin-top: 0.2rem;
    }
    .sensor-row {
      display: grid;
      grid-template-columns: 1.4fr 1fr 1fr 1fr;
      gap: 0.8rem;
      align-items: center;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      padding-top: 0.6rem;
      font-size: clamp(1rem, 1.5vw, 1.16rem);
    }
    .sensor-head {
      border-top: none;
      padding-top: 0;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
      font-size: clamp(0.8rem, 1.1vw, 0.92rem);
      font-weight: 600;
    }
    .transit-table {
      display: grid;
      gap: 0.7rem;
      margin-top: 1rem;
    }
    .transit-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      align-items: center;
      gap: 0.9rem;
      padding-top: 0.4rem;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      font-size: clamp(1rem, 1.7vw, 1.2rem);
    }
    .transit-head {
      border-top: none;
      padding-top: 0;
      font-size: clamp(0.82rem, 1.2vw, 0.92rem);
      color: var(--muted);
      letter-spacing: 0.04em;
      text-transform: uppercase;
      font-weight: 600;
    }
    .transit-time {
      font-size: clamp(2.4rem, 4.1vw, 2.9rem);
      font-weight: 700;
      text-align: left;
    }
    .transit-time.live {
      color: var(--accent);
    }
    .transit-fallback {
      margin: 0;
    }
    @media (max-width: 900px) {
      .shell { padding: 1rem; }
      .header-panel {
        min-height: auto;
      }
      .transit-row {
        gap: 0.6rem;
      }
    }
  </style>
</head>
<body>
  <div class=\"shell\">
    <div class=\"grid\">
      <section class=\"panel header-panel\">
        <div class=\"time-box\">
          <div class=\"tag\">Live clock</div>
          <div id=\"clock\" class=\"clock\">--:--:--</div>
          <div id=\"date\" class=\"date\">--</div>
        </div>
      </section>
      <section class=\"panel departures-panel\">
        <div>
          <div class=\"tag\">Next departures</div>
          <h3>Merisotilaantori</h3>
        </div>
        <div class=\"transit-table\">
          <div class=\"transit-row transit-head\">
            <span>Leave home at</span>
            <span>Tram departs at</span>
          </div>
          <div id=\"transit-list\" class=\"transit-table-body\">
            <p class=\"muted transit-fallback\">Loading\u2026</p>
          </div>
        </div>
        <p id=\"transit-updated\" class=\"muted\"></p>
      </section>
      <section class=\"panel sensor-panel\">
        <div class=\"sensor-table\">
          <div class=\"sensor-row sensor-head\">
            <span>Sensor</span>
            <span>Temperature</span>
            <span>Humidity</span>
            <span>Pressure</span>
          </div>
          <div id=\"sensor-table-body\"></div>
        </div>
      </section>
    </div>
  </div>
  <script>
    const elements = {
      clock: document.getElementById('clock'),
      date: document.getElementById('date'),
      sensorTableBody: document.getElementById('sensor-table-body')
    };

    function updateClock() {
      const now = new Date();
      elements.clock.textContent = now.toLocaleTimeString('en-GB');
      elements.date.textContent = now.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
    }

    function renderSensorRows(sensors) {
      if (!elements.sensorTableBody) {
        return;
      }
      const rows = (sensors || []).map((sensor) => {
        const name = sensor.name || '--';
        const temperature = sensor.temperature || '--';
        const humidity = sensor.humidity || '--';
        const pressure = sensor.pressure || '--';
        return `<div class="sensor-row"><span>${name}</span><span>${temperature}</span><span>${humidity}</span><span>${pressure}</span></div>`;
      }).join('');
      elements.sensorTableBody.innerHTML = rows;
    }

    function updateDashboard(data) {
      renderSensorRows(data.sensors || []);
    }

    async function refreshData() {
      try {
        const response = await fetch('/api/data');
        const data = await response.json();
        updateDashboard(data);
      } catch (error) {
        console.error(error);
      }
    }

    updateClock();
    refreshData();
    setInterval(updateClock, 1000);
    setInterval(refreshData, 3000);

    function leaveHomeAt(departureTime, offsetMinutes = 4) {
      const match = /^(\\d{1,2}):(\\d{2})$/.exec(String(departureTime || ''));
      if (!match) {
        return '--';
      }
      const hours = Number(match[1]);
      const minutes = Number(match[2]);
      if (Number.isNaN(hours) || Number.isNaN(minutes) || hours < 0 || hours > 23 || minutes < 0 || minutes > 59) {
        return '--';
      }
      const minutesPerDay = 24 * 60;
      const totalMinutes = (((hours * 60) + minutes - offsetMinutes) % minutesPerDay + minutesPerDay) % minutesPerDay;
      const leaveHours = Math.floor(totalMinutes / 60);
      const leaveMinutes = totalMinutes % 60;
      return `${String(leaveHours).padStart(2, '0')}:${String(leaveMinutes).padStart(2, '0')}`;
    }

    async function fetchTransit() {
      try {
        const resp = await fetch('/api/transit');
        const data = await resp.json();
        const departures = data.departures;
        const list = document.getElementById('transit-list');
        if (data.status) {
          list.innerHTML = `<p class=\"muted transit-fallback\">${data.status}</p>`;
        } else if (!departures.length) {
          list.innerHTML = '<p class=\"muted transit-fallback\">No departures available.</p>';
        } else {
          list.innerHTML = departures.map((a) => {
            const live = a.is_realtime;
            const departureTime = live ? a.realtime : a.scheduled;
            const leaveTime = leaveHomeAt(departureTime, 4);
            const liveClass = live ? ' live' : '';
            return `<div class=\"transit-row\"><strong class=\"transit-time\">${leaveTime}</strong><strong class=\"transit-time${liveClass}\">${departureTime}</strong></div>`;
          }).join('');
        }
        document.getElementById('transit-updated').textContent =
          'Updated ' + new Date().toLocaleTimeString('en-GB');
      } catch (e) {
        console.error(e);
      }
    }

    fetchTransit();
    setInterval(fetchTransit, 300000);
  </script>
</body>
</html>
        """


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


if __name__ == "__main__":
    service.start()
    transit_service.start()
    main()

