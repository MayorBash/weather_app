from flask import Flask, render_template, request, send_file
import requests
import matplotlib.pyplot as plt
import io
from collections import defaultdict, deque
import os

app = Flask(__name__)

# Last 5 searched cities (in-memory)
recent_cities = deque(maxlen=5)

# Weather icons (unchanged)
WEATHER_ICONS = {
    0: "☀️ Clear sky",
    1: "🌤️ Mainly clear",
    2: "⛅ Partly cloudy",
    3: "☁️ Overcast",
    45: "🌫️ Fog",
    48: "🌫️ Depositing rime fog",
    51: "🌦️ Light drizzle",
    53: "🌦️ Moderate drizzle",
    55: "🌧️ Dense drizzle",
    61: "🌦️ Slight rain",
    63: "🌧️ Moderate rain",
    65: "🌧️ Heavy rain",
    71: "🌨️ Slight snow",
    73: "🌨️ Moderate snow",
    75: "❄️ Heavy snow",
    77: "🌨️ Snow grains",
    80: "🌦️ Rain showers",
    81: "🌧️ Rain showers",
    82: "⛈️ Violent rain showers",
    95: "⛈️ Thunderstorm",
    96: "⛈️ Thunderstorm with hail",
    99: "⛈️ Severe thunderstorm with hail",
}

@app.route("/", methods=["GET", "POST"])
def home():
    city = None
    temp = None
    condition = None
    windspeed = None
    forecast = []
    error = None

    if request.method == "POST":
        city = request.form["city"].strip()
        if city:
            # Add to recent searches
            if city not in recent_cities:
                recent_cities.appendleft(city)

            # Geocoding
            try:
                geo_url = f"https://nominatim.openstreetmap.org/search?q={city}&format=json&limit=1"
                headers = {"User-Agent": "WeatherApp/1.0 (shiruba487@gmail.com)"}
                geo_resp = requests.get(geo_url, headers=headers, timeout=10)
                geo_resp.raise_for_status()
                geo_data = geo_resp.json()
                if not geo_data:
                    error = f"City '{city}' not found."
                    return render_template("index.html", error=error, recent_cities=recent_cities)
                lat, lon = geo_data[0]["lat"], geo_data[0]["lon"]
            except Exception as e:
                error = f"Geocoding error: {str(e)}"
                return render_template("index.html", error=error, recent_cities=recent_cities)

            # Weather API
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&daily=temperature_2m_max,temperature_2m_min,weathercode,sunrise,sunset&hourly=relativehumidity_2m&timezone=auto"
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()

                temp = data["current_weather"]["temperature"]
                windspeed = data["current_weather"]["windspeed"]
                code = data["current_weather"]["weathercode"]
                condition = WEATHER_ICONS.get(code, "Unknown")

                # Build daily humidity
                hourly_times = data["hourly"]["time"]
                hourly_humidity = data["hourly"]["relativehumidity_2m"]
                humidity_by_day = defaultdict(list)
                for t, h in zip(hourly_times, hourly_humidity):
                    day = t.split("T")[0]
                    humidity_by_day[day].append(h)
                humidity_daily = {day: max(vals) for day, vals in humidity_by_day.items()}

                # Forecast
                dates = data["daily"]["time"]
                max_temps = data["daily"]["temperature_2m_max"]
                min_temps = data["daily"]["temperature_2m_min"]
                codes = data["daily"]["weathercode"]
                sunrise = data["daily"]["sunrise"]
                sunset = data["daily"]["sunset"]

                forecast = []
                for d, mn, mx, c, sr, ss in zip(dates, min_temps, max_temps, codes, sunrise, sunset):
                    forecast.append({
                        "date": d,
                        "min": mn,
                        "max": mx,
                        "icon": WEATHER_ICONS.get(c, "❓ Unknown"),
                        "sunrise": sr.split("T")[1],
                        "sunset": ss.split("T")[1],
                        "humidity": humidity_daily.get(d, "N/A")
                    })

            except Exception as e:
                error = f"Weather API error: {str(e)}"

    return render_template(
        "index.html",
        city=city, temp=temp, condition=condition,
        windspeed=windspeed, forecast=forecast,
        error=error, recent_cities=recent_cities
    )


@app.route("/forecast_chart")
def forecast_chart():
    city = request.args.get("city", "London")
    try:
        geo_url = f"https://nominatim.openstreetmap.org/search?q={city}&format=json&limit=1"
        headers = {"User-Agent": "WeatherApp/1.0 (shiruba487@gmail.com)"}
        geo_resp = requests.get(geo_url, headers=headers, timeout=10)
        geo_resp.raise_for_status()
        geo_data = geo_resp.json()
        if not geo_data:
            return "City not found", 400
        lat, lon = geo_data[0]["lat"], geo_data[0]["lon"]
    except Exception as e:
        return f"Geocoding error: {str(e)}", 500

    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,weathercode&timezone=auto"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        dates = data["daily"]["time"]
        max_temps = data["daily"]["temperature_2m_max"]
        min_temps = data["daily"]["temperature_2m_min"]
        codes = data["daily"]["weathercode"]

        plt.figure(figsize=(9, 5))
        plt.plot(dates, max_temps, marker="o", label="Max Temp (°C)", color="red")
        plt.plot(dates, min_temps, marker="o", label="Min Temp (°C)", color="blue")
        plt.fill_between(dates, min_temps, max_temps, color="lightgray", alpha=0.3)

        for i, (x, y, code) in enumerate(zip(dates, max_temps, codes)):
            icon = WEATHER_ICONS.get(code, "❓")
            plt.text(i, y + 1, icon.split()[0], ha="center", fontsize=12)

        plt.xlabel("Date")
        plt.ylabel("Temperature (°C)")
        plt.title(f"7-Day Forecast for {city.title()}")
        plt.legend()
        plt.xticks(rotation=30)

        img = io.BytesIO()
        plt.savefig(img, format="png")
        img.seek(0)
        plt.close()
        return send_file(img, mimetype="image/png")

    except Exception as e:
        return f"Weather API error: {str(e)}", 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
