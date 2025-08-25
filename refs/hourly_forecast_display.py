import json
from textwrap import wrap
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from datetime import datetime
from typing import Any, Dict, List, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align
from rich import box
from rich.columns import Columns

# API Configuration - Using the one you provided
OPENWEATHER_API_KEY = "fe95920166f28786c34849635cc40d2e"
LATITUDE = 12.701
LONGITUDE = 102.231
API_URL = (
    f"https://api.openweathermap.org/data/3.0/onecall?"
    f"lat={LATITUDE}&lon={LONGITUDE}&exclude=minutely,daily,alerts&units=metric&appid="
    f"{OPENWEATHER_API_KEY}"
)

def fetch_weather_data() -> Tuple[Dict[str, Any], str]:
    """Fetches weather data from the OpenWeatherMap API."""
    headers = {
        "User-Agent": "rich-weather/1.0",
        "Accept": "application/json",
    }
    req = Request(API_URL, headers=headers)
    try:
        with urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return {}, f"HTTP Error {resp.status}"
            raw = resp.read()
            data = json.loads(raw.decode("utf-8"))
            return data, ""
    except HTTPError as e:
        return {}, f"HTTPError {e.code}: {e.reason}"
    except URLError as e:
        return {}, f"URLError: {getattr(e, 'reason', str(e))}"
    except Exception as e:
        return {}, f"An unexpected error occurred: {e}"

def get_weather_emoji(icon_code: str) -> str:
    """Maps OpenWeatherMap icon codes to emojis."""
    if "01" in icon_code:  # Clear sky
        return "☀️" if "d" in icon_code else "🌙"
    elif "02" in icon_code:  # Few clouds
        return "🌤️" if "d" in icon_code else "☁️"
    elif "03" in icon_code or "04" in icon_code:  # Scattered/Broken clouds
        return "☁️"
    elif "09" in icon_code or "10" in icon_code:  # Rain
        return "🌧️"
    elif "11" in icon_code:  # Thunderstorm
        return "⛈️"
    elif "13" in icon_code:  # Snow
        return "❄️"
    elif "50" in icon_code:  # Mist
        return "🌫️"
    return "❓"


def create_hourly_forecast_panels(hourly_data: List[Dict[str, Any]]) -> Columns:
    """Creates a Rich Columns layout with Panels for the hourly forecast."""

    panels = []
    for hour in hourly_data:
        time_str = datetime.fromtimestamp(hour["dt"]).strftime("%H:%M")
        temp = f"{hour['temp']:.1f}°C"
        
        weather_desc = hour["weather"][0]["description"].title()
        weather_icon = get_weather_emoji(hour["weather"][0]["icon"])
        
        pop = f"{hour.get('pop', 0) * 100:.0f}%"

        # Use a two-column grid for perfect alignment
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", width=10)  # Column for labels
        grid.add_column(justify="left")     # Column for values
        
        grid.add_row("🌡️ Temp:", f"[bold green]{temp}[/]")
        grid.add_row("💧 Precip:", f"[bold blue]{pop}[/]")

        # Conditionally add rain data if it exists
        if 'rain' in hour and '1h' in hour['rain']:
            rain_1h = hour['rain']['1h']
            grid.add_row("🌧️ Rain:", f"[bold cyan]{rain_1h:.2f} mm[/]")

        grid.add_row(f"[white]{weather_icon}[/]", f"[white]{weather_desc}[/]")

        panels.append(
            Panel(
                grid,
                title=f"[bold magenta]{time_str}[/]",
                box=box.ROUNDED,
                expand=True
            )
        )

    return Columns(panels, equal=True, expand=True)



def main():
    """Main function to fetch data and display it."""
    console = Console()
    
    with console.status("[bold green]Fetching weather data..."):
        weather_data, error = fetch_weather_data()

    if error:
        error_panel = Panel(
            Text(f"Failed to retrieve data: {error}", justify="center", style="bold red"),
            title="Error",
            border_style="red"
        )
        console.print(error_panel)
        return

    hourly_data = weather_data.get("hourly")
    
    if not hourly_data:
        console.print(Panel(
            Text("Hourly forecast data is not available.", justify="center", style="yellow"),
            title="Warning"
        ))
        return

    # Display Location Information
    location_info = (
        f"Location: [bold cyan]Makham[/] "
        f"([green]Lat:[/] {weather_data.get('lat', '-')}, [green]Lon:[/] {weather_data.get('lon', '-')})"
    )

    console.print(Panel(Text.from_markup(location_info, justify="center")))

    # Calculate how many panels can fit on screen
    # Assuming a fixed width for each panel to estimate
    panel_width = 35  # Approximate width of a single panel
    num_panels = console.width // panel_width
    
    # Slice the data to the calculated number of panels
    sliced_data = hourly_data[:num_panels]

    # Display Hourly Forecast Panels
    console.print(create_hourly_forecast_panels(sliced_data))


if __name__ == "__main__":
    main()
