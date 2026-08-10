import asyncio
import threading
import time
from datetime import datetime

from pidisplay.config import RUUVITAG_AVAILABLE, RUUVITAG_SENSORS, RuuviTagSensor

_MIN_BACKOFF_SECONDS = 1.0
_MAX_BACKOFF_SECONDS = 60.0


class DashboardService:
    """Keeps a single long-lived BLE scan running and serves the latest cached readings.

    A previous version restarted the RuuviTag BLE scan on every refresh cycle, which
    raced with BlueZ's discovery teardown and surfaced as org.bluez.Error.InProgress.
    This version starts exactly one scan for the service's lifetime; HTTP reads only
    ever consult the in-memory cache, never touch BLE.
    """

    def __init__(self, stale_after_seconds: int = 45) -> None:
        self.stale_after_seconds = stale_after_seconds
        self._lock = threading.Lock()
        self._latest: dict[str, dict] = {}
        self._has_ever_read = False

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._loop is not None and self._task is not None:
            self._loop.call_soon_threadsafe(self._task.cancel)
        if self._thread:
            self._thread.join(timeout=5)

    def get_state(self) -> dict:
        with self._lock:
            cache = {mac: dict(entry) for mac, entry in self._latest.items()}
            has_ever_read = self._has_ever_read
        return self._build_state(cache, has_ever_read)

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._task = self._loop.create_task(self._scan_forever())
            self._loop.run_until_complete(self._task)
        except asyncio.CancelledError:
            pass
        finally:
            self._loop.close()
            self._loop = None
            self._task = None
            asyncio.set_event_loop(None)

    async def _scan_forever(self) -> None:
        if not RUUVITAG_AVAILABLE:
            self._log_ruuvi("ruuvitag_sensor is not available in this environment")
            return

        backoff = _MIN_BACKOFF_SECONDS
        while not self._stop_event.is_set():
            stream = None
            try:
                stream = RuuviTagSensor.get_data_async([])
                async for found_data in stream:
                    self._handle_reading(found_data)
                    backoff = _MIN_BACKOFF_SECONDS
                # Stream ended on its own; treat like an error and retry below.
                self._log_ruuvi("Scan stream ended unexpectedly; restarting")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._log_ruuvi(f"Scan error: {exc}; retrying in {backoff:.0f}s")
            finally:
                if stream is not None:
                    await stream.aclose()

            try:
                await asyncio.sleep(backoff)
            except asyncio.CancelledError:
                raise
            backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)

    def _handle_reading(self, found_data: object) -> None:
        if not isinstance(found_data, (tuple, list)) or len(found_data) != 2:
            self._log_ruuvi(f"Malformed reading: {found_data!r}")
            return

        mac, payload = found_data
        if not isinstance(payload, dict):
            self._log_ruuvi(f"Missing payload for {mac}")
            return

        entry = {
            "temperature": self._format_value(payload.get("temperature")),
            "humidity": self._format_value(payload.get("humidity")),
            "pressure": self._format_value(payload.get("pressure")),
            "battery": self._format_value(payload.get("battery")),
            "last_seen": time.monotonic(),
        }
        with self._lock:
            is_update = mac in self._latest
            self._latest[mac] = entry
            self._has_ever_read = True
        self._log_ruuvi(f"{'Read update' if is_update else 'Read OK'} {mac}")

    def _build_state(self, cache: dict[str, dict], has_ever_read: bool) -> dict:
        now = time.monotonic()
        known_mac_order = {mac: index for index, (_, mac) in enumerate(RUUVITAG_SENSORS)}

        sensor_rows = []
        for name, mac in RUUVITAG_SENSORS:
            sensor_rows.append(self._sensor_row(name, mac, cache.get(mac), now))

        for mac, entry in cache.items():
            if mac in known_mac_order:
                continue
            sensor_rows.append(self._sensor_row(mac, mac, entry, now))
        sensor_rows.sort(key=lambda row: (known_mac_order.get(row["mac"], len(known_mac_order)), row["name"]))

        fresh_rows = [row for row in sensor_rows if row["fresh"]]

        if not RUUVITAG_AVAILABLE:
            status = "Unavailable"
        elif fresh_rows:
            status = "Live sensor"
        elif has_ever_read:
            status = "Stale"
        else:
            status = "Starting"

        first = fresh_rows[0] if fresh_rows else None
        now_dt = datetime.now()

        return {
            "status": status,
            "source": "ruuvi",
            "timestamp": now_dt.strftime("%H:%M:%S"),
            "date": now_dt.strftime("%d.%m.%Y"),
            "temperature": first["temperature"] if first else "--",
            "humidity": first["humidity"] if first else "--",
            "pressure": first["pressure"] if first else "--",
            "battery": first["battery"] if first else "--",
            "signal": "OK" if fresh_rows else "Unavailable",
            "mac": first["mac"] if first else "--",
            "sensor_name": first["name"] if first else "--",
            "sensors": [{k: v for k, v in row.items() if k != "fresh"} for row in sensor_rows],
        }

    def _sensor_row(self, name: str, mac: str, entry: dict | None, now: float) -> dict:
        fresh = entry is not None and (now - entry["last_seen"]) <= self.stale_after_seconds
        if fresh:
            return {
                "name": name,
                "temperature": entry["temperature"],
                "humidity": entry["humidity"],
                "pressure": entry["pressure"],
                "battery": entry["battery"],
                "mac": mac,
                "fresh": True,
            }
        return {
            "name": name,
            "temperature": "--",
            "humidity": "--",
            "pressure": "--",
            "battery": "--",
            "mac": mac,
            "fresh": False,
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
