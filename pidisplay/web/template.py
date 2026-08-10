from pathlib import Path
import base64

_BASE_DIR = Path(__file__).resolve().parent


def _read_asset(filename: str) -> str:
    return (_BASE_DIR / filename).read_text(encoding="utf-8")


def build_dashboard_page() -> str:
    html = _read_asset("dashboard.html")
    css = _read_asset("dashboard.css")
    logo_bytes = (_BASE_DIR.parent.parent / "hsl.png").read_bytes()
    logo_src = "data:image/png;base64," + base64.b64encode(logo_bytes).decode("ascii")
    return html.replace("{{ DASHBOARD_CSS }}", css).replace("{{ HSL_LOGO_SRC }}", logo_src)
