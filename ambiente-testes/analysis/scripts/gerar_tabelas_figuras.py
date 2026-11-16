#!/usr/bin/env python3
"""Gera as tabelas numéricas associadas às oito figuras de resultados."""

from __future__ import annotations

import csv
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "results" / "processed"
OUTPUT = ROOT / "analysis" / "output" / "tabelas"

VARIANT_LABELS = {
    "m1-platform": "M1 plataforma",
    "m1-platform-t2": "M1, 2 threads",
    "m1-platform-t4": "M1, 4 threads",
    "m1-platform-t250": "M1, 250 threads",
    "m2-virtual": "M2 virtual",
    "m3-event-loop": r"M3 \textit{event loop}",
    "m3-bounded-elastic": r"M3 \texttt{boundedElastic}",
    "m3-reactive": "M3 reativo",
}


def read_csv(study: str, filename: str = "summary.csv") -> list[dict[str, str]]:
    path = PROCESSED / study / filename
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def number(value: float, decimals: int) -> str:
    return f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def metric(row: dict[str, str], name: str, decimals: int, scale: float = 1.0) -> str:
    average = number(float(row[name + "Mean"]) / scale, decimals)
    deviation = number(float(row[name + "StdDev"]) / scale, decimals)
    return f"{average} ({deviation})"


def table(caption: str, label: str, columns: str, headers: list[str],
          rows: list[list[str]]) -> str:
    lines = [
        r"\begin{table}[H]",
        r"    \centering",
        r"    \setlength{\tabcolsep}{3pt}",
        f"    \\caption{{{caption}}}",
        f"    \\label{{{label}}}",
        f"    \\begin{{tabular}}{{{columns}}}",
        r"        \hline",
    ]
    for header in headers:
        lines.append("        " + header + r" \\")
    lines.append(r"        \hline")
    for row in rows:
        lines.append("        " + " & ".join(row) + r" \\")
        lines.append(r"        \hline")
    lines.extend([r"    \end{tabular}", r"\end{table}", ""])
    return "\n".join(lines)


def ordered_summary(study: str, rates: list[int], variants: list[str]) -> list[dict[str, str]]:
    rows = read_csv(study)
    index = {
        (int(row["targetRateRps"]), row["variant"]): row
        for row in rows
        if int(row["targetRateRps"]) in rates and row["variant"] in variants
    }
    expected = {(rate, variant) for rate in rates for variant in variants}
    if set(index) != expected:
        raise ValueError(f"Combinações inesperadas em {study}: {set(index) ^ expected}")
    return [index[(rate, variant)] for rate in rates for variant in variants]


def frontier_table(study: str, rates: list[int], variants: list[str],
                   figure: str, table_label: str, include_p50: bool) -> str:
    entries = ordered_summary(study, rates, variants)
    rows = []
    for row in entries:
        variant = row["variant"]
        cells = [
            number(float(row["targetRateRps"]), 0),
            (r"\mbox{" + VARIANT_LABELS[variant] + "}"
             if variant == "m3-bounded-elastic" else VARIANT_LABELS[variant]),
            r"\mbox{" + metric(row, "successfulRps", 2) + "}",
        ]
        if include_p50:
            cells.append(r"\mbox{" + metric(row, "latencyP50Ms", 1) + "}")
        cells.append(r"\mbox{" + metric(row, "latencyP99Ms", 1) + "}")
        rows.append(cells)
    headers = [
        r"\textbf{Taxa}\newline\textbf{(req/s)} & \textbf{Variante} & "
        r"\textbf{Vazão útil}\newline\textbf{(DP; sucessos/s)}"
        + (r" & \textbf{P50}\newline\textbf{(DP; ms)}" if include_p50 else "")
        + r" & \textbf{P99}\newline\textbf{(DP; ms)}"
    ]
    columns = (
        "|C{1.35cm}|L{4.0cm}|C{3.2cm}|C{3.5cm}|C{3.5cm}|"
        if include_p50 else "|C{1.4cm}|L{4.2cm}|C{4.25cm}|C{4.25cm}|"
    )
    metrics = "vazão útil, P50 e P99" if include_p50 else "vazão útil e P99"
    return table(
        f"Valores da Figura~\\ref{{{figure}}}: {metrics}, médias e desvios padrão "
        "das cinco rodadas. Fonte: elaborado pelo autor.",
        table_label, columns, headers, rows,
    )


def resources_table(study: str, variants: list[str], figure: str, table_label: str) -> str:
    entries = ordered_summary(study, [90], variants)
    rows = [
        [
            VARIANT_LABELS[row["variant"]],
            metric(row, "containerCpuThrottledSeconds", 1),
            metric(row, "nonVoluntaryContextSwitches", 0),
        ]
        for row in entries
    ]
    return table(
        f"Valores da Figura~\\ref{{{figure}}}: \\textit{{throttling}} e trocas de contexto "
        "não voluntárias, médias e desvios padrão das cinco rodadas. "
        "Fonte: elaborado pelo autor.",
        table_label,
        "|L{4.2cm}|C{4.0cm}|C{5.0cm}|",
        [
            r"\textbf{Variante} & \textbf{\textit{Throttling}}\newline"
            r"\textbf{(DP; s)} & \textbf{Trocas não voluntárias}\newline\textbf{(DP)}"
        ],
        rows,
    )


def paired_table(study: str, variants: list[str], short_labels: list[str],
                 figure: str, table_label: str) -> str:
    entries = read_csv(study, "runs.csv")
    index = {(int(row["repetition"]), row["variant"]): row for row in entries}
    repetitions = sorted({repetition for repetition, variant in index if variant in variants})
    if len(repetitions) != 5 or any(
        (repetition, variant) not in index
        for repetition in repetitions for variant in variants
    ):
        raise ValueError(f"Blocos pareados incompletos em {study}")
    rows = []
    for repetition in repetitions:
        selected = [index[(repetition, variant)] for variant in variants]
        rows.append(
            [str(repetition)]
            + [number(float(row["successfulRps"]), 2) for row in selected]
            + [number(float(row["latencyP99Ms"]) / 1000, 2) for row in selected]
        )
    rows.append(
        [r"\textbf{Média}"]
        + [number(mean(float(index[(rep, variant)]["successfulRps"]) for rep in repetitions), 2)
           for variant in variants]
        + [number(mean(float(index[(rep, variant)]["latencyP99Ms"]) for rep in repetitions) / 1000, 2)
           for variant in variants]
    )
    n = len(variants)
    headers = [
        f"\\textbf{{Bloco}} & \\multicolumn{{{n}}}{{c|}}{{\\textbf{{Vazão útil (sucessos/s)}}}}"
        f" & \\multicolumn{{{n}}}{{c|}}{{\\textbf{{P99 (s)}}}}",
        " & " + " & ".join(r"\textbf{" + label + "}" for label in short_labels * 2),
    ]
    width = "2.15cm" if n == 3 else "2.8cm"
    columns = "|C{1.2cm}|" + "|".join([f"C{{{width}}}"] * (2 * n)) + "|"
    return table(
        f"Valores pareados da Figura~\\ref{{{figure}}} por bloco de repetição. "
        "Fonte: elaborado pelo autor.",
        table_label, columns, headers, rows,
    )


def delay_table() -> str:
    entries = read_csv("io-delay-sensitivity-confirmation")
    variants = ["m1-platform", "m2-virtual", "m3-reactive"]
    index = {(int(row["databaseDelay"].removesuffix("ms")), row["variant"]): row
             for row in entries}
    expected = {(delay, variant) for delay in [50, 100, 200] for variant in variants}
    if set(index) != expected:
        raise ValueError("Combinações inesperadas na sensibilidade de atraso")
    rows = []
    for delay in [50, 100, 200]:
        for variant in variants:
            row = index[(delay, variant)]
            rows.append([
                str(delay),
                VARIANT_LABELS[variant],
                r"\mbox{" + metric(row, "successRatio", 2, 0.01) + "}",
                r"\mbox{" + metric(row, "latencyP50Ms", 1) + "}",
                r"\mbox{" + metric(row, "latencyP99Ms", 1) + "}",
            ])
    return table(
        r"Valores da Figura~\ref{fig:io-sensibilidade-atraso}: razão de sucesso, "
        "P50 e P99 por espera controlada, médias e desvios padrão de três rodadas. "
        "Fonte: elaborado pelo autor.",
        "tab:fig-io-sensibilidade-atraso",
        "|C{1.5cm}|L{2.9cm}|C{3.2cm}|C{3.15cm}|C{3.35cm}|",
        [
            r"\textbf{Espera}\newline\textbf{(ms)} & \textbf{Variante} & "
            r"\textbf{Razão de sucesso}\newline\textbf{(DP; \%)} & "
            r"\textbf{P50}\newline\textbf{(DP; ms)} & "
            r"\textbf{P99}\newline\textbf{(DP; ms)}"
        ],
        rows,
    )


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    cpu_variants = ["m1-platform", "m2-virtual", "m3-event-loop", "m3-bounded-elastic"]
    io_variants = ["m1-platform", "m2-virtual", "m3-reactive"]
    confirmation_variants = [
        "m1-platform", "m1-platform-t2", "m1-platform-t4", "m2-virtual", "m3-event-loop"
    ]
    contents = {
        "fig-cpu-fronteira.tex": frontier_table(
            "cpu-pbkdf2-final", [25, 60, 75, 90], cpu_variants,
            "fig:cpu-fronteira", "tab:fig-cpu-fronteira", True,
        ),
        "fig-cpu-oversubscription.tex": resources_table(
            "cpu-pbkdf2-final", cpu_variants,
            "fig:cpu-oversubscription", "tab:fig-cpu-oversubscription",
        ),
        "fig-cpu-confirmacao-pareada.tex": paired_table(
            "cpu-concurrency-confirmation",
            ["m1-platform", "m1-platform-t4", "m1-platform-t2"],
            ["M1, 200", "M1, 4", "M1, 2"],
            "fig:cpu-confirmacao-pareada", "tab:fig-cpu-confirmacao-pareada",
        ),
        "fig-cpu-confirmacao-recursos.tex": resources_table(
            "cpu-concurrency-confirmation", confirmation_variants,
            "fig:cpu-confirmacao-recursos", "tab:fig-cpu-confirmacao-recursos",
        ),
        "fig-io-fronteira.tex": frontier_table(
            "io-database-delay-final", [1000, 1900, 2100, 2300], io_variants,
            "fig:io-fronteira", "tab:fig-io-fronteira", True,
        ),
        "fig-io-limite-threads.tex": paired_table(
            "io-thread-limit-confirmation",
            ["m1-platform", "m1-platform-t250"],
            ["M1, 200", "M1, 250"],
            "fig:io-limite-threads", "tab:fig-io-limite-threads",
        ),
        "fig-io-sensibilidade-atraso.tex": delay_table(),
        "fig-mixed-fronteira.tex": frontier_table(
            "mixed-final", [1000, 1500, 1900], cpu_variants,
            "fig:mixed-fronteira", "tab:fig-mixed-fronteira", True,
        ),
    }
    for filename, content in contents.items():
        path = OUTPUT / filename
        path.write_text(content, encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
