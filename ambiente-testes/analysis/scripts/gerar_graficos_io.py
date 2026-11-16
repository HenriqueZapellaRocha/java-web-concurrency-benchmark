#!/usr/bin/env python3
"""Gera as figuras da seção I/O-bound diretamente dos CSVs processados."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from statistics import mean

from PIL import Image, ImageDraw

from gerar_graficos_cpu import (
    F_AXIS,
    F_LEGEND,
    F_PANEL,
    F_POINT,
    F_TICK,
    F_VALUE,
    GRID,
    INK,
    LIGHT,
    MUTED,
    WHITE,
    canvas,
    marker,
    pt,
    vertical_axis_label,
)


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results" / "processed"
OUTPUT = ROOT / "analysis" / "output" / "figuras"

MAIN_SUMMARY = RESULTS / "io-database-delay-final" / "summary.csv"
THREAD_RUNS = RESULTS / "io-thread-limit-confirmation" / "runs.csv"
DELAY_SUMMARY = RESULTS / "io-delay-sensitivity-confirmation" / "summary.csv"

VARIANTS = ["m1-platform", "m2-virtual", "m3-reactive"]
COLORS = {
    "m1-platform": "#B25A00",
    "m2-virtual": "#007A53",
    "m3-reactive": "#1F66B3",
}
LABELS = {
    "m1-platform": "M1 · plataforma",
    "m2-virtual": "M2 · virtual",
    "m3-reactive": "M3 · reativo",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def number(row: dict[str, str], key: str) -> float:
    raw = row.get(key, "")
    return float(raw) if raw else 0.0


def legend(draw: ImageDraw.ImageDraw, width: int, y: int) -> None:
    item_width = 470
    start = (width - item_width * len(VARIANTS)) // 2
    for index, variant in enumerate(VARIANTS):
        x = start + index * item_width
        draw.line((x, y, x + 56, y), fill=COLORS[variant], width=6)
        marker(draw, x + 28, y, COLORS[variant], index, 8)
        draw.text((x + 72, y), LABELS[variant], fill=INK, font=F_LEGEND, anchor="lm")


def frontier_point_labels(
    draw: ImageDraw.ImageDraw,
    labels_by_rate: dict[int, list[tuple[float, float, float, str]]],
    rates: list[int],
    plot_top: int,
    log_y: bool,
    decimals: int = 1,
    suffix: str = "",
    group_equal: bool = False,
) -> None:
    for rate, entries in labels_by_rate.items():
        if group_equal:
            groups: dict[float, list[tuple[float, float, float, str]]] = {}
            for entry in entries:
                groups.setdefault(round(entry[2], decimals), []).append(entry)
            labeled = []
            for group in groups.values():
                if len(group) == 1:
                    labeled.append((*group[0], 1))
                else:
                    labeled.append((group[0][0], mean(item[1] for item in group),
                                    mean(item[2] for item in group), MUTED, len(group)))
        else:
            labeled = [(*entry, 1) for entry in entries]
        ordered = sorted(labeled, key=lambda item: item[1], reverse=True)
        positions: list[float] = []
        previous = float("inf")
        for _, py, _, _, _ in ordered:
            label_y = min(py - 29, previous - 38)
            positions.append(label_y)
            previous = label_y
        if positions[-1] < plot_top - 42:
            shift = plot_top - 42 - positions[-1]
            positions = [position + shift for position in positions]

        offset_x = 88 if rate == rates[0] else (-88 if rate == rates[-1] else 48)
        for (px, py, amount, color, count), label_y in zip(ordered, positions):
            label = (
                f"{pt(amount / 1000, 2)} s" if amount >= 1000 else f"{pt(amount, decimals)} ms"
            ) if log_y else pt(amount, decimals) + suffix
            if count > 1:
                label += f" ({count} var.)"
            label_x = px + offset_x
            bounds = draw.textbbox((label_x, label_y), label, font=F_POINT, anchor="mm")
            background = (bounds[0] - 8, bounds[1] - 5, bounds[2] + 8, bounds[3] + 5)
            draw.line((px, py - 10, label_x, background[3]), fill=color, width=2)
            draw.rounded_rectangle(background, radius=7, fill=WHITE, outline=color, width=2)
            draw.text((label_x, label_y), label, fill=color, font=F_POINT, anchor="mm")


def line_panel(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    rows: list[dict[str, str]],
    x_values: list[int],
    x_key: str,
    metric: str,
    deviation: str,
    title: str,
    y_ticks: list[float],
    log_y: bool = False,
    ideal: bool = False,
    percent_line: float | None = None,
    image: Image.Image | None = None,
    y_axis_title: str | None = None,
    x_axis_title: str | None = None,
    point_labels: bool = False,
    label_decimals: int = 1,
    label_suffix: str = "",
    group_equal_labels: bool = False,
) -> None:
    left, top, right, bottom = box
    plot_left, plot_top = left + (155 if y_axis_title else 125), top + (140 if point_labels else 84)
    plot_right, plot_bottom = right - 38, bottom - 92
    draw.text(((left + right) // 2, top + 12), title, fill=INK, font=F_PANEL, anchor="ma")
    x = lambda amount: plot_left + x_values.index(amount) * (plot_right - plot_left) / (len(x_values) - 1)
    if log_y:
        low, high = math.log10(y_ticks[0]), math.log10(y_ticks[-1])
        y = lambda amount: plot_bottom - (math.log10(max(amount, y_ticks[0])) - low) / (high - low) * (plot_bottom - plot_top)
    else:
        low, high = y_ticks[0], y_ticks[-1]
        y = lambda amount: plot_bottom - (amount - low) / (high - low) * (plot_bottom - plot_top)

    for tick in y_ticks:
        py = y(tick)
        draw.line((plot_left, py, plot_right, py), fill=GRID, width=2)
        if log_y:
            label = f"{int(tick / 1000)} s" if tick >= 1000 else f"{int(tick)} ms"
        elif high <= 110:
            label = f"{int(tick)}%"
        else:
            label = f"{int(tick):,}".replace(",", ".")
        draw.text((plot_left - 18, py), label, fill=MUTED, font=F_TICK, anchor="rm")
    for item in x_values:
        px = x(item)
        draw.line((px, plot_bottom, px, plot_bottom + 9), fill=INK, width=2)
        draw.text((px, plot_bottom + 20), str(item), fill=INK, font=F_TICK, anchor="ma")
    draw.line((plot_left, plot_top, plot_left, plot_bottom), fill=INK, width=3)
    draw.line((plot_left, plot_bottom, plot_right, plot_bottom), fill=INK, width=3)
    if y_axis_title and image is not None:
        vertical_axis_label(image, y_axis_title, left + 38, (plot_top + plot_bottom) // 2)
    if x_axis_title:
        draw.text(((plot_left + plot_right) // 2, bottom - 18), x_axis_title,
                  fill=INK, font=F_AXIS, anchor="ms")

    if percent_line is not None:
        py = y(percent_line)
        draw.line((plot_left, py, plot_right, py), fill="#7B838B", width=3)
        draw.text((plot_right - 5, py - 10), "critério de 99%", fill=MUTED, font=F_TICK, anchor="rb")
    if ideal:
        points = [(x(item), y(item)) for item in x_values]
        draw.line(points, fill="#7B838B", width=3)
        midpoint = (x_values[0] + x_values[1]) / 2
        draw.text(((x(x_values[0]) + x(x_values[1])) / 2, y(midpoint) - 26),
                  "ideal", fill=MUTED, font=F_TICK, anchor="mb")

    labels_by_rate: dict[int, list[tuple[float, float, float, str]]] = {rate: [] for rate in x_values}
    for variant_index, variant in enumerate(VARIANTS):
        selected = [row for row in rows if row["variant"] == variant]
        selected.sort(key=lambda row: x_values.index(int(row[x_key].removesuffix("ms"))))
        points = []
        for row in selected:
            x_item = int(row[x_key].removesuffix("ms"))
            amount = number(row, metric)
            points.append((x(x_item), y(amount)))
        draw.line(points, fill=COLORS[variant], width=6, joint="curve")
        for row, (px, py) in zip(selected, points):
            amount = number(row, metric)
            sd = number(row, deviation)
            lower = max(y_ticks[0], amount - sd)
            upper = min(y_ticks[-1], amount + sd)
            draw.line((px, y(lower), px, y(upper)), fill=COLORS[variant], width=3)
            draw.line((px - 9, y(lower), px + 9, y(lower)), fill=COLORS[variant], width=3)
            draw.line((px - 9, y(upper), px + 9, y(upper)), fill=COLORS[variant], width=3)
            marker(draw, px, py, COLORS[variant], variant_index)
            if point_labels:
                labels_by_rate[int(row[x_key].removesuffix("ms"))].append((px, py, amount, COLORS[variant]))

    if point_labels:
        frontier_point_labels(draw, labels_by_rate, x_values, plot_top, log_y,
                              label_decimals, label_suffix, group_equal_labels)


def generate_frontier(rows: list[dict[str, str]]) -> None:
    image, draw = canvas(
        2500,
        2050,
        "Capacidade útil e latência no workload I/O-bound",
        "Médias nos pontos; barras = um desvio-padrão",
    )
    legend(draw, 2500, 170)
    rates = [1000, 1900, 2100, 2300]
    line_panel(draw, (35, 215, 1240, 1160), rows, rates, "targetRateRps",
               "successfulRpsMean", "successfulRpsStdDev", "(a) Vazão útil média",
               [0, 500, 1000, 1500, 2000, 2500], ideal=True,
               image=image, y_axis_title="Vazão útil média (sucessos/s)",
               x_axis_title="Taxa oferecida (req/s)", point_labels=True)
    line_panel(draw, (1260, 215, 2465, 1160), rows, rates, "targetRateRps",
               "latencyP99MsMean", "latencyP99MsStdDev", "(b) P99 — escala logarítmica",
               [100, 500, 1000, 5000], log_y=True,
               image=image, y_axis_title="P99 da latência",
               x_axis_title="Taxa oferecida (req/s)", point_labels=True)
    line_panel(draw, (35, 1180, 2465, 2005), rows, rates, "targetRateRps",
               "latencyP50MsMean", "latencyP50MsStdDev", "(c) P50 — escala logarítmica",
               [100, 200, 500, 1000, 2000, 5000], log_y=True,
               image=image, y_axis_title="P50 da latência",
               x_axis_title="Taxa oferecida (req/s)", point_labels=True)
    image.save(OUTPUT / "io-fronteira.png", dpi=(300, 300), optimize=True)


def paired_panel(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    rows: list[dict[str, str]],
    metric: str,
    title: str,
    ticks: list[float],
    divisor: float = 1.0,
    suffix: str = "",
    decimals: int = 0,
) -> None:
    left, top, right, bottom = box
    plot_left, plot_top = left + 120, top + 90
    plot_right, plot_bottom = right - 65, bottom - 95
    draw.text(((left + right) // 2, top + 10), title, fill=INK, font=F_PANEL, anchor="ma")
    x_positions = [plot_left + (plot_right - plot_left) * 0.28, plot_left + (plot_right - plot_left) * 0.72]
    low, high = ticks[0], ticks[-1]
    y = lambda amount: plot_bottom - (amount - low) / (high - low) * (plot_bottom - plot_top)
    for tick in ticks:
        py = y(tick)
        draw.line((plot_left, py, plot_right, py), fill=GRID, width=2)
        draw.text((plot_left - 18, py), f"{int(tick):,}".replace(",", ".") + suffix, fill=MUTED, font=F_TICK, anchor="rm")
    draw.line((plot_left, plot_top, plot_left, plot_bottom), fill=INK, width=3)
    draw.line((plot_left, plot_bottom, plot_right, plot_bottom), fill=INK, width=3)
    draw.text((x_positions[0], plot_bottom + 23), "M1 · 200 threads", fill=INK, font=F_AXIS, anchor="ma")
    draw.text((x_positions[1], plot_bottom + 23), "M1 · 250 threads", fill=INK, font=F_AXIS, anchor="ma")
    series = []
    for variant in ("m1-platform", "m1-platform-t250"):
        series.append({int(row["repetition"]): number(row, metric) / divisor for row in rows if row["variant"] == variant})
    repetitions = sorted(set(series[0]) & set(series[1]))
    shades = ["#56636F", "#6A7683", "#87919B", "#A0A8B0", "#BBC1C6"]
    for index, repetition in enumerate(repetitions):
        points = [(px, y(values[repetition])) for px, values in zip(x_positions, series)]
        draw.line(points, fill=shades[index], width=4)
        for px, py in points:
            draw.ellipse((px - 8, py - 8, px + 8, py + 8), fill=WHITE, outline=shades[index], width=4)
    means = [mean(values[rep] for rep in repetitions) for values in series]
    points = [(px, y(amount)) for px, amount in zip(x_positions, means)]
    draw.line(points, fill="#9D1C20", width=10)
    for index, ((px, py), amount) in enumerate(zip(points, means)):
        draw.ellipse((px - 13, py - 13, px + 13, py + 13), fill=WHITE, outline="#9D1C20", width=7)
        draw.text((px + (-18 if index == 0 else 18), py - 18), pt(amount, decimals), fill="#8A171B", font=F_VALUE, anchor="rb" if index == 0 else "lb")


def generate_thread_limit(rows: list[dict[str, str]]) -> None:
    image, draw = canvas(2500, 1170, "Efeito pareado do limite de threads do M1 em 2.100 req/s",
                         "Linhas finas representam as cinco repetições; linha espessa representa a média")
    paired_panel(draw, (35, 170, 1240, 1120), rows, "successfulRps", "(a) Vazão útil",
                 [0, 500, 1000, 1500, 2000, 2500])
    paired_panel(draw, (1260, 170, 2465, 1120), rows, "latencyP99Ms", "(b) P99 da latência",
                 [0, 2, 4, 6, 8], divisor=1000.0, suffix=" s", decimals=2)
    image.save(OUTPUT / "io-limite-threads.png", dpi=(300, 300), optimize=True)


def generate_delay(rows: list[dict[str, str]]) -> None:
    adjusted = []
    for row in rows:
        copy = dict(row)
        copy["successPercentMean"] = str(number(row, "successRatioMean") * 100)
        copy["successPercentStdDev"] = str(number(row, "successRatioStdDev") * 100)
        adjusted.append(copy)
    image, draw = canvas(2500, 2050, "Sensibilidade à espera controlada em 1.000 req/s",
                         "Médias nos pontos; barras representam um desvio-padrão")
    legend(draw, 2500, 170)
    delays = [50, 100, 200]
    line_panel(draw, (35, 215, 1240, 1160), adjusted, delays, "databaseDelay",
               "successPercentMean", "successPercentStdDev", "(a) Requisições concluídas com sucesso",
               [90, 92, 94, 96, 98, 100], percent_line=99,
               image=image, y_axis_title="Razão de sucesso (%)",
               x_axis_title="Atraso configurado no PostgreSQL (ms)", point_labels=True,
               label_decimals=2, label_suffix="%", group_equal_labels=True)
    line_panel(draw, (1260, 215, 2465, 1160), adjusted, delays, "databaseDelay",
               "latencyP99MsMean", "latencyP99MsStdDev", "(b) P99 — escala logarítmica",
               [100, 500, 1000, 2000], log_y=True,
               image=image, y_axis_title="P99 da latência",
               x_axis_title="Atraso configurado no PostgreSQL (ms)", point_labels=True)
    line_panel(draw, (35, 1180, 2465, 2005), adjusted, delays, "databaseDelay",
               "latencyP50MsMean", "latencyP50MsStdDev", "(c) P50 — escala logarítmica",
               [40, 100, 200, 500, 1000], log_y=True,
               image=image, y_axis_title="P50 da latência",
               x_axis_title="Atraso configurado no PostgreSQL (ms)", point_labels=True,
               label_decimals=0, group_equal_labels=True)
    image.save(OUTPUT / "io-sensibilidade-atraso.png", dpi=(300, 300), optimize=True)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    generate_frontier(read_csv(MAIN_SUMMARY))
    generate_thread_limit(read_csv(THREAD_RUNS))
    generate_delay(read_csv(DELAY_SUMMARY))
    for name in ("io-fronteira.png", "io-limite-threads.png", "io-sensibilidade-atraso.png"):
        print(OUTPUT / name)


if __name__ == "__main__":
    main()
