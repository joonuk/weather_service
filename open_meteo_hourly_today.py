from __future__ import annotations

import argparse
import json
import ssl
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


FORECAST_API_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_API_URL = "https://geocoding-api.open-meteo.com/v1/search"
DEFAULT_LOCATION_NAME = "서울특별시, 대한민국"
DEFAULT_LATITUDE = 37.5665
DEFAULT_LONGITUDE = 126.9780
DEFAULT_TIMEZONE = "Asia/Seoul"

HOURLY_FIELDS = [
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "precipitation_probability",
    "precipitation",
    "weather_code",
    "wind_speed_10m",
]

WEATHER_CODE_LABELS = {
    0: "맑음",
    1: "대체로 맑음",
    2: "부분적으로 흐림",
    3: "흐림",
    45: "안개",
    48: "착빙 안개",
    51: "약한 이슬비",
    53: "보통 이슬비",
    55: "강한 이슬비",
    56: "약한 어는 이슬비",
    57: "강한 어는 이슬비",
    61: "약한 비",
    63: "보통 비",
    65: "강한 비",
    66: "약한 어는 비",
    67: "강한 어는 비",
    71: "약한 눈",
    73: "보통 눈",
    75: "강한 눈",
    77: "싸락눈",
    80: "약한 소나기",
    81: "보통 소나기",
    82: "강한 소나기",
    85: "약한 눈 소나기",
    86: "강한 눈 소나기",
    95: "뇌우",
    96: "약한 우박 동반 뇌우",
    99: "강한 우박 동반 뇌우",
}


@dataclass
class Location:
    name: str
    latitude: float
    longitude: float
    timezone: str


def build_ssl_context() -> ssl.SSLContext:
    verify_paths = ssl.get_default_verify_paths()
    candidates = [
        verify_paths.cafile,
        verify_paths.openssl_cafile,
        "/private/etc/ssl/cert.pem",
        "/etc/ssl/cert.pem",
        "/opt/homebrew/etc/openssl@3/cert.pem",
        "/usr/local/etc/openssl@3/cert.pem",
    ]

    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return ssl.create_default_context(cafile=candidate)

    return ssl.create_default_context()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Open-Meteo API로 오늘의 시간별 날씨를 조회합니다. "
            "아무 인자 없이 실행하면 기본값으로 서울 날씨를 조회합니다."
        )
    )
    parser.add_argument("--city", help="조회할 도시 이름 예: Seoul, Busan")
    parser.add_argument("--latitude", type=float, help="위도")
    parser.add_argument("--longitude", type=float, help="경도")
    parser.add_argument(
        "--timezone",
        default=DEFAULT_TIMEZONE,
        help=(
            f'시간대. 기본값은 "{DEFAULT_TIMEZONE}"입니다. '
            '도시명을 쓰면 해당 도시의 시간대를 자동으로 사용합니다.'
        ),
    )
    return parser.parse_args()


def fetch_json(url: str) -> dict[str, Any]:
    try:
        with urlopen(url, timeout=10, context=build_ssl_context()) as response:
            return json.load(response)
    except HTTPError as error:
        raise RuntimeError(
            f"HTTP 오류가 발생했습니다: {error.code} {error.reason}"
        ) from error
    except URLError as error:
        raise RuntimeError(f"네트워크 오류가 발생했습니다: {error.reason}") from error


def find_location(
    city: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    timezone: str = DEFAULT_TIMEZONE,
) -> Location:
    if city:
        params = {
            "name": city,
            "count": 1,
            "language": "ko",
            "format": "json",
        }
        payload = fetch_json(f"{GEOCODING_API_URL}?{urlencode(params)}")
        results = payload.get("results") or []
        if not results:
            raise RuntimeError(f'"{city}"에 해당하는 위치를 찾지 못했습니다.')

        item = results[0]
        display_name = ", ".join(
            part
            for part in [item.get("name"), item.get("admin1"), item.get("country")]
            if part
        )
        return Location(
            name=display_name,
            latitude=float(item["latitude"]),
            longitude=float(item["longitude"]),
            timezone=str(item.get("timezone", timezone)),
        )

    if latitude is None and longitude is None:
        return Location(
            name=DEFAULT_LOCATION_NAME,
            latitude=DEFAULT_LATITUDE,
            longitude=DEFAULT_LONGITUDE,
            timezone=DEFAULT_TIMEZONE,
        )

    if latitude is None or longitude is None:
        raise RuntimeError("--latitude와 --longitude는 함께 지정해야 합니다.")

    return Location(
        name=f"{latitude}, {longitude}",
        latitude=latitude,
        longitude=longitude,
        timezone=timezone,
    )


def resolve_location(args: argparse.Namespace) -> Location:
    return find_location(
        city=args.city,
        latitude=args.latitude,
        longitude=args.longitude,
        timezone=args.timezone,
    )


def build_forecast_url(location: Location) -> str:
    params = {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "hourly": ",".join(HOURLY_FIELDS),
        "timezone": location.timezone,
        "forecast_days": 1,
    }
    return f"{FORECAST_API_URL}?{urlencode(params)}"


def fetch_forecast(location: Location) -> dict[str, Any]:
    return fetch_json(build_forecast_url(location))


def weather_label(code: Any) -> str:
    try:
        numeric_code = int(code)
    except (TypeError, ValueError):
        return "알 수 없음"
    return WEATHER_CODE_LABELS.get(numeric_code, f"알 수 없음({numeric_code})")


def extract_hourly_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        raise RuntimeError("응답에 hourly 데이터가 없습니다.")

    times = hourly.get("time")
    if not isinstance(times, list) or not times:
        raise RuntimeError("응답에 시간 정보가 없습니다.")

    rows: list[dict[str, Any]] = []
    for index, timestamp in enumerate(times):
        weather_code = hourly["weather_code"][index]
        rows.append(
            {
                "time": timestamp,
                "temperature_2m": float(hourly["temperature_2m"][index]),
                "apparent_temperature": float(hourly["apparent_temperature"][index]),
                "relative_humidity_2m": float(hourly["relative_humidity_2m"][index]),
                "precipitation_probability": float(
                    hourly["precipitation_probability"][index]
                ),
                "precipitation": float(hourly["precipitation"][index]),
                "weather_code": int(weather_code),
                "weather_label": weather_label(weather_code),
                "wind_speed_10m": float(hourly["wind_speed_10m"][index]),
            }
        )

    return rows


def print_hourly_forecast(location: Location, payload: dict[str, Any]) -> None:
    rows = extract_hourly_rows(payload)

    print(f"지역: {location.name}")
    print(f"좌표: {location.latitude}, {location.longitude}")
    print(f"시간대: {payload.get('timezone', location.timezone)}")
    print("-" * 90)

    for row in rows:
        print(
            f"{row['time']} | "
            f"{row['temperature_2m']:>5.1f}°C | "
            f"체감 {row['apparent_temperature']:>5.1f}°C | "
            f"습도 {row['relative_humidity_2m']:>3.0f}% | "
            f"강수확률 {row['precipitation_probability']:>3.0f}% | "
            f"강수량 {row['precipitation']:>4.1f} mm | "
            f"풍속 {row['wind_speed_10m']:>4.1f} km/h | "
            f"{row['weather_label']}"
        )


def main() -> int:
    args = parse_args()

    try:
        if args.city is None and args.latitude is None and args.longitude is None:
            print(f"입력 위치가 없어 기본값({DEFAULT_LOCATION_NAME})을 사용합니다.")
        location = resolve_location(args)
        payload = fetch_forecast(location)
        print_hourly_forecast(location, payload)
    except RuntimeError as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
