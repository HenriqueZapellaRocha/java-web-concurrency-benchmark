#!/usr/bin/env python3
"""Gera as figuras da seção CPU-bound diretamente dos CSVs processados."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from statistics import mean

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results" / "processed"
OUTPUT = ROOT / "analysis" / "output" / "figuras"

MAIN_SUMMARY = RESULTS / "cpu-pbkdf2-final" / "summary.csv"
CONFIRMATION_RUNS = RESULTS / "cpu-concurrency-confirmation" / "runs.csv"
CONFIRMATION_SUMMARY = RESULTS / "cpu-concurrency-confirmation" / "summary.csv"

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
VARIANTS = list(LABELS)

INK = "#20242A"
MUTED = "#5D6670"
GRID = "#D9DEE3"
LIGHT = "#EFF2F4"
WHITE = "#FFFFFF"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            index = 1 if bold and path.suffix == ".ttc" else 0
            return ImageFont.truetype(str(path), size=size, index=index)
    return ImageFont.load_default(size=size)


F_TITLE = font(48, True)
F_SUBTITLE = font(28)
F_PANEL = font(34, True)
F_AXIS = font(25)
F_TICK = font(22)
F_LEGEND = font(23)
F_VALUE = font(22, True)
F_POINT = font(26, True)
F_FOOTER = font(20)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def value(row: dict[str, str], key: str) -> float:
    raw = row.get(key, "")
    return float(raw) if raw else 0.0


def pt(value_: float, decimals: int = 1) -> str:
    return f"{value_:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def canvas(width: int, height: int, title: str, subtitle: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (width, height), WHITE)
    draw = ImageDraw.Draw(image)
    draw.text((width // 2, 42), title, fill=INK, font=F_TITLE, anchor="ma")
    draw.text((width // 2, 104), subtitle, fill=MUTED, font=F_SUBTITLE, anchor="ma")
    return image, draw


def marker(draw: ImageDraw.ImageDraw, x: float, y: float, color: str, kind: int, radius: int = 9) -> None:
    box = (x - radius, y - radius, x + radius, y + radius)
    if kind == 0:
        draw.ellipse(box, fill=WHITE, outline=color, width=5)
    elif kind == 1:
        draw.rectangle(box, fill=WHITE, outline=color, width=5)
    elif kind == 2:
        draw.polygon([(x, y - radius), (x + radius, y + radius), (x - radius, y + radius)], fill=WHITE, outline=color)
        draw.line([(x, y - radius), (x + radius, y + radius), (x - radius, y + radius), (x, y - radius)], fill=color, width=5)
    else:
        draw.polygon([(x, y - radius), (x + radius, y), (x, y + radius), (x - radius, y)], fill=WHITE, outline=color)
        draw.line([(x, y - radius), (x + radius, y), (x, y + radius), (x - radius, y), (x, y - radius)], fill=color, width=5)


def legend(draw: ImageDraw.ImageDraw, width: int, y: int) -> None:
    item_width = 420
    start = (width - item_width * len(VARIANTS)) // 2
    for index, variant in enumerate(VARIANTS):
        x = start + index * item_width
        color = COLORS[variant]
        draw.line((x, y, x + 52, y), fill=color, width=6)
        marker(draw, x + 26, y, color, index, 8)
        draw.text((x + 68, y), LABELS[variant], fill=INK, font=F_LEGEND, anchor="lm")


def vertical_axis_label(image: Image.Image, label: str, x: int, y: int) -> None:
    bounds = ImageDraw.Draw(image).textbbox((0, 0), label, font=F_AXIS)
    width, height = bounds[2] - bounds[0] + 6, bounds[3] - bounds[1] + 6
    text_image = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    ImageDraw.Draw(text_image).text(
        (3 - bounds[0], 3 - bounds[1]), label, fill=INK, font=F_AXIS
    )
    rotated = text_image.rotate(90, expand=True)
    image.paste(rotated, (x - rotated.width // 2, y - rotated.height // 2), rotated)


def point_label(amount: float, log_y: bool) -> str:
    if log_y:
        return f"{pt(amount / 1000, 2)} s" if amount >= 1000 else f"{pt(amount, 1)} ms"
    return pt(amount, 1)


def draw_point_labels(
    draw: ImageDraw.ImageDraw,
    labels_by_rate: dict[int, list[tuple[float, float, float, str]]],
    plot_top: int,
    log_y: bool,
) -> None:
    for rate, entries in labels_by_rate.items():
        if not log_y and len({round(amount, 1) for _, _, amount, _ in entries}) == 1:
            px = entries[0][0]
            py = sum(item[1] for item in entries) / len(entries)
            entries = [(px, py, sum(item[2] for item in entries) / len(entries), MUTED)]
            shared = True
        else:
            shared = False

        # Ordenar de baixo para cima mantém rótulos próximos dos pontos e evita colisões.
        ordered = sorted(entries, key=lambda item: item[1], reverse=True)
        positions: list[float] = []
        previous = float("inf")
        for _, py, _, _ in ordered:
            label_y = min(py - 29, previous - 35)
            positions.append(label_y)
            previous = label_y
        if positions[-1] < plot_top - 42:
            shift = plot_top - 42 - positions[-1]
            positions = [position + shift for position in positions]

        offset_x = 100 if rate == 25 else (-100 if rate == 90 else 42)
        for (px, py, amount, color), label_y in zip(ordered, positions):
            label = point_label(amount, log_y)
            if shared:
                label += " (4 var.)"
            label_x = px + offset_x
            bounds = draw.textbbox((label_x, label_y), label, font=F_POINT, anchor="mm")
            box = (bounds[0] - 8, bounds[1] - 5, bounds[2] + 8, bounds[3] + 5)
            draw.line((px, py - 10, label_x, box[3]), fill=color, width=2)
            draw.rounded_rectangle(box, radius=7, fill=WHITE, outline=color, width=2)
            draw.text((label_x, label_y), label, fill=color, font=F_POINT, anchor="mm")


def line_panel(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    rows: list[dict[str, str]],
    metric: str,
    deviation: str,
    title: str,
    y_ticks: list[float],
    y_axis_title: str,
    log_y: bool = False,
    ideal: bool = False,
) -> None:
    left, top, right, bottom = box
    plot_left, plot_top = left + 155, top + 140
    plot_right, plot_bottom = right - 35, bottom - 88
    draw.text(((left + right) // 2, top + 12), title, fill=INK, font=F_PANEL, anchor="ma")

    rates = [25, 60, 75, 90]
    x = lambda rate: plot_left + rates.index(rate) * (plot_right - plot_left) / (len(rates) - 1)
    if log_y:
        low, high = math.log10(y_ticks[0]), math.log10(y_ticks[-1])
        y = lambda amount: plot_bottom - (math.log10(max(amount, y_ticks[0])) - low) / (high - low) * (plot_bottom - plot_top)
    else:
        low, high = y_ticks[0], y_ticks[-1]
        y = lambda amount: plot_bottom - (amount - low) / (high - low) * (plot_bottom - plot_top)

    for tick in y_ticks:
        py = y(tick)
        draw.line((plot_left, py, plot_right, py), fill=GRID, width=2)
        label = f"{int(tick / 1000)} s" if log_y and tick >= 1000 else (f"{int(tick)} ms" if log_y else str(int(tick)))
        draw.text((plot_left - 18, py), label, fill=MUTED, font=F_TICK, anchor="rm")
    for rate in rates:
        px = x(rate)
        draw.line((px, plot_bottom, px, plot_bottom + 9), fill=INK, width=2)
        draw.text((px, plot_bottom + 20), str(rate), fill=INK, font=F_TICK, anchor="ma")

    draw.line((plot_left, plot_top, plot_left, plot_bottom), fill=INK, width=3)
    draw.line((plot_left, plot_bottom, plot_right, plot_bottom), fill=INK, width=3)
    draw.text(((plot_left + plot_right) // 2, bottom - 18), "Taxa oferecida (req/s)", fill=INK, font=F_AXIS, anchor="ms")
    vertical_axis_label(image, y_axis_title, left + 38, (plot_top + plot_bottom) // 2)

    if ideal:
        ideal_points = [(x(rate), y(rate)) for rate in rates]
        draw.line(ideal_points, fill="#7B838B", width=3)
        draw.text((x(90) - 8, y(90) - 16), "ideal", fill=MUTED, font=F_TICK, anchor="rb")

    labels_by_rate: dict[int, list[tuple[float, float, float, str]]] = {rate: [] for rate in rates}
    for variant_index, variant in enumerate(VARIANTS):
        selected = sorted(
            (row for row in rows if row["variant"] == variant),
            key=lambda row: int(row["targetRateRps"]),
        )
        points = [(x(int(row["targetRateRps"])), y(value(row, metric))) for row in selected]
        draw.line(points, fill=COLORS[variant], width=6, joint="curve")
        for row, (px, py) in zip(selected, points):
            mean_value = value(row, metric)
            sd = value(row, deviation)
            lower = max(y_ticks[0], mean_value - sd)
            upper = min(y_ticks[-1], mean_value + sd)
            draw.line((px, y(lower), px, y(upper)), fill=COLORS[variant], width=3)
            draw.line((px - 9, y(lower), px + 9, y(lower)), fill=COLORS[variant], width=3)
            draw.line((px - 9, y(upper), px + 9, y(upper)), fill=COLORS[variant], width=3)
            marker(draw, px, py, COLORS[variant], variant_index)
            labels_by_rate[int(row["targetRateRps"])].append((px, py, mean_value, COLORS[variant]))

    draw_point_labels(draw, labels_by_rate, plot_top, log_y)


def generate_frontier(summary: list[dict[str, str]]) -> None:
    image, draw = canvas(
        2500,
        2050,
        "Capacidade útil e latência",
        "Médias nos pontos; barras = um desvio-padrão; valores coincidentes compartilham rótulo",
    )
    legend(draw, 2500, 170)
    line_panel(
        image,
        draw,
        (40, 215, 1240, 1160),
        summary,
        "successfulRpsMean",
        "successfulRpsStdDev",
        "(a) Vazão útil média",
        [0, 25, 50, 75, 100],
        "Vazão útil média (sucessos/s)",
        ideal=True,
    )
    line_panel(
        image,
        draw,
        (1260, 215, 2460, 1160),
        summary,
        "latencyP99MsMean",
        "latencyP99MsStdDev",
        "(b) P99 da latência — escala logarítmica",
        [10, 100, 1000, 10000, 20000],
        "P99 da latência",
        log_y=True,
    )
    line_panel(
        image,
        draw,
        (40, 1180, 2460, 2005),
        summary,
        "latencyP50MsMean",
        "latencyP50MsStdDev",
        "(c) P50 da latência — escala logarítmica",
        [10, 100, 1000, 10000, 20000],
        "P50 da latência",
        log_y=True,
    )
    image.save(OUTPUT / "cpu-fronteira.png", dpi=(300, 300), optimize=True)


def log_lollipop_panel(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    rows: list[dict[str, str]],
    metric: str,
    title: str,
    ticks: list[float],
    suffix: str,
    categories: list[tuple[str, str, str, int]] | None = None,
) -> None:
    left, top, right, bottom = box
    plot_left, plot_top = left + 320, top + 110
    plot_right, plot_bottom = right - 80, bottom - 85
    draw.text(((left + right) // 2, top + 12), title, fill=INK, font=F_PANEL, anchor="ma")
    low, high = math.log10(ticks[0]), math.log10(ticks[-1])
    x = lambda amount: plot_left + (math.log10(max(amount, ticks[0])) - low) / (high - low) * (plot_right - plot_left)
    if categories is None:
        categories = [
            (variant, LABELS[variant], COLORS[variant], index)
            for index, variant in enumerate(VARIANTS)
        ]
    row_height = (plot_bottom - plot_top) / len(categories)

    for tick in ticks:
        px = x(tick)
        draw.line((px, plot_top, px, plot_bottom), fill=GRID, width=2)
        draw.text((px, plot_bottom + 18), f"{int(tick):,}".replace(",", "."), fill=MUTED, font=F_TICK, anchor="ma")
    draw.text(((plot_left + plot_right) // 2, bottom - 13), "Escala logarítmica", fill=MUTED, font=F_AXIS, anchor="ms")

    for index, (variant, label, color, marker_kind) in enumerate(categories):
        row = next(row for row in rows if row["variant"] == variant and int(row["targetRateRps"]) == 90)
        amount = value(row, metric)
        py = plot_top + row_height * (index + 0.5)
        draw.text((plot_left - 24, py), label, fill=INK, font=F_LEGEND, anchor="rm")
        draw.line((x(ticks[0]), py, x(amount), py), fill=color, width=10)
        marker(draw, x(amount), py, color, marker_kind, 11)
        formatted = pt(amount, 1 if amount < 1000 else 0) + suffix
        label_x, label_y = x(amount), py - 24
        bounds = draw.textbbox((label_x, label_y), formatted, font=F_POINT, anchor="mb")
        background = (bounds[0] - 8, bounds[1] - 5, bounds[2] + 8, bounds[3] + 5)
        draw.rounded_rectangle(background, radius=7, fill=WHITE, outline=color, width=2)
        draw.text((label_x, label_y), formatted, fill=INK, font=F_POINT, anchor="mb")


def generate_oversubscription(summary: list[dict[str, str]]) -> None:
    image, draw = canvas(
        2500,
        1170,
        "Indicadores de disputa pelas duas CPUs em 90 req/s",
        "Médias das cinco rodadas; eixos logarítmicos",
    )
    log_lollipop_panel(
        draw,
        (30, 180, 1240, 1120),
        summary,
        "containerCpuThrottledSecondsMean",
        "(a) Tempo de CPU limitado pelo cgroup",
        [1, 10, 100, 1000],
        " s",
    )
    log_lollipop_panel(
        draw,
        (1260, 180, 2470, 1120),
        summary,
        "nonVoluntaryContextSwitchesMean",
        "(b) Trocas de contexto não voluntárias",
        [1000, 10000, 100000],
        "",
    )
    image.save(OUTPUT / "cpu-oversubscription.png", dpi=(300, 300), optimize=True)


def generate_confirmation_resources(summary: list[dict[str, str]]) -> None:
    categories = [
        ("m1-platform", "M1 · 200 threads", COLORS["m1-platform"], 0),
        ("m1-platform-t2", "M1 · 2 threads", "#B33248", 0),
        ("m1-platform-t4", "M1 · 4 threads", "#7053A3", 0),
        ("m2-virtual", "M2 · virtual", COLORS["m2-virtual"], 1),
        ("m3-event-loop", "M3 · event loop", COLORS["m3-event-loop"], 2),
    ]
    image, draw = canvas(
        2500,
        1270,
        "Disputa por CPU na confirmação de concorrência",
        "Médias das cinco rodadas a 90 req/s; eixos logarítmicos",
    )
    log_lollipop_panel(
        draw,
        (30, 180, 1240, 1220),
        summary,
        "containerCpuThrottledSecondsMean",
        "(a) Tempo acumulado de throttling",
        [1, 10, 100, 1000],
        " s",
        categories,
    )
    log_lollipop_panel(
        draw,
        (1260, 180, 2470, 1220),
        summary,
        "nonVoluntaryContextSwitchesMean",
        "(b) Trocas de contexto não voluntárias",
        [1000, 10000, 100000],
        "",
        categories,
    )
    image.save(OUTPUT / "cpu-confirmacao-recursos.png", dpi=(300, 300), optimize=True)


def paired_panel(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    runs: list[dict[str, str]],
    metric: str,
    title: str,
    ticks: list[float],
    divisor: float = 1.0,
    suffix: str = "",
) -> None:
    left, top, right, bottom = box
    plot_left, plot_top = left + 110, top + 90
    plot_right, plot_bottom = right - 60, bottom - 95
    draw.text(((left + right) // 2, top + 10), title, fill=INK, font=F_PANEL, anchor="ma")
    categories = [
        ("m1-platform", "M1 · 200 threads"),
        ("m1-platform-t4", "M1 · 4 threads"),
        ("m1-platform-t2", "M1 · 2 threads"),
    ]
    x_positions = [
        plot_left + (plot_right - plot_left) * 0.18,
        plot_left + (plot_right - plot_left) * 0.50,
        plot_left + (plot_right - plot_left) * 0.82,
    ]
    low, high = ticks[0], ticks[-1]
    y = lambda amount: plot_bottom - (amount - low) / (high - low) * (plot_bottom - plot_top)

    for tick in ticks:
        py = y(tick)
        draw.line((plot_left, py, plot_right, py), fill=GRID, width=2)
        draw.text((plot_left - 18, py), f"{int(tick)}{suffix}", fill=MUTED, font=F_TICK, anchor="rm")
    draw.line((plot_left, plot_top, plot_left, plot_bottom), fill=INK, width=3)
    draw.line((plot_left, plot_bottom, plot_right, plot_bottom), fill=INK, width=3)
    series: list[dict[int, float]] = []
    for (variant, label), px in zip(categories, x_positions):
        draw.text((px, plot_bottom + 23), label, fill=INK, font=F_AXIS, anchor="ma")
        series.append({
            int(row["repetition"]): value(row, metric) / divisor
            for row in runs
            if row["variant"] == variant
        })
    repetitions = sorted(set.intersection(*(set(values) for values in series)))
    line_colors = ["#6A7683", "#87919B", "#A0A8B0", "#56636F", "#BBC1C6"]
    for index, repetition in enumerate(repetitions):
        color = line_colors[index % len(line_colors)]
        points = [(px, y(values[repetition])) for px, values in zip(x_positions, series)]
        draw.line(points, fill=color, width=4)
        for px, py in points:
            draw.ellipse((px - 8, py - 8, px + 8, py + 8), fill=WHITE, outline=color, width=4)

    means = [mean(values[rep] for rep in repetitions) for values in series]
    mean_points = [(px, y(amount)) for px, amount in zip(x_positions, means)]
    draw.line(mean_points, fill="#9D1C20", width=10)
    for px, py in mean_points:
        draw.ellipse((px - 13, py - 13, px + 13, py + 13), fill=WHITE, outline="#9D1C20", width=7)
    for index, ((px, py), amount) in enumerate(zip(mean_points, means)):
        anchor = "rb" if index == 0 else ("mb" if index == 1 else "lb")
        offset_x = -18 if index == 0 else (0 if index == 1 else 18)
        draw.text((px + offset_x, py - 18), pt(amount, 2), fill="#8A171B", font=F_VALUE, anchor=anchor)


def generate_confirmation(runs: list[dict[str, str]]) -> None:
    image, draw = canvas(
        2500,
        1170,
        "Efeito pareado dos limites de concorrência do M1 em 90 req/s",
        "Linhas finas representam as cinco repetições; linha espessa representa a média",
    )
    paired_panel(
        draw,
        (35, 170, 1240, 1120),
        runs,
        "successfulRps",
        "(a) Vazão útil",
        [20, 40, 60, 80, 100],
    )
    paired_panel(
        draw,
        (1260, 170, 2465, 1120),
        runs,
        "latencyP99Ms",
        "(b) P99 da latência",
        [0, 4, 8, 12, 16],
        divisor=1000.0,
        suffix=" s",
    )
    image.save(OUTPUT / "cpu-confirmacao-pareada.png", dpi=(300, 300), optimize=True)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    summary = read_csv(MAIN_SUMMARY)
    runs = read_csv(CONFIRMATION_RUNS)
    confirmation_summary = read_csv(CONFIRMATION_SUMMARY)
    generate_frontier(summary)
    generate_oversubscription(summary)
    generate_confirmation(runs)
    generate_confirmation_resources(confirmation_summary)
    for name in ("cpu-fronteira.png", "cpu-oversubscription.png", "cpu-confirmacao-pareada.png", "cpu-confirmacao-recursos.png"):
        print(OUTPUT / name)


if __name__ == "__main__":
    main()
