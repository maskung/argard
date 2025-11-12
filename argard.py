import json
import sys
import time
import math
import threading
import queue
import configparser
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from rich import box
from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns

# --- API Configuration ---
config = configparser.ConfigParser()
config.read('config.ini')

# Weather.com API
weather_com_config = config['WeatherCom']
STATION_ID = weather_com_config.get('STATION_ID')
WEATHER_COM_API_KEY = weather_com_config.get('API_KEY')
API_URL = (
    f"https://api.weather.com/v2/pws/observations/current?"
    f"stationId={STATION_ID}&format=json&units=m&apiKey={WEATHER_COM_API_KEY}"
)

# OpenWeather API
openweather_config = config['OpenWeather']
OPENWEATHER_API_KEY = openweather_config.get('API_KEY')
LATITUDE = openweather_config.getfloat('LATITUDE')
LONGITUDE = openweather_config.getfloat('LONGITUDE')
OPENWEATHER_API_URL = (
    f"https://api.openweathermap.org/data/3.0/onecall?"
    f"lat={LATITUDE}&lon={LONGITUDE}&exclude=minutely,daily,alerts&units=metric&appid="
    f"{OPENWEATHER_API_KEY}"
)

# General Settings
general_config = config['General']
REFRESH_SECONDS = general_config.getint('REFRESH_SECONDS')

# --- Display Mode State ---
class DisplayMode:
    def __init__(self):
        self.full_forecast = False
        self.lock = threading.Lock()
        self.mode_changed = False
        self.auto_switch_interval = 10  # Auto-switch every 10 seconds for testing
        self.last_switch_time = time.time()
        self.enable_auto_switch = False  # Disable auto-switch, use manual key press

    def toggle_forecast(self):
        with self.lock:
            self.full_forecast = not self.full_forecast
            self.mode_changed = True

    def auto_toggle(self):
        """Auto toggle forecast mode for testing purposes"""
        with self.lock:
            if self.enable_auto_switch:
                current_time = time.time()
                if current_time - self.last_switch_time >= self.auto_switch_interval:
                    self.full_forecast = not self.full_forecast
                    self.mode_changed = True
                    self.last_switch_time = current_time
                    return True
            return False

    def is_full_forecast(self):
        with self.lock:
            return self.full_forecast

    def has_mode_changed(self):
        with self.lock:
            if self.mode_changed:
                self.mode_changed = False
                return True
            return False

    def clear_mode_change(self):
        with self.lock:
            self.mode_changed = False

display_mode = DisplayMode()

# --- Data Fetching Functions ---

def fetch_observation() -> Tuple[Dict[str, Any], str]:
    headers = {"User-Agent": "pws-rich-dashboard/1.0", "Accept": "application/json"}
    req = Request(API_URL, headers=headers)
    try:
        with urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return {}, f"HTTP {resp.status}"
            data = json.loads(resp.read().decode("utf-8"))
            obs_list = data.get("observations") or []
            return (obs_list[0], "") if obs_list else ({}, "No observations")
    except Exception as e:
        return {}, f"Error: {e}"

def fetch_hourly_forecast() -> Tuple[List[Dict[str, Any]], str]:
    headers = {"User-Agent": "pws-rich-dashboard/1.0", "Accept": "application/json"}
    req = Request(OPENWEATHER_API_URL, headers=headers)
    try:
        with urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return [], f"HTTP {resp.status}"
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("hourly", []), ""
    except Exception as e:
        return [], f"Error: {e}"

# --- Helper Functions ---

def ms_to_kmh(v): return round(float(v) * 3.6, 1) if isinstance(v, (int, float)) else v
def deg_to_compass(deg):
    try: d = float(deg) % 360
    except: return "-"
    return ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"][int((d+11.25)//22.5)%16]
def deg_to_arrow(deg):
    try: d = float(deg) % 360
    except: return "?"
    return ["↑","↗","→","↘","↓","↙","←","↖"][int((d+22.5)//45)%8]
def get_feeling_level(t):
    try:
        t = float(t)
        if t >= 40: return "🥵 Dangerously Hot", "bold red"
        if t >= 35: return "🔥 Very Hot", "red"
        if t >= 28: return "😊 Warm", "yellow"
        if t >= 20: return "😌 Comfortable", "green"
        return "🥶 Cool", "cyan"
    except: return "🤷 N/A", "dim"
def get_wind_description(s):
    try:
        s = float(s)
        if s < 2: return "🧘 Calm", "dim"
        if s < 12: return "🍃 Light", "green"
        if s < 29: return "💨 Moderate", "yellow"
        if s < 50: return "🌬️ Strong", "orange3"
        if s < 75: return "🌪️ Gale", "red"
        if s < 103: return "⛈️ Storm", "bold red"
        return "🌀 Hurricane", "bold magenta"
    except: return "🤷 N/A", "dim"
def get_rain_description(r):
    try:
        r = float(r)
        if r == 0: return "☀️ No Rain", "dim"
        if r < 2.5: return "💧 Light", "green"
        if r < 10: return "🌧️  Moderate", "yellow"
        if r < 50: return "⛈️   Heavy", "red"
        return "🌊 Violent", "bold magenta"
    except: return "🤷 N/A", "dim"
def get_uv_description(u):
    try:
        u = float(u)
        if u <= 2: return "😊 Low", "green"
        if u <= 5: return "😎 Moderate", "yellow"
        if u <= 7: return "😮 High", "orange3"
        if u <= 10: return "🥵 Very High", "red"
        return "😱 Extreme", "bold magenta"
    except: return "🤷 N/A", "dim"
def get_weather_emoji(icon):
    if "01" in icon: return "☀️" if "d" in icon else "🌙"
    if "02" in icon: return "🌤️" if "d" in icon else "☁️"
    if "03" in icon or "04" in icon: return "☁️"
    if "09" in icon or "10" in icon: return "🌧️"
    if "11" in icon: return "⛈️"
    if "13" in icon: return "❄️"
    if "50" in icon: return "🌫️"
    return "❓"

# --- Panel Creation Functions ---

def header_panel(obs, error): # (Restored)
    station = obs.get("stationID", "-")
    obs_time = obs.get("obsTimeLocal") or obs.get("obsTimeUtc") or "-"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = f"🌤️ Station: {station} | 📅 Obs: {obs_time} | 🕐 Now: {now_str}"
    if error: status += f"  •  [bold red]❌ Error:[/] {error}"
    return Panel(
        Text(status, justify="center"), 
        style="bold", 
        box=box.SIMPLE, 
        padding=(0, 1),
        subtitle="v1.1.0",
        subtitle_align="right"
    )

def thermal_panel(obs): # (Restored)
    m = obs.get("metric") or {}
    temp, heat_index, dew, chill = m.get("temp","-"), m.get("heatIndex","-"), m.get("dewpt","-"), m.get("windChill","-")
    feeling, style = get_feeling_level(heat_index)
    grid = Table.grid(padding=(0, 2))
    grid.add_row("🌡️  Temperature", f"{temp} °C")
    grid.add_row("🔥 Feels like", f"{heat_index} °C")
    grid.add_row("🤔 Feeling", Text(feeling, style=style))
    grid.add_row("💧 Dew point", f"{dew} °C")
    grid.add_row("❄️  Wind chill", f"{chill} °C")
    return Panel(Align.center(grid), title="🌡️  Thermal Comfort", box=box.ROUNDED, padding=(0, 1))

def wind_panel(obs): # (Restored)
    m = obs.get("metric") or {}
    speed_kmh = ms_to_kmh(m.get("windSpeed", "-"))
    gust_kmh = ms_to_kmh(m.get("windGust", "-"))
    wind_dir = obs.get("winddir", "-")
    desc, style = get_wind_description(speed_kmh)
    grid = Table.grid(padding=(0,1))
    grid.add_column(justify="right"); grid.add_column(justify="left")
    grid.add_row("Direction:", f" {deg_to_arrow(wind_dir)} {wind_dir}° {deg_to_compass(wind_dir)}")
    grid.add_row("Speed:", f" {speed_kmh} km/h")
    grid.add_row("Gust:", f" {gust_kmh} km/h")
    grid.add_row("Desc:", Text(desc, style=style))
    return Panel(Align.center(grid), title="💨 Wind | Gust", box=box.ROUNDED, padding=(0, 1))

def rain_panel(obs): # (Restored)
    m = obs.get("metric") or {}
    rate, total = m.get("precipRate", "-"), m.get("precipTotal", "-")
    desc, style = get_rain_description(rate)
    grid = Table.grid(padding=(0, 2))
    grid.add_row("📈 Rate:", f"{rate} mm/h")
    grid.add_row("💧 Intensity:", Text(desc, style=style))
    grid.add_row("📅 Today:", f"{total} mm")
    return Panel(Align.center(grid), title="🌧️  Rainfall", box=box.ROUNDED, padding=(0, 1))

def solar_panel(obs): # (Restored)
    uv, solar = obs.get("uv", "-"), obs.get("solarRadiation", "-")
    desc, style = get_uv_description(uv)
    grid = Table.grid(padding=(0, 2))
    grid.add_row("☀️  UV Index:", Text(str(uv), style=style))
    grid.add_row("😎 UV Level:", Text(desc, style=style))
    grid.add_row("⚡ Solar Rad.:", f"{solar} W/m²")
    return Panel(Align.center(grid), title="☀️  Solar • UV", box=box.ROUNDED, padding=(0, 1))

def humidity_panel(obs): # (Restored)
    humid = obs.get("humidity", "-")
    display = Text(f"💧 {humid}%", justify="center")
    try:
        if float(humid) < 30: display.append("\n\n🌵 Dry", style="yellow")
        elif float(humid) < 60: display.append("\n\n🌤️ Normal", style="green")
        else: display.append("\n\n💦 Humid", style="blue")
    except: pass
    return Panel(Align.center(display), title="💧 Humidity", subtitle="Relative", box=box.ROUNDED, padding=(0, 1))

def barometer_panel(obs): # (Restored)
    pressure = obs.get("metric", {}).get("pressure", "-")
    return Panel(Align.center(f"[bold bright_green]{pressure}[/] hPa"), title="🌡️  Barometer", box=box.ROUNDED)

def sun_panel(obs): # (Restored)
    lat, lon = obs.get("lat"), obs.get("lon")
    if lat is None or lon is None: return Panel("No location data", title="☀️ Sun Rise/Set")
    # Simplified calculation
    now = datetime.now()
    day_of_year = now.timetuple().tm_yday
    declination = 23.45 * math.sin(math.radians(360/365 * (day_of_year - 80)))
    hour_angle = math.degrees(math.acos(-math.tan(math.radians(lat)) * math.tan(math.radians(declination))))
    sunrise = 12 - hour_angle / 15
    sunset = 12 + hour_angle / 15
    daylight = sunset - sunrise
    grid = Table.grid()
    grid.add_row("🌅 Sunrise:", f"{int(sunrise):02d}:{int((sunrise%1)*60):02d}")
    grid.add_row("🌇 Sunset:", f"{int(sunset):02d}:{int((sunset%1)*60):02d}")
    grid.add_row("☀️  Daylight:", f"{int(daylight)}h {int((daylight%1)*60)}m")
    return Panel(Align.center(grid), title="☀️  Sun Rise/Set", box=box.ROUNDED)

def moon_phase_panel(obs): # (Restored)
    """Display current moon phase based on date with new moon and full moon info"""
    now = datetime.now()
    day_of_year = now.timetuple().tm_yday
    moon_cycle = 29.53
    phase = (day_of_year % moon_cycle) / moon_cycle
    
    is_new_moon, is_full_moon = False, False

    if phase < 0.0625: moon_emoji, phase_name, is_new_moon = "🌑", "New Moon", True
    elif phase < 0.1875: moon_emoji, phase_name = "🌒", "Waxing Crescent"
    elif phase < 0.3125: moon_emoji, phase_name = "🌓", "First Quarter"
    elif phase < 0.4375: moon_emoji, phase_name = "🌔", "Waxing Gibbous"
    elif phase < 0.5625: moon_emoji, phase_name, is_full_moon = "🌕", "Full Moon", True
    elif phase < 0.6875: moon_emoji, phase_name = "🌖", "Waning Gibbous"
    elif phase < 0.8125: moon_emoji, phase_name = "🌗", "Last Quarter"
    else: moon_emoji, phase_name = "🌘", "Waning Crescent"
    
    days_since_new = (day_of_year % moon_cycle)
    days_until_new = moon_cycle - days_since_new
    next_new_moon = now + timedelta(days=days_until_new)
    
    moon_display = Text(justify="center")
    moon_display.append(f"{moon_emoji}\n\n{phase_name}\n")
    
    if is_new_moon: moon_display.append("🌑 NEW MOON!\n", style="bold bright_yellow")
    elif is_full_moon: moon_display.append("🌕 FULL MOON!\n", style="bold bright_white")

    moon_display.append(f"Phase: {phase:.1%}\n")
    
    if days_since_new < 3:
        moon_display.append(f"🌑 {days_since_new:.0f} days since new moon\n", style="bright_yellow")
    else:
        moon_display.append(f"🌑 {days_until_new:.0f} days until next new moon\n")
    
    moon_display.append(f"Next: {next_new_moon.strftime('%b %d')} | Date: {now.strftime('%b %d')}")
    
    return Panel(
        Align.center(moon_display),
        title="🌙 Moon Phase",
        box=box.ROUNDED,
        padding=(0, 1),
    )


def create_hourly_forecast_panels(hourly_data: List[Dict[str, Any]]) -> Columns:
    panels = []
    for hour in hourly_data:
        time_str = datetime.fromtimestamp(hour["dt"]).strftime("%H:%M")
        temp = f"{hour['temp']:.1f}°C"
        weather_desc = hour["weather"][0]["description"].title()
        weather_icon = get_weather_emoji(hour["weather"][0]["icon"])
        pop = f"{hour.get('pop', 0) * 100:.0f}%"
        wind_speed_kmh = ms_to_kmh(hour.get("wind_speed", "-"))
        wind_arrow = deg_to_arrow(hour.get("wind_deg", "-"))
        clouds = f"{hour.get('clouds', '-')} %"
        visibility_km = f"{hour.get('visibility', 0) / 1000:.1f} km"
        pressure = f"{hour.get('pressure', '-')} hPa"
        humidity = f"{hour.get('humidity', '-')} %"

        grid = Table.grid(expand=True)
        grid.add_column(width=10); grid.add_column()
        grid.add_row("🌡️  Temp:", f"[green]{temp}[/]")
        grid.add_row("💧 Humid:", f"[cyan]{humidity}[/]")
        grid.add_row("☁️  Clouds:", f"[grey70]{clouds}[/]")
        grid.add_row("💨 Wind:", f"[orange3]{wind_arrow} {wind_speed_kmh} km/h[/]")
        grid.add_row("👁️  Vis:", f"[white]{visibility_km}[/]")
        grid.add_row(" barometer:", f"[bright_green]{pressure}[/]")
        grid.add_row("💧 Precip:", f"[blue]{pop}[/]")
        if 'rain' in hour and '1h' in hour['rain']:
            grid.add_row("🌧️  Rain:", f"[cyan]{hour['rain']['1h']:.2f} mm[/]")
        grid.add_row(f"[white]{weather_icon}[/]", f"[white]{weather_desc}[/]")
        panels.append(Panel(grid, title=f"[magenta]{time_str}[/]", box=box.ROUNDED, expand=True))
    return Columns(panels, equal=True, expand=True)

# --- Full Screen Forecast Layout ---

def build_full_forecast_layout(hourly_data: List[Dict[str, Any]]) -> Layout:
    """Create a full-screen layout showing only the hourly forecast (next 12 hours from current time)"""
    layout = Layout(name="root")

    # Header
    header_text = Text("🌤️ HOURLY FORECAST (NEXT 12 HOURS)", justify="center", style="bold blue")
    header_panel = Panel(header_text, box=box.HEAVY_HEAD, padding=(0, 1))

    # Show next 12 hours from current time
    forecast_hours = hourly_data[:12]  # First 12 hours from current time
    forecast_columns = create_hourly_forecast_panels(forecast_hours)

    # Main forecast panel
    forecast_panel = Panel(
        forecast_columns,
        title="",
        box=box.ROUNDED,
        expand=True,
        padding=(1, 1)
    )

    # Footer
    if display_mode.enable_auto_switch:
        time_until_switch = display_mode.auto_switch_interval - (time.time() - display_mode.last_switch_time)
        footer_text = Text(f"⌨️ Auto-switch in {int(time_until_switch)}s • Ctrl+C to quit", justify="center", style="yellow")
    else:
        footer_text = Text("⌨️ Type 'n' + Enter: return to main • Ctrl+C: quit", justify="center", style="yellow")
    footer_panel = Panel(footer_text, box=box.SIMPLE, padding=(0, 1))

    # Layout structure
    layout.split(
        Layout(name="header", size=3),
        Layout(name="forecast", ratio=1),
        Layout(name="footer", size=3)
    )

    layout["header"].update(header_panel)
    layout["forecast"].update(forecast_panel)
    layout["footer"].update(footer_panel)

    return layout

# --- Main Layout ---

def build_layout(obs: Dict[str, Any], error: str, hourly_data: List[Dict[str, Any]], console: Console) -> Layout:
    # Check if we're in full forecast mode
    if display_mode.is_full_forecast():
        return build_full_forecast_layout(hourly_data)

    # Normal mode layout
    layout = Layout(name="root")
    layout.split(Layout(name="header", size=3), Layout(name="body", ratio=1), Layout(name="forecast", size=12), Layout(name="footer", size=1))
    layout["body"].split(Layout(name="row1", ratio=1), Layout(name="row2", ratio=1), Layout(name="row3", ratio=1))
    layout["row1"].split_row(thermal_panel(obs), rain_panel(obs))
    layout["row2"].split_row(humidity_panel(obs), wind_panel(obs), solar_panel(obs))
    layout["row3"].split_row(barometer_panel(obs), moon_phase_panel(obs), sun_panel(obs))
    layout["header"].update(header_panel(obs, error))

    panel_width = 35
    num_panels = console.width // panel_width
    sliced_data = hourly_data[:num_panels]
    forecast_columns = create_hourly_forecast_panels(sliced_data)
    layout["forecast"].update(Panel(forecast_columns, title="[bold]Hourly Forecast[/bold]", box=box.HEAVY_HEAD, expand=True))

      # Show auto-switch status
    if display_mode.enable_auto_switch:
        time_until_switch = display_mode.auto_switch_interval - (time.time() - display_mode.last_switch_time)
        status_text = f"⌨️ Press Ctrl+C to quit • Auto-switch in {int(time_until_switch)}s • 🔄 Auto-refresh every "
    else:
        status_text = f"⌨️ Ctrl+C: quit • Type 'n' + Enter: 12-24hr forecast • 🔄 Auto-refresh every "

    foot = Text(status_text, justify="center")
    foot.append(str(REFRESH_SECONDS), style="bold").append("s")
    layout["footer"].update(foot)
    return layout

# --- Keyboard Input Handler ---

# Thread-safe queue for keyboard input
input_queue = queue.Queue()

def input_thread():
    """Thread to handle keyboard input"""
    while True:
        try:
            key = input().strip().lower()
            if key == 'n':
                input_queue.put('toggle')
        except:
            break

# Start input thread
threading.Thread(target=input_thread, daemon=True).start()

def check_for_forecast_key():
    """Check for 'n' key press to toggle forecast mode"""
    try:
        while not input_queue.empty():
            command = input_queue.get_nowait()
            if command == 'toggle':
                display_mode.toggle_forecast()
                return True
    except:
        pass
    return False

# --- Main Execution ---

def main() -> None:
    console = Console()
    obs, last_err, hourly_data, last_hourly_err = {}, "", [], ""

    with console.status("[bold green]Fetching data..."):
        obs, last_err = fetch_observation()
        hourly_data, last_hourly_err = fetch_hourly_forecast()

    layout = build_layout(obs, last_err or last_hourly_err, hourly_data, console)

    with Live(layout, refresh_per_second=4, screen=True, console=console) as live:
        last_update_time = time.time()
        while True:
            # Check for 'n' key press
            try:
                check_for_forecast_key()
            except:
                pass

            # Always update layout to reflect any mode changes immediately
            new_layout = build_layout(obs, last_err or last_hourly_err, hourly_data, console)
            live.update(new_layout)

            # Refresh data when mode changes or in normal mode after timeout
            current_time = time.time()
            should_refresh = False

            # Force refresh when mode changes
            if display_mode.has_mode_changed():
                should_refresh = True
                last_update_time = current_time  # Reset timer

            # Regular refresh in normal mode
            elif not display_mode.is_full_forecast() and current_time - last_update_time >= REFRESH_SECONDS:
                should_refresh = True
                last_update_time = current_time

            if should_refresh:
                obs, last_err = fetch_observation()
                hourly_data, last_hourly_err = fetch_hourly_forecast()

            time.sleep(0.25)  # Short sleep for responsive UI

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
