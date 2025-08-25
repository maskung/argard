import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
import sys
from datetime import datetime

# --- Weather Code Mapping ---
# Map WMO weather codes from Open-Meteo to emoji and description
WEATHER_CODES = {
    0: ("☀️", "Clear sky"),
    1: ("🌤️", "Mainly clear"),
    2: ("⛅", "Partly cloudy"),
    3: ("☁️", "Overcast"),
    45: ("🌫️", "Fog"),
    48: ("🌫️", "Depositing rime fog"),
    51: ("💧", "Light drizzle"),
    53: ("💧", "Moderate drizzle"),
    55: ("💧", "Dense drizzle"),
    56: ("❄️", "Light freezing drizzle"),
    57: ("❄️", "Dense freezing drizzle"),
    61: ("🌧️", "Slight rain"),
    63: ("🌧️", "Moderate rain"),
    65: ("🌧️", "Heavy rain"),
    66: ("❄️", "Light freezing rain"),
    67: ("❄️", "Heavy freezing rain"),
    71: ("🌨️", "Slight snow fall"),
    73: ("🌨️", "Moderate snow fall"),
    75: ("🌨️", "Heavy snow fall"),
    77: ("❄️", "Snow grains"),
    80: ("🌦️", "Slight rain showers"),
    81: ("🌦️", "Moderate rain showers"),
    82: ("🌦️", "Violent rain showers"),
    85: ("🌨️", "Slight snow showers"),
    86: ("🌨️", "Heavy snow showers"),
    95: ("⛈️", "Thunderstorm"),
    96: ("⛈️", "Thunderstorm with slight hail"),
    99: ("⛈️", "Thunderstorm with heavy hail"),
}

def get_location_from_ip():
    """Fetches location data (lat, lon, city) from IP address."""
    try:
        response = requests.get("http://ip-api.com/json/", timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes
        data = response.json()
        if data.get("status") == "success":
            return {
                "lat": data["lat"],
                "lon": data["lon"],
                "city": data.get("city", "Unknown City"),
            }
        else:
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error getting location: {e}", file=sys.stderr)
        return None

def get_weather_forecast(lat, lon):
    """Fetches both daily and hourly weather forecast from Open-Meteo."""
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "weather_code,temperature_2m_max,temperature_2m_min",
            "hourly": "temperature_2m,weather_code",
            "timezone": "auto",
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error getting weather forecast: {e}", file=sys.stderr)
        return None

def display_hourly_forecast(console, forecast_data, city):
    """Displays the 12-hour forecast."""
    if "hourly" not in forecast_data:
        console.print("[bold red]Could not retrieve hourly forecast.[/bold red]")
        return

    hourly_table = Table(show_header=True, header_style="bold yellow")
    hourly_table.add_column("Time", style="dim", width=8)
    hourly_table.add_column("Description", width=20)
    hourly_table.add_column("Temp (°C)", justify="right", style="bold green")

    hourly_data = forecast_data["hourly"]
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    
    # Find the index of the current hour in the forecast data
    try:
        start_index = hourly_data["time"].index(now.strftime("%Y-%m-%dT%H:%M"))
    except ValueError:
        # If current hour not found, find the next available hour
        for i, time_str in enumerate(hourly_data["time"]):
            if datetime.fromisoformat(time_str) > now:
                start_index = i
                break
        else:
            start_index = 0


    for i in range(start_index, min(start_index + 12, len(hourly_data["time"]))):
        time_str = hourly_data["time"][i]
        time_obj = datetime.fromisoformat(time_str)
        
        weather_code = hourly_data["weather_code"][i]
        temp = hourly_data["temperature_2m"][i]

        emoji, description = WEATHER_CODES.get(weather_code, ("❓", "Unknown"))
        
        hourly_table.add_row(
            time_obj.strftime("%H:%M"),
            f"{emoji} {description}",
            f"{temp:.1f}",
        )

    title = Text(f"12-Hour Forecast for {city}", justify="center", style="bold yellow")
    console.print(Panel(hourly_table, title=title, border_style="yellow"))


def main():
    """Main function to run the weather forecast display."""
    console = Console()

    with console.status("[bold green]Fetching location data..."):
        location = get_location_from_ip()

    if not location:
        console.print("[bold red]Could not determine your location.[/bold red]")
        return

    city = location["city"]
    with console.status(f"[bold green]Fetching weather forecast for {city}..."):
        forecast_data = get_weather_forecast(location["lat"], location["lon"])

    if not forecast_data:
        console.print("[bold red]Could not retrieve weather forecast.[/bold red]")
        return

    # Display Hourly Forecast
    display_hourly_forecast(console, forecast_data, city)

    # Display Daily Forecast
    if "daily" not in forecast_data:
        console.print("[bold red]Could not retrieve daily forecast.[/bold red]")
        return
        
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Date", style="dim", width=12)
    table.add_column("Description", width=20)
    table.add_column("High (°C)", justify="right", style="bold red")
    table.add_column("Low (°C)", justify="right", style="bold blue")

    daily_data = forecast_data["daily"]
    for i in range(len(daily_data["time"])):
        date = daily_data["time"][i]
        weather_code = daily_data["weather_code"][i]
        temp_max = daily_data["temperature_2m_max"][i]
        temp_min = daily_data["temperature_2m_min"][i]

        emoji, description = WEATHER_CODES.get(weather_code, ("❓", "Unknown"))
        
        table.add_row(
            date,
            f"{emoji} {description}",
            f"{temp_max:.1f}",
            f"{temp_min:.1f}",
        )

    title = Text(f"7-Day Weather Forecast for {city}", justify="center", style="bold cyan")
    console.print(Panel(table, title=title, border_style="green"))


if __name__ == "__main__":
    main()