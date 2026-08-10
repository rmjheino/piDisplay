import asyncio
import threading
import time
from datetime import datetime

from pidisplay.config import RUUVITAG_AVAILABLE, RUUVITAG_SENSORS, RuuviTagSensor


class DashboardService:
    def __init__(self, refresh_seconds: int = 10, scan_seconds: int = 8) -> None:
        self.refresh_seconds = refresh_seconds
        self.scan_seconds = scan_seconds
        self._async_loop: asyncio.AbstractEventLoop | None = None
        self._state = {
            "status": "Starting",
            "source": "ruuvi",
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
        self._async_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._async_loop)
        try:
            next_run = time.monotonic()
            while not self._stop_event.is_set():
                self._refresh_state()
                next_run += self.refresh_seconds
                sleep_for = max(0.0, next_run - time.monotonic())
                self._stop_event.wait(sleep_for)
        finally:
            self._async_loop.close()
            self._async_loop = None
            asyncio.set_event_loop(None)

    def _refresh_state(self) -> None:
        if RUUVITAG_AVAILABLE:
            try:
                if self._async_loop is None:
                    self._log_ruuvi("Async loop is not initialized; skipping live sensor refresh")
                    state = {}
                else:
                    state = self._async_loop.run_until_complete(self._collect_ruuvi_state())
                if state:
                    self._set_state(state)
                    return
            except Exception as exc:
                self._log_ruuvi(f"Refresh error: {exc}")

        if not RUUVITAG_AVAILABLE:
            self._log_ruuvi("ruuvitag_sensor is not available in this environment")
        else:
            self._log_ruuvi("Falling back to unavailable state")

        self._set_state(self._build_unavailable_state())

    def _set_state(self, state: dict) -> None:
        with self._lock:
            now = datetime.now()
            state["timestamp"] = now.strftime("%H:%M:%S")
            state["date"] = now.strftime("%d.%m.%Y")
            self._state = state

    async def _collect_ruuvi_state(self) -> dict:
        sensor_rows = await self._collect_available_sensor_rows()
        if not sensor_rows:
            self._log_ruuvi("No sensor readings received from any visible sensor")
            return {}

        self._log_ruuvi(f"Collected {len(sensor_rows)} visible sensor readings")
        first_sensor = sensor_rows[0]

        return {
            "status": "Live sensor",
            "source": "ruuvi",
            "temperature": "--",
            "humidity": "--",
            "pressure": "--",
            "battery": "--",
            "signal": "OK",
            "mac": first_sensor["mac"],
            "sensor_name": first_sensor["name"],
            "sensors": sensor_rows,
        }

    async def _collect_available_sensor_rows(self) -> list[dict]:
        if RuuviTagSensor is None:
            return []

        known_sensor_names = {mac: name for name, mac in RUUVITAG_SENSORS}
        known_mac_order = {mac: index for index, (_, mac) in enumerate(RUUVITAG_SENSORS)}
        sensor_rows_by_mac: dict[str, dict] = {}
        deadline = time.monotonic() + self.scan_seconds

        self._log_ruuvi("Reading visible sensors")

        try:
            stream = RuuviTagSensor.get_data_async([])
            while time.monotonic() < deadline:
                wait_seconds = max(0.0, deadline - time.monotonic())
                found_data = await asyncio.wait_for(anext(stream), timeout=wait_seconds)
                if not isinstance(found_data, (tuple, list)) or len(found_data) != 2:
                    self._log_ruuvi(f"Malformed reading: {found_data!r}")
                    continue

                found_mac, payload = found_data
                if not isinstance(payload, dict):
                    self._log_ruuvi(f"Missing payload for {found_mac}")
                    continue

                sensor_name = known_sensor_names.get(found_mac, found_mac)
                sensor_row = {
                    "name": sensor_name,
                    "temperature": self._format_value(payload.get("temperature")),
                    "humidity": self._format_value(payload.get("humidity")),
                    "pressure": self._format_value(payload.get("pressure")),
                    "battery": self._format_value(payload.get("battery")),
                    "mac": found_mac,
                }
                if found_mac in sensor_rows_by_mac:
                    self._log_ruuvi(f"Read update {sensor_row['name']} ({found_mac})")
                else:
                    self._log_ruuvi(f"Read OK {sensor_row['name']} ({found_mac})")
                sensor_rows_by_mac[found_mac] = sensor_row
        except asyncio.TimeoutError:
            pass
        except StopAsyncIteration:
            pass
        except Exception as exc:
            self._log_ruuvi(f"Scan error: {exc}")

        sensor_rows = list(sensor_rows_by_mac.values())
        sensor_rows.sort(key=lambda row: (known_mac_order.get(row["mac"], len(known_mac_order)), row["name"]))
        return sensor_rows

    def _build_unavailable_state(self) -> dict:
        sensors = []
        for name, mac in RUUVITAG_SENSORS:
            sensors.append(
                {
                    "name": name,
                    "temperature": "--",
                    "humidity": "--",
                    "pressure": "--",
                    "battery": "--",
                    "mac": mac,
                }
            )

        return {
            "status": "Sensor unavailable",
            "source": "ruuvi",
            "temperature": "--",
            "humidity": "--",
            "pressure": "--",
            "battery": "--",
            "signal": "Unavailable",
            "mac": "--",
            "sensor_name": "--",
            "sensors": sensors,
        }

    @staticmethod
    def _log_ruuvi(message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[Ruuvi {timestamp}] {message}", flush=True)

    @staticmethod
    def _format_value(value: object) -> str:
        if value in (None, "", "--"):
            return "--"
        if isinstance(value, float):
            return f"{value:.1f}"
        return str(value)
