#!/usr/bin/env python3
"""Gera a figura da seção de workload misto a partir do CSV consolidado."""

from __future__ import annotations

import csv
from pathlib import Path

from PIL import Image, ImageDraw

from gerar_graficos_cpu import F_AXIS, F_LEGEND, F_PANEL, F_TICK, GRID, INK, MUTED, canvas, marker, vertical_axis_label
from gerar_graficos_io import frontier_point_labels


ROOT = Path(__file__).resolve().parents[2]
SUMMARY = ROOT / "results" / "processed" / "mixed-final" / "summary.csv"
OUTPUT = ROOT / "analysis" / "output" / "figuras" / "mixed-fronteira.png"

VARIANTS = ["m1-platform", "m2-virtual", "m3-event-loop", "m3-bounded-elastic"]
COLORS = {
    "m1-platform": "#B25A00",
    "m2-virtual": "#007A53",
    "m3-event-loop": "#1F66B3",
    "m3-bounded-elastic": "#7A3E9D",
}
LABELS = {
    "m1-platform": "M1 · plataforma",
    "m2-virtual": "M2 · virtual",
    "m3-event-loop": "M3 · event loop",
    "m3-bounded-elastic": "M3 · bounded elastic",
}


def read_rows() -> list[dict[str, str]]:
    with SUMMARY.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def number(row: dict[str, str], key: str) -> float:
    raw = row.get(key, "")
    return float(raw) if raw else 0.0


def legend(draw: ImageDraw.ImageDraw, width: int, y: int) -> None:
    item_width = 430
    start = (width - item_width * len(VARIANTS)) // 2
    for index, variant in enumerate(VARIANTS):
        x = start + index * item_width
        draw.line((x, y, x + 52, y), fill=COLORS[variant], width=6)
        marker(draw, x + 26, y, COLORS[variant], index, 8)
        draw.text((x + 68, y), LABELS[variant], fill=INK, font=F_LEGEND, anchor="lm")


def panel(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    rows: list[dict[str, str]],
    metric: str,
    deviation: str,
    title: str,
    ticks: list[float],
    y_axis_title: str,
    ideal: bool = False,
    label_decimals: int = 1,
    label_suffix: str = "",
    group_equal_labels: bool = False,
) -> None:
    left, top, right, bottom = box
    plot_left, plot_top = left + 155, top + 140
    plot_right, plot_bottom = right - 38, bottom - 92
    rates = [1000, 1500, 1900]
    x = lambda rate: plot_left + rates.index(rate) * (plot_right - plot_left) / (len(rates) - 1)
    low, high = ticks[0], ticks[-1]
    y = lambda amount: plot_bottom - (amount - low) / (high - low) * (plot_bottom - plot_top)
    draw.text(((left + right) // 2, top + 12), title, fill=INK, font=F_PANEL, anchor="ma")

    for tick in ticks:
        py = y(tick)
        draw.line((plot_left, py, plot_right, py), fill=GRID, width=2)
        label = f"{int(tick):,}".replace(",", ".") + (" ms" if high <= 1000 else "")
        draw.text((plot_left - 18, py), label, fill=MUTED, font=F_TICK, anchor="rm")
    for rate in rates:
        px = x(rate)
        draw.line((px, plot_bottom, px, plot_bottom + 9), fill=INK, width=2)
        draw.text((px, plot_bottom + 20), f"{rate:,}".replace(",", "."), fill=INK, font=F_TICK, anchor="ma")
    draw.line((plot_left, plot_top, plot_left, plot_bottom), fill=INK, width=3)
    draw.line((plot_left, plot_bottom, plot_right, plot_bottom), fill=INK, width=3)
    vertical_axis_label(image, y_axis_title, left + 38, (plot_top + plot_bottom) // 2)
    draw.text(((plot_left + plot_right) // 2, bottom - 18), "Taxa oferecida (req/s)",
              fill=INK, font=F_AXIS, anchor="ms")

    if ideal:
        points = [(x(rate), y(rate)) for rate in rates]
        draw.line(points, fill="#7B838B", width=3)
        draw.text((x(1900) - 8, y(1900) - 16), "ideal", fill=MUTED, font=F_TICK, anchor="rb")

    labels_by_rate: dict[int, list[tuple[float, float, float, str]]] = {rate: [] for rate in rates}
    for variant_index, variant in enumerate(VARIANTS):
        selected = sorted((row for row in rows if row["variant"] == variant), key=lambda row: int(row["targetRateRps"]))
        points = [(x(int(row["targetRateRps"])), y(number(row, metric))) for row in selected]
        draw.line(points, fill=COLORS[variant], width=6, joint="curve")
        for row, (px, py) in zip(selected, points):
            amount, sd = number(row, metric), number(row, deviation)
            lower, upper = max(low, amount - sd), min(high, amount + sd)
            draw.line((px, y(lower), px, y(upper)), fill=COLORS[variant], width=3)
            draw.line((px - 9, y(lower), px + 9, y(lower)), fill=COLORS[variant], width=3)
            draw.line((px - 9, y(upper), px + 9, y(upper)), fill=COLORS[variant], width=3)
            marker(draw, px, py, COLORS[variant], variant_index)
            labels_by_rate[int(row["targetRateRps"])].append((px, py, amount, COLORS[variant]))

    frontier_point_labels(draw, labels_by_rate, rates, plot_top, False,
                          label_decimals, label_suffix, group_equal_labels)


def main() -> None:
    rows = read_rows()
    image, draw = canvas(
        2500,
        2050,
        "Capacidade útil e latência no workload misto",
        "Médias nos pontos; barras representam um desvio-padrão",
    )
    legend(draw, 2500, 170)
    panel(image, draw, (35, 215, 1240, 1160), rows, "successfulRpsMean", "successfulRpsStdDev",
          "(a) Vazão útil média", [0, 500, 1000, 1500, 2000],
          "Vazão útil média (sucessos/s)", ideal=True, label_decimals=0,
          group_equal_labels=True)
    panel(image, draw, (1260, 215, 2465, 1160), rows, "latencyP99MsMean", "latencyP99MsStdDev",
          "(b) P99 da latência", [0, 200, 400, 600, 800], "P99 da latência (ms)",
          label_suffix=" ms")
    panel(image, draw, (35, 1180, 2465, 2005), rows, "latencyP50MsMean", "latencyP50MsStdDev",
          "(c) P50 da latência", [0, 50, 100, 150, 200, 250, 300, 350],
          "P50 da latência (ms)", label_decimals=0, label_suffix=" ms",
          group_equal_labels=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT, dpi=(300, 300), optimize=True)
    print(OUTPUT)


if __name__ == "__main__":
    main()
