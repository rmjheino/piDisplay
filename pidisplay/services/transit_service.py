import json
import threading
import urllib.error
import urllib.request
from datetime import datetime
from urllib.parse import urlencode


class TransitService:
    _API_URL = "https://api.digitransit.fi/routing/v2/hsl/gtfs/v1"
    _STOP_NAME = "Merisotilaantori"
    _ALERT_ROUTE = "HSL:1004"

    def __init__(self, stop_id: str, api_key: str, refresh_seconds: int = 300) -> None:
        self._stop_id = stop_id
        self._api_key = api_key
        self._refresh_seconds = refresh_seconds
        self._departures: list = []
        self._has_alerts = False
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

    def get_has_alerts(self) -> bool:
        with self._lock:
            return self._has_alerts

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
                self._has_alerts = False
                self._status = "No API key set (DIGITRANSIT_API_KEY)"
            return

        try:
            if not self._stop_id:
                self._stop_id = self._resolve_stop_id()
            if self._stop_id:
                departures, has_alerts = self._fetch_transit_state()
                with self._lock:
                    self._departures = departures
                    self._has_alerts = has_alerts
                    self._status = ""
        except Exception as exc:
            print(f"[TransitService] {exc}", flush=True)
            with self._lock:
                self._has_alerts = False
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

    def _fetch_transit_state(self) -> tuple[list, bool]:
        query = (
            '{ stop(id: "%s") { stoptimesWithoutPatterns(numberOfDepartures: 3) {'
            ' serviceDay scheduledDeparture realtimeDeparture realtime } } '
            'alerts(route: ["%s"]) { alertDescriptionText } }'
        ) % (self._stop_id, self._ALERT_ROUTE)
        data = self._graphql(query)
        payload = data.get("data", {})
        stoptimes = payload.get("stop", {}).get("stoptimesWithoutPatterns", [])
        departures = [
            {
                "scheduled": self._epoch_hhmm(st["serviceDay"] + st["scheduledDeparture"]),
                "realtime": self._epoch_hhmm(st["serviceDay"] + st["realtimeDeparture"]),
                "is_realtime": st.get("realtime", False),
            }
            for st in stoptimes
        ]
        alerts = payload.get("alerts", [])
        return departures, bool(alerts)

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
