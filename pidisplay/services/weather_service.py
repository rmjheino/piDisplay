import asyncio
import threading
from datetime import datetime

try:
    import python_weather as weather
except Exception:  # pragma: no cover - depends on runtime environment
    weather = None


class WeatherService:
    def __init__(self, refresh_seconds: int = 3600, city: str = "Helsinki") -> None:
        self._refresh_seconds = refresh_seconds
        self._city = city
        self._lock = threading.Lock()
        self._state: dict = {
            "status": "Unavailable",
            "hours": [],
            "updated_at": "",
        }
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
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
            self._refresh()
            self._stop_event.wait(self._refresh_seconds)

    def _refresh(self) -> None:
        try:
            if weather is None:
                raise RuntimeError("python-weather is not installed")

            forecast = asyncio.run(self._fetch_forecast())
            state = self._normalize_daily_forecast(forecast)
            with self._lock:
                self._state = state
        except Exception as exc:  # pragma: no cover - runtime dependent
            print(f"[WeatherService] {exc}", flush=True)
            with self._lock:
                self._state = {
                    "status": "Unavailable",
                    "hours": [],
                    "updated_at": "",
                    "error": str(exc),
                }

    async def _fetch_forecast(self) -> object:
        client = weather.Client(unit=weather.METRIC)
        try:
            return await client.get(self._city)
        finally:
            await client.close()

    def _normalize_daily_forecast(self, payload: object, now: datetime | None = None) -> dict:
        if payload is None:
            return {
                "status": "Unavailable",
                "hours": [],
                "updated_at": self._timestamp(),
            }

        daily_forecasts = self._get_field(payload, "daily_forecasts")
        if not daily_forecasts:
            return {
                "status": "Unavailable",
                "hours": [],
                "updated_at": self._timestamp(),
            }

        entries = []
        for day in daily_forecasts:
            day_date = self._get_field(day, "date")
            for forecast in self._get_field(day, "hourly_forecasts") or []:
                entries.append((self._combine_datetime(day_date, self._get_field(forecast, "time")), forecast))
        entries.sort(key=lambda pair: pair[0] or datetime.min)

        now = now or datetime.now()
        start_index = 0
        best_diff = None
        for index, (entry_dt, _) in enumerate(entries):
            if entry_dt is None:
                continue
            diff = abs((entry_dt - now).total_seconds())
            if best_diff is None or diff < best_diff:
                best_diff = diff
                start_index = index

        compact_hours = [self._format_hour_entry(forecast) for _, forecast in entries[start_index : start_index + 4]]

        return {
            "status": "Live" if compact_hours else "Unavailable",
            "hours": compact_hours,
            "updated_at": self._timestamp(),
        }

    def _format_hour_entry(self, forecast: object) -> dict:
        rain_value = self._get_field(forecast, "chance_of_rain")
        if rain_value is None:
            rain_value = self._get_field(forecast, "chances_of_rain")
        return {
            "time": self._extract_hour(self._get_field(forecast, "time")),
            "temperature": self._format_temperature(self._get_field(forecast, "temperature")),
            "chance_of_rain": self._format_percent(rain_value),
        }

    @staticmethod
    def _get_field(obj: object, name: str) -> object:
        if isinstance(obj, dict):
            return obj.get(name)
        return getattr(obj, name, None)

    @staticmethod
    def _combine_datetime(day_value: object, time_value: object) -> datetime | None:
        date_part = None
        if isinstance(day_value, datetime):
            date_part = day_value.date()
        elif hasattr(day_value, "year") and hasattr(day_value, "month"):
            date_part = day_value
        elif isinstance(day_value, str):
            try:
                date_part = datetime.strptime(day_value[:10], "%Y-%m-%d").date()
            except ValueError:
                date_part = None

        time_part = None
        if isinstance(time_value, datetime):
            date_part = date_part or time_value.date()
            time_part = time_value.time()
        elif hasattr(time_value, "hour") and hasattr(time_value, "minute"):
            time_part = time_value
        elif isinstance(time_value, str):
            raw = time_value.split(" ", 1)[1] if " " in time_value else time_value
            try:
                time_part = datetime.strptime(raw[:5], "%H:%M").time()
            except ValueError:
                time_part = None
            if date_part is None and " " in time_value:
                try:
                    date_part = datetime.strptime(time_value.split(" ", 1)[0], "%Y-%m-%d").date()
                except ValueError:
                    date_part = None

        if date_part is None or time_part is None:
            return None
        return datetime.combine(date_part, time_part)

    @staticmethod
    def _extract_hour(value: object) -> str:
        if isinstance(value, str):
            if " " in value:
                value = value.split(" ", 1)[1]
            if ":" in value:
                return value[:5]
        if hasattr(value, "strftime"):
            try:
                return value.strftime("%H:%M")
            except Exception:
                return "--"
        return "--"

    @staticmethod
    def _format_temperature(value: object) -> str:
        try:
            return f"{float(value):.0f}°C"
        except (TypeError, ValueError):
            return "--"

    @staticmethod
    def _format_percent(value: object) -> str:
        try:
            return f"{int(float(value))}%"
        except (TypeError, ValueError):
            return "--"

    @staticmethod
    def _timestamp() -> str:
        return datetime.now().strftime("%H:%M")
