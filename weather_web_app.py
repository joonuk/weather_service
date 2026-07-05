from __future__ import annotations

import base64
from datetime import datetime
from statistics import mean
from zoneinfo import ZoneInfo

from flask import Flask, render_template, request

from open_meteo_hourly_today import (
    DEFAULT_LOCATION_NAME,
    DEFAULT_TIMEZONE,
    extract_hourly_rows,
    fetch_forecast,
    find_location,
)
from plot_open_meteo_temperature import (
    extract_temperature_series,
    render_temperature_chart_png,
)

app = Flask(__name__)


def pick_current_row(rows: list[dict], timezone_name: str) -> dict:
    current_hour = datetime.now(ZoneInfo(timezone_name)).strftime("%H:00")
    for row in rows:
        if row["time"][11:16] == current_hour:
            return row
    return rows[0]


def build_summary(rows: list[dict], timezone_name: str) -> dict:
    current_row = pick_current_row(rows, timezone_name)
    current_row = {
        **current_row,
        "time_label": current_row["time"][11:16],
    }
    temperatures = [row["temperature_2m"] for row in rows]
    rain_probabilities = [row["precipitation_probability"] for row in rows]

    return {
        "current": current_row,
        "min_temp": min(temperatures),
        "max_temp": max(temperatures),
        "avg_temp": mean(temperatures),
        "max_rain_probability": max(rain_probabilities),
    }


def build_chart_data_url(location_name: str, payload: dict) -> str:
    times, temperatures = extract_temperature_series(payload)
    chart_bytes = render_temperature_chart_png(location_name, times, temperatures)
    encoded_chart = base64.b64encode(chart_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded_chart}"


@app.route("/", methods=["GET"])
def index():
    query = request.args.get("location", "").strip()
    used_default = not query

    try:
        if used_default:
            location = find_location()
        else:
            location = find_location(city=query, timezone=DEFAULT_TIMEZONE)

        payload = fetch_forecast(location)
        rows = extract_hourly_rows(payload)
        summary = build_summary(rows, payload.get("timezone", location.timezone))
        chart_data_url = build_chart_data_url(location.name, payload)
    except RuntimeError as error:
        return render_template(
            "index.html",
            error=str(error),
            location_name=None,
            query=query,
            used_default=used_default,
            summary=None,
            chart_data_url=None,
            rows=[],
            page_title="오늘의 날씨 그래프",
            default_location_name=DEFAULT_LOCATION_NAME,
        )

    display_rows = [
        {
            **row,
            "time_label": row["time"][11:16],
        }
        for row in rows
    ]

    return render_template(
        "index.html",
        error=None,
        location_name=location.name,
        query=query,
        used_default=used_default,
        summary=summary,
        chart_data_url=chart_data_url,
        rows=display_rows,
        page_title="오늘의 날씨 그래프",
        default_location_name=DEFAULT_LOCATION_NAME,
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
