import asyncio
import threading
import time
from datetime import datetime

from pidisplay.config import RUUVITAG_AVAILABLE, RUUVITAG_SENSORS, RuuviTagSensor


class DashboardService:
    def __init__(self, refresh_seconds: int = 10) -> None:
        self.refresh_seconds = refresh_seconds
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
        sensors = []
        successful_reads = 0
        for name, mac in RUUVITAG_SENSORS:
            sensor = await self._collect_single_sensor_state(name, mac)
            if sensor:
                sensors.append(sensor)
                successful_reads += 1
            else:
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

        if successful_reads == 0:
            self._log_ruuvi("No sensor readings received from any configured sensor")
            return {}

        status = "Live sensor" if successful_reads == len(RUUVITAG_SENSORS) else "Partial sensor data"
        signal = "OK" if successful_reads == len(RUUVITAG_SENSORS) else "Degraded"
        self._log_ruuvi(f"Collected {successful_reads}/{len(RUUVITAG_SENSORS)} sensor readings")

        return {
            "status": status,
            "source": "ruuvi",
            "temperature": "--",
            "humidity": "--",
            "pressure": "--",
            "battery": "--",
            "signal": signal,
            "mac": "--",
            "sensor_name": "--",
            "sensors": sensors,
        }

    async def _collect_single_sensor_state(self, name: str, mac: str, timeout_seconds: float = 4.0) -> dict | None:
        self._log_ruuvi(f"Reading sensor {name} ({mac})")

        async def _first_payload() -> object | None:
            if RuuviTagSensor is None:
                return None
            async for found_data in RuuviTagSensor.get_data_async([mac]):
                if not isinstance(found_data, (tuple, list)) or len(found_data) != 2:
                    self._log_ruuvi(f"Malformed reading for {name}: {found_data!r}")
                    continue

                found_mac, payload = found_data
                if found_mac != mac:
                    self._log_ruuvi(f"Ignoring unexpected MAC {found_mac} while reading {name}")
                    continue
                return payload
            return None

        try:
            payload = await asyncio.wait_for(_first_payload(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            self._log_ruuvi(f"Timeout while reading {name} ({mac})")
            return None
        except Exception as exc:
            self._log_ruuvi(f"Read error for {name} ({mac}): {exc}")
            return None

        if not isinstance(payload, dict):
            self._log_ruuvi(f"Missing payload for {name} ({mac})")
            return None

        formatted = {
            "name": name,
            "temperature": self._format_value(payload.get("temperature")),
            "humidity": self._format_value(payload.get("humidity")),
            "pressure": self._format_value(payload.get("pressure")),
            "battery": self._format_value(payload.get("battery")),
            "mac": mac,
        }
        self._log_ruuvi(
            f"Read OK {name} ({mac}) temp={formatted['temperature']} hum={formatted['humidity']} "
            f"pres={formatted['pressure']} batt={formatted['battery']}"
        )
        return formatted

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
