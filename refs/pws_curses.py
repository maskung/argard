import curses
import json
import locale
import time
from typing import Any, Dict, List, Tuple
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


API_URL = (
    "https://api.weather.com/v2/pws/observations/current?"
    "stationId=IMAKHA6&format=json&units=m&apiKey=6cc3c0b18bf9490183c0b18bf9b9017c"
)
REFRESH_SECONDS = 30


def fetch_observation() -> Tuple[Dict[str, Any], str]:
    """
    Fetch current observation JSON and return (observation_dict, error_message).
    If successful, error_message is an empty string.
    """
    headers = {
        "User-Agent": "pws-curses/1.0 (+https://api.weather.com)",
        "Accept": "application/json",
    }
    req = Request(API_URL, headers=headers)
    try:
        with urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return {}, f"HTTP {resp.status}"
            raw = resp.read()
            data = json.loads(raw.decode("utf-8"))
            observations = data.get("observations") or []
            if not observations:
                return {}, "No observations in response"
            return observations[0], ""
    except HTTPError as e:
        return {}, f"HTTPError {e.code}: {e.reason}"
    except URLError as e:
        return {}, f"URLError: {getattr(e, 'reason', str(e))}"
    except Exception as e:  # noqa: BLE001 (keep broad to show message in UI)
        return {}, f"Error: {str(e)}"


def build_rows(obs: Dict[str, Any]) -> List[Tuple[str, str]]:
    metric = obs.get("metric") or {}
    rows = [
        ("Station ID", str(obs.get("stationID", "-"))),
        ("Obs Time (Local)", str(obs.get("obsTimeLocal", "-"))),
        ("UV", str(obs.get("uv", "-"))),
        ("Wind Dir (°)", str(obs.get("winddir", "-"))),
        ("Humidity (%)", str(obs.get("humidity", "-"))),
        ("QC Status", str(obs.get("qcStatus", "-"))),
        ("Solar Radiation", str(obs.get("solarRadiation", "-"))),
        ("Temp (°C)", str(metric.get("temp", "-"))),
        ("Heat Index (°C)", str(metric.get("heatIndex", "-"))),
        ("Dew Point (°C)", str(metric.get("dewpt", "-"))),
        ("Wind Chill (°C)", str(metric.get("windChill", "-"))),
        ("Wind Speed (m/s)", str(metric.get("windSpeed", "-"))),
        ("Wind Gust (m/s)", str(metric.get("windGust", "-"))),
        ("Pressure (hPa)", str(metric.get("pressure", "-"))),
        ("Precip Rate (mm/h)", str(metric.get("precipRate", "-"))),
        ("Precip Total (mm)", str(metric.get("precipTotal", "-"))),
    ]
    return rows


def draw_centered(stdscr, y: int, text: str, attr=0):
    height, width = stdscr.getmaxyx()
    x = max(0, (width - len(text)) // 2)
    if 0 <= y < height:
        stdscr.addnstr(y, x, text, max(0, width - x), attr)


def draw_table(stdscr, start_y: int, rows: List[Tuple[str, str]]):
    height, width = stdscr.getmaxyx()
    label_width = max((len(label) for label, _ in rows), default=10)
    label_width = min(label_width, max(10, width // 3))
    value_width = max(10, width - label_width - 6)

    header_label = "Field"
    header_value = "Value"
    stdscr.addnstr(start_y, 2, header_label, label_width, curses.A_BOLD)
    stdscr.addnstr(start_y, 4 + label_width, header_value, value_width, curses.A_BOLD)

    sep_line = "-" * min(width - 4, label_width + value_width + 2)
    stdscr.addnstr(start_y + 1, 2, sep_line, len(sep_line))

    y = start_y + 2
    for label, value in rows:
        if y >= height - 2:
            break
        stdscr.addnstr(y, 2, label.ljust(label_width), label_width)
        stdscr.addnstr(y, 4 + label_width, str(value), value_width)
        y += 1


def main(stdscr):
    locale.setlocale(locale.LC_ALL, "")
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(200)

    last_fetch_ts = 0.0
    last_error = ""
    observation: Dict[str, Any] = {}

    while True:
        now = time.monotonic()
        should_refresh = (now - last_fetch_ts) > REFRESH_SECONDS or not observation
        if should_refresh:
            obs, err = fetch_observation()
            if not err:
                observation = obs
                last_error = ""
                last_fetch_ts = now
            else:
                last_error = err
                last_fetch_ts = now

        stdscr.erase()
        height, width = stdscr.getmaxyx()

        title = "PWS Realtime Weather - Station IMAKHA6"
        draw_centered(stdscr, 0, title, curses.A_BOLD)
        subtitle = "Data source: api.weather.com | press r=refresh, q=quit"
        draw_centered(stdscr, 1, subtitle)

        if last_error:
            error_text = f"Last error: {last_error}"
            draw_centered(stdscr, 3, error_text, curses.A_BOLD)
        else:
            info_line = f"Last update: {time.strftime('%Y-%m-%d %H:%M:%S')} | Auto-refresh {REFRESH_SECONDS}s"
            draw_centered(stdscr, 3, info_line)

        rows: List[Tuple[str, str]] = build_rows(observation) if observation else []

        needed_height = 6 + len(rows)
        if height < needed_height or width < 40:
            warning = "Please enlarge the terminal window to display the table."
            draw_centered(stdscr, height // 2, warning, curses.A_BOLD)
        else:
            draw_table(stdscr, 5, rows)

        stdscr.refresh()

        try:
            ch = stdscr.getch()
        except Exception:
            ch = -1

        if ch in (ord('q'), ord('Q')):
            break
        if ch in (ord('r'), ord('R')):
            # Force refresh on next loop
            last_fetch_ts = 0.0


if __name__ == "__main__":
    curses.wrapper(main)


