# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A small Flask app that shows today's hourly weather for a city, backed by the free Open-Meteo API (no API key required). Deployed as a Vercel serverless function (see `vercel.json`, which targets `main.py`).

## Commands

```bash
pip install -r requirements.txt     # Flask + matplotlib

python main.py                      # run the web app at http://127.0.0.1:8000
python weather_web_app.py           # same thing, run directly

python open_meteo_hourly_today.py                # CLI: print today's hourly forecast for Seoul
python open_meteo_hourly_today.py --city Busan    # ...for another city
python plot_open_meteo_temperature.py --city Busan --output out.png   # CLI: save a temperature chart PNG
```

There is no test suite, linter, or formatter configured in this repo (no `pytest`/`ruff`/`flake8` config, no CI). To sanity-check a change, use `python -m py_compile <file>.py` and manually exercise the relevant CLI/route — don't assume a `pytest` invocation will find anything to run.

## Architecture

Three-layer pipeline, each layer importable and runnable standalone:

1. **`open_meteo_hourly_today.py`** — the only layer that talks to the network. `fetch_json()` is the single HTTP choke point (via `urlopen`) used by both the geocoding call (`find_location`, city name → lat/lon/timezone) and the forecast call (`fetch_forecast`). Both wrap failures as a plain `RuntimeError` with a Korean message — that message is what reaches the end user through the Flask layer, so changes to error handling belong here, not in `weather_web_app.py`. `extract_hourly_rows()` turns the raw Open-Meteo JSON into a flat list of per-hour dicts (temperature, precipitation, weather code → Korean label via `WEATHER_CODE_LABELS`, etc.) — this is the shared row format every other layer consumes. Also doubles as a CLI (`main()`/`print_hourly_forecast`).
2. **`plot_open_meteo_temperature.py`** — renders a Matplotlib PNG from the hourly rows (`extract_temperature_series` + `render_temperature_chart_png`/`plot_temperature`). `render_temperature_chart_png` returns raw PNG bytes (used by the web app to embed a `data:` URL); `plot_temperature` writes to a file (used by the CLI). Imports `matplotlib` lazily behind a try/except with a friendly install hint, since it's a heavier optional dependency.
3. **`weather_web_app.py`** — the Flask app. The `index()` route calls into layer 1 for data and layer 2 for the chart, computes a summary (current/min/max/avg) via `build_summary`/`pick_current_row`, base64-encodes the chart into `chart_data_url`, and renders `templates/index.html`. A location query that fails (city not found, network error) re-renders the same template with `error` set instead of a separate error page — look for the `error=` render branch rather than assuming a redirect or status code.

`main.py` just imports `app` from `weather_web_app` and runs it — this is the Vercel entrypoint.

Default location (used whenever no city/lat-lon is given) is Seoul, defined once in `open_meteo_hourly_today.py` (`DEFAULT_LOCATION_NAME`, `DEFAULT_LATITUDE/LONGITUDE`, `DEFAULT_TIMEZONE`) and imported everywhere else — don't hardcode Seoul's coordinates again elsewhere.
