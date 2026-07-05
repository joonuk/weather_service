from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path

from open_meteo_hourly_today import (
    DEFAULT_TIMEZONE,
    extract_hourly_rows,
    fetch_forecast,
    resolve_location,
)

try:
    import matplotlib

    matplotlib.use("Agg")

    import matplotlib.pyplot as plt
    from matplotlib import font_manager
except ModuleNotFoundError as error:
    raise SystemExit(
        "matplotlib이 설치되어 있지 않습니다. "
        "예: python3 -m pip install matplotlib"
    ) from error


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Open-Meteo의 오늘 기온 데이터를 Matplotlib 그래프로 저장합니다. "
            "아무 인자 없이 실행하면 서울 데이터를 사용합니다."
        )
    )
    parser.add_argument("--city", help="조회할 도시 이름 예: Seoul, Busan")
    parser.add_argument("--latitude", type=float, help="위도")
    parser.add_argument("--longitude", type=float, help="경도")
    parser.add_argument(
        "--timezone",
        default=DEFAULT_TIMEZONE,
        help=f'시간대. 기본값은 "{DEFAULT_TIMEZONE}"입니다.',
    )
    parser.add_argument(
        "--output",
        default="today_temperature.png",
        help="저장할 그래프 파일 경로",
    )
    return parser.parse_args()


def configure_fonts() -> None:
    available_fonts = {font.name for font in font_manager.fontManager.ttflist}
    for font_name in [
        "DejaVu Sans",
        "AppleGothic",
        "Malgun Gothic",
        "NanumGothic",
        "Noto Sans CJK KR",
    ]:
        if font_name in available_fonts:
            plt.rcParams["font.family"] = font_name
            break

    plt.rcParams["axes.unicode_minus"] = False


def extract_temperature_series(payload: dict) -> tuple[list[str], list[float]]:
    rows = extract_hourly_rows(payload)
    return [row["time"] for row in rows], [row["temperature_2m"] for row in rows]


def build_temperature_figure(location_name: str, times: list[str], temperatures: list[float]):
    configure_fonts()

    hour_labels = [timestamp[11:16] for timestamp in times]
    min_temp = min(temperatures)
    max_temp = max(temperatures)
    min_index = temperatures.index(min_temp)
    max_index = temperatures.index(max_temp)

    fig, ax = plt.subplots(figsize=(12, 6), constrained_layout=True)
    fig.patch.set_facecolor("#fffaf2")
    ax.set_facecolor("#fffdf8")

    ax.plot(
        hour_labels,
        temperatures,
        color="#e76f51",
        linewidth=2.5,
        marker="o",
        markersize=4.5,
        markerfacecolor="#f4a261",
        markeredgewidth=0,
    )
    ax.fill_between(hour_labels, temperatures, color="#f4a261", alpha=0.18)

    ax.scatter(hour_labels[min_index], min_temp, color="#457b9d", s=70, zorder=3)
    ax.scatter(hour_labels[max_index], max_temp, color="#d62828", s=70, zorder=3)

    ax.annotate(
        f"Low {min_temp:.1f}°C",
        (hour_labels[min_index], min_temp),
        textcoords="offset points",
        xytext=(0, -18),
        ha="center",
        color="#457b9d",
        fontsize=10,
    )
    ax.annotate(
        f"High {max_temp:.1f}°C",
        (hour_labels[max_index], max_temp),
        textcoords="offset points",
        xytext=(0, 12),
        ha="center",
        color="#d62828",
        fontsize=10,
    )

    # Use ASCII-only chart labels so the PNG renders reliably in Vercel's Linux runtime.
    ax.set_title("Today's Hourly Temperature", fontsize=16, fontweight="bold", pad=16)
    ax.set_xlabel("Hour", fontsize=11)
    ax.set_ylabel("Temperature (°C)", fontsize=11)
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    tick_step = 2 if len(hour_labels) > 12 else 1
    ax.set_xticks(range(0, len(hour_labels), tick_step))
    ax.set_xticklabels(hour_labels[::tick_step], rotation=45, ha="right")

    return fig


def render_temperature_chart_png(
    location_name: str,
    times: list[str],
    temperatures: list[float],
) -> bytes:
    fig = build_temperature_figure(location_name, times, temperatures)
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=160)
    plt.close(fig)
    return buffer.getvalue()


def plot_temperature(
    location_name: str,
    times: list[str],
    temperatures: list[float],
    output_path: Path,
) -> None:
    fig = build_temperature_figure(location_name, times, temperatures)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def main() -> int:
    args = parse_args()

    try:
        location = resolve_location(args)
        payload = fetch_forecast(location)
        times, temperatures = extract_temperature_series(payload)
        output_path = Path(args.output).expanduser().resolve()
        plot_temperature(location.name, times, temperatures, output_path)
    except RuntimeError as error:
        print(f"오류: {error}")
        return 1

    print(f"그래프를 저장했습니다: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
