#!/usr/bin/env python3
"""Summarize the checkpoint 2 LLC sweep and pointer-chase prefetcher runs."""

import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNTIMES = ("python", "java")
PROGRAMS = (
    "Sequential",
    "BranchPredictable",
    "BranchUnpredictable",
    "PointerChase",
    "DynamicDispatch",
)
CAPACITIES = (0.5, 1, 2, 4, 8, 16)
PREFETCHERS = ("no_prefetch", "next_line", "ip_stride")


@dataclass(frozen=True)
class Run:
    ipc: float
    instructions: int
    cycles: int
    memory_wait_percent: float
    l1d_accesses: int
    l1d_misses: int
    llc_accesses: int
    llc_misses: int
    prefetch_issued: int
    prefetch_useful: int
    prefetch_useless: int


def required(pattern: str, text: str, path: Path) -> re.Match[str]:
    match = re.search(pattern, text, re.MULTILINE)
    if match is None:
        raise ValueError(f"Missing expected ChampSim metric in {path}: {pattern}")
    return match


def cache_counts(text: str, name: str, path: Path, *, optional: bool = False) -> tuple[int, int]:
    pattern = rf"^cpu0->{name} TOTAL\s+ACCESS:\s*(\d+)\s+HIT:\s*\d+\s+MISS:\s*(\d+)"
    match = re.search(pattern, text, re.MULTILINE)
    if match is None:
        if optional:
            return 0, 0
        raise ValueError(f"Missing expected cache counters in {path}: {pattern}")
    return int(match.group(1)), int(match.group(2))


def parse(path: Path) -> Run:
    text = path.read_text(encoding="utf-8", errors="replace")
    if "ChampSim completed all CPUs" not in text:
        raise ValueError(f"Incomplete ChampSim output: {path}")

    core = required(
        r"^CPU 0 cumulative IPC:\s*([\d.]+)\s+instructions:\s*(\d+)\s+cycles:\s*(\d+)",
        text,
        path,
    )
    stalls = required(
        r"^CPU 0 zero-retire stall cycles: \d+ memory-wait: \d+ "
        r"\(([\d.]+)% of cycles\)",
        text,
        path,
    )
    l1d_accesses, l1d_misses = cache_counts(text, "cpu0_L1D", path)
    _, l1i_misses = cache_counts(text, "cpu0_L1I", path)
    llc_accesses, llc_misses = cache_counts(
        text, "LLC", path, optional=(l1d_misses == 0 and l1i_misses == 0)
    )
    prefetch = required(
        r"^cpu0->cpu0_L1D PREFETCH REQUESTED:\s*(\d+)\s+ISSUED:\s*(\d+)"
        r"\s+USEFUL:\s*(\d+)\s+USELESS:\s*(\d+)",
        text,
        path,
    )
    return Run(
        ipc=float(core.group(1)),
        instructions=int(core.group(2)),
        cycles=int(core.group(3)),
        memory_wait_percent=float(stalls.group(1)),
        l1d_accesses=l1d_accesses,
        l1d_misses=l1d_misses,
        llc_accesses=llc_accesses,
        llc_misses=llc_misses,
        prefetch_issued=int(prefetch.group(2)),
        prefetch_useful=int(prefetch.group(3)),
        prefetch_useless=int(prefetch.group(4)),
    )


def rate(misses: int, accesses: int) -> str:
    return f"{100 * misses / accesses:.2f}" if accesses else "NA"


def cycle_reduction_percent(baseline: int, current: int) -> float:
    reduction = 100 * (baseline - current) / baseline
    return 0.0 if abs(reduction) < 0.005 else reduction


def capacity_path(runtime: str, program: str, capacity: float) -> Path:
    suffix = "512kb" if capacity == 0.5 else f"{capacity:g}mb"
    return ROOT / "results" / "checkpoint2" / "llc_sweep" / f"{runtime}_{program}_{suffix}.txt"


def write_llc_sweep() -> list[dict[str, object]]:
    rows = []
    baselines: dict[tuple[str, str], Run] = {}
    for runtime in RUNTIMES:
        for program in PROGRAMS:
            for capacity in CAPACITIES:
                run = parse(capacity_path(runtime, program, capacity))
                if capacity == 2:
                    baselines[(runtime, program)] = run
                rows.append(
                    {
                        "runtime": runtime,
                        "program": program,
                        "capacity_mib": capacity,
                        "run": run,
                    }
                )

    output = ROOT / "checkpoint2_llc_sweep.csv"
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            (
                "runtime",
                "program",
                "llc_capacity_mib",
                "ipc",
                "instructions",
                "cycles",
                "cycle_reduction_percent_vs_2mib",
                "memory_wait_percent_of_cycles",
                "l1d_miss_rate_percent",
                "llc_accesses",
                "llc_misses",
                "llc_miss_rate_percent",
            )
        )
        for row in rows:
            run = row["run"]
            baseline = baselines[(row["runtime"], row["program"])]
            writer.writerow(
                (
                    row["runtime"],
                    row["program"],
                    row["capacity_mib"],
                    f"{run.ipc:.4f}",
                    run.instructions,
                    run.cycles,
                    f"{cycle_reduction_percent(baseline.cycles, run.cycles):.2f}",
                    f"{run.memory_wait_percent:.2f}",
                    rate(run.l1d_misses, run.l1d_accesses),
                    run.llc_accesses,
                    run.llc_misses,
                    rate(run.llc_misses, run.llc_accesses),
                )
            )
    return rows


def write_prefetch_results() -> list[dict[str, object]]:
    rows = []
    for runtime in RUNTIMES:
        for prefetcher in PREFETCHERS:
            if prefetcher == "no_prefetch":
                path = ROOT / "results" / f"{runtime}_PointerChase_skip5000000_1000000.txt"
            else:
                path = (
                    ROOT
                    / "results"
                    / "checkpoint2"
                    / "prefetcher"
                    / f"{runtime}_PointerChase_{prefetcher}.txt"
                )
            rows.append(
                {"runtime": runtime, "prefetcher": prefetcher, "run": parse(path)}
            )

    baselines = {
        row["runtime"]: row["run"]
        for row in rows
        if row["prefetcher"] == "no_prefetch"
    }
    output = ROOT / "checkpoint2_prefetcher.csv"
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            (
                "runtime",
                "program",
                "l1d_prefetcher",
                "ipc",
                "instructions",
                "cycles",
                "cycle_reduction_percent_vs_no_prefetch",
                "memory_wait_percent_of_cycles",
                "l1d_miss_rate_percent",
                "llc_miss_rate_percent",
                "l1d_prefetches_issued",
                "l1d_prefetches_useful",
                "l1d_prefetches_useless",
            )
        )
        for row in rows:
            run = row["run"]
            baseline = baselines[row["runtime"]]
            writer.writerow(
                (
                    row["runtime"],
                    "PointerChase",
                    row["prefetcher"],
                    f"{run.ipc:.4f}",
                    run.instructions,
                    run.cycles,
                    f"{cycle_reduction_percent(baseline.cycles, run.cycles):.2f}",
                    f"{run.memory_wait_percent:.2f}",
                    rate(run.l1d_misses, run.l1d_accesses),
                    rate(run.llc_misses, run.llc_accesses),
                    run.prefetch_issued,
                    run.prefetch_useful,
                    run.prefetch_useless,
                )
            )
    return rows


def coordinates(rows: list[dict[str, object]], runtime: str, field: str) -> list[str]:
    points = []
    for program in PROGRAMS:
        values = []
        for row in rows:
            if row["runtime"] == runtime and row["program"] == program:
                run = row["run"]
                capacity = row["capacity_mib"]
                if field == "cycle_reduction":
                    baseline = next(
                        item["run"]
                        for item in rows
                        if item["runtime"] == runtime
                        and item["program"] == program
                        and item["capacity_mib"] == 2
                    )
                    value = cycle_reduction_percent(baseline.cycles, run.cycles)
                else:
                    if not run.llc_accesses:
                        continue
                    value = 100 * run.llc_misses / run.llc_accesses
                values.append((capacity, value))
        points.append((program, values))
    return points


def plot_axis(rows: list[dict[str, object]], metric: str, label: str, title: str) -> list[str]:
    plot_points = {
        runtime: coordinates(rows, runtime, metric) for runtime in RUNTIMES
    }
    y_values = [
        value
        for points in plot_points.values()
        for _, values in points
        for _, value in values
    ]
    minimum = min(y_values) if y_values else 0.0
    maximum = max(y_values) if y_values else 1.0
    padding = max(1.0 if minimum == maximum else 0.1, (maximum - minimum) * 0.05)
    y_min = math.floor((minimum - padding) * 100) / 100
    y_max = math.ceil((maximum + padding) * 100) / 100
    lines = [
        r"\begin{figure}[htbp]",
        r"\centering",
        r"\begin{tikzpicture}",
        r"\begin{groupplot}[",
        r"  group style={group size=1 by 2,vertical sep=1cm},",
        r"  width=0.9\textwidth,height=5cm,",
        r"  xmode=log,log basis x=2,xmin=0.5,xmax=16,",
        r"  xtick={0.5,1,2,4,8,16},",
        r"  xticklabels={$0.5$,$1$,$2$,$4$,$8$,$16$},",
        r"  xlabel={LLC capacity (MiB)},",
        f"  ylabel={{{label}}},",
        f"  ymin={y_min:.2f},ymax={y_max:.2f},",
        r"  grid=major,",
        r"]",
    ]
    for runtime in RUNTIMES:
        lines.append(r"\nextgroupplot[title={" + runtime.title() + "}]")
        for program, values in plot_points[runtime]:
            if not values:
                continue
            point_text = " ".join(
                f"({capacity:g},{value:.2f})" for capacity, value in values
            )
            lines.append(r"\addplot+[mark=*] coordinates {" + point_text + "};")
            lines.append(r"\addlegendentry{" + program + "}")
    lines.extend(
        (
            r"\end{groupplot}",
            r"\end{tikzpicture}",
            r"\caption{" + title + (" Java BranchUnpredictable has no LLC accesses and is omitted." if metric == "llc_miss_rate" else "") + "}",
            r"\end{figure}",
        )
    )
    return lines


def write_plots(rows: list[dict[str, object]]) -> None:
    lines = plot_axis(
        rows,
        "cycle_reduction",
        r"Cycle reduction vs. 2 MiB (\%)",
        "Cycle change across the LLC capacity sweep. Positive values indicate fewer cycles than the 2 MiB run.",
    )
    lines.extend(
        plot_axis(
            rows,
            "llc_miss_rate",
            r"LLC miss rate (\%)",
            "LLC miss rate across the tested capacities.",
        )
    )
    (ROOT / "checkpoint2_plots.tex").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def write_prefetch_table(rows: list[dict[str, object]]) -> None:
    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\small",
        r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{llrrrrrrr}",
        r"\toprule",
        r"Runtime & L1D prefetcher & IPC & Cycles & Cycle reduction (\%) & Memory wait (\%) & L1D miss (\%) & LLC miss (\%) & Useful / issued \\",
        r"\midrule",
    ]
    baselines = {
        row["runtime"]: row["run"]
        for row in rows
        if row["prefetcher"] == "no_prefetch"
    }
    for row in rows:
        run = row["run"]
        baseline = baselines[row["runtime"]]
        reduction = cycle_reduction_percent(baseline.cycles, run.cycles)
        useful_issued = (
            f"{run.prefetch_useful}/{run.prefetch_issued}"
            if run.prefetch_issued
            else "0/0"
        )
        label = {
            "no_prefetch": "None",
            "next_line": "Next-line",
            "ip_stride": "IP-stride",
        }[row["prefetcher"]]
        lines.append(
            f"{row['runtime'].title()} & {label} & {run.ipc:.4f} & {run.cycles}"
            f" & {reduction:+.2f} & {run.memory_wait_percent:.2f}"
            f" & {rate(run.l1d_misses, run.l1d_accesses)}"
            f" & {rate(run.llc_misses, run.llc_accesses)}"
            f" & {useful_issued} \\\\"
        )
    lines.extend(
        (
            r"\bottomrule",
            r"\end{tabular}%",
            "}",
            r"\caption{Pointer-chase results. Prefetch usefulness counts are from the L1D.}",
            r"\end{table}",
        )
    )
    (ROOT / "checkpoint2_prefetch_table.tex").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main() -> None:
    sweep_rows = write_llc_sweep()
    prefetch_rows = write_prefetch_results()
    write_plots(sweep_rows)
    write_prefetch_table(prefetch_rows)
    print(
        "Wrote checkpoint2_llc_sweep.csv, checkpoint2_prefetcher.csv, "
        "checkpoint2_plots.tex, and checkpoint2_prefetch_table.tex"
    )


if __name__ == "__main__":
    main()
