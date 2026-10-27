#!/usr/bin/env python3
"""Compare baseline and enlarged-cache ChampSim workload runs."""

import csv
import re
from dataclasses import dataclass
from pathlib import Path


RUNTIMES = ("python", "java")
PROGRAMS = (
    "Sequential",
    "BranchPredictable",
    "BranchUnpredictable",
    "PointerChase",
    "DynamicDispatch",
)
VARIANTS = ("baseline", "l1d_capacity", "llc_capacity")


@dataclass(frozen=True)
class Sensitivity:
    runtime: str
    program: str
    variant: str
    ipc: float
    cycles: int
    l1d_accesses: int
    l1d_misses: int
    llc_accesses: int
    llc_misses: int


def require(pattern: str, text: str, path: Path) -> re.Match[str]:
    match = re.search(pattern, text, re.MULTILINE)
    if match is None:
        raise ValueError(f"Missing expected ChampSim metric in {path}: {pattern}")
    return match


def parse(path: Path, runtime: str, program: str, variant: str) -> Sensitivity:
    text = path.read_text(encoding="utf-8", errors="replace")
    if "ChampSim completed all CPUs" not in text:
        raise ValueError(f"Incomplete ChampSim output: {path}")
    core = require(
        r"^CPU 0 cumulative IPC:\s*([\d.]+)\s+instructions:\s*\d+\s+cycles:\s*(\d+)",
        text,
        path,
    )

    def cache(name: str, *, absent_if_no_traffic: bool = False) -> tuple[int, int]:
        pattern = rf"^cpu0->{name} TOTAL\s+ACCESS:\s*(\d+)\s+HIT:\s*\d+\s+MISS:\s*(\d+)"
        match = re.search(pattern, text, re.MULTILINE)
        if match is None and absent_if_no_traffic:
            return 0, 0
        if match is None:
            raise ValueError(f"Missing expected ChampSim metric in {path}: {pattern}")
        return int(match.group(1)), int(match.group(2))

    l1d_accesses, l1d_misses = cache("cpu0_L1D")
    _, l1i_misses = cache("cpu0_L1I")
    llc_accesses, llc_misses = cache(
        "LLC",
        absent_if_no_traffic=l1d_misses == 0 and l1i_misses == 0,
    )
    return Sensitivity(
        runtime=runtime,
        program=program,
        variant=variant,
        ipc=float(core.group(1)),
        cycles=int(core.group(2)),
        l1d_accesses=l1d_accesses,
        l1d_misses=l1d_misses,
        llc_accesses=llc_accesses,
        llc_misses=llc_misses,
    )


def write_cycle_reduction_plot(path: Path, rows: list[Sensitivity]) -> None:
    baseline = {
        (row.runtime, row.program): row
        for row in rows
        if row.variant == "baseline"
    }
    programs = (
        "Sequential",
        "BranchPredictable",
        "BranchUnpredictable",
        "PointerChase",
        "DynamicDispatch",
    )
    lines = [
        r"\begin{figure}[htbp]",
        r"\centering",
        r"\begin{tikzpicture}",
        r"\begin{axis}[",
        r"  width=0.92\textwidth,",
        r"  height=6cm,",
        r"  ybar,",
        r"  bar width=5pt,",
        r"  symbolic x coords={Sequential,BranchPredictable,BranchUnpredictable,PointerChase,DynamicDispatch},",
        r"  xtick=data,",
        r"  xticklabels={Sequential,Predictable,Unpredictable,Pointer chase,Dispatch},",
        r"  x tick label style={rotate=20,anchor=east,font=\small},",
        r"  ylabel={Cycle reduction (\%)},",
        r"  ymin=-0.05, ymax=0.55,",
        r"  ytick={0,0.1,0.2,0.3,0.4,0.5},",
        r"  grid=major,",
        r"  legend style={at={(0.5,1.02)},anchor=south,legend columns=4,draw=none,font=\footnotesize},",
        r"]",
    ]
    for runtime in RUNTIMES:
        for variant in ("l1d_capacity", "llc_capacity"):
            coordinates = []
            for program in programs:
                row = next(
                    item
                    for item in rows
                    if item.runtime == runtime
                    and item.program == program
                    and item.variant == variant
                )
                base = baseline[(runtime, program)]
                reduction = 100 * (base.cycles - row.cycles) / base.cycles
                coordinates.append(f"({program},{reduction:.2f})")
            lines.append(r"\addplot coordinates {" + " ".join(coordinates) + "};")
    lines.extend(
        (
            r"\legend{Python L1D,Python LLC,Java L1D,Java LLC}",
            r"\end{axis}",
            r"\end{tikzpicture}",
            r"\caption{Cycle reduction after increasing one cache's capacity by four times. Positive values mean fewer cycles.}",
            r"\label{fig:cache-sensitivity}",
            r"\end{figure}",
        )
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    rows = [
        parse(
            root / "results" / "sensitivity" / f"{runtime}_{program}_{variant}.txt",
            runtime,
            program,
            variant,
        )
        for runtime in RUNTIMES
        for program in PROGRAMS
        for variant in VARIANTS
    ]
    baseline = {
        (row.runtime, row.program): row
        for row in rows
        if row.variant == "baseline"
    }
    csv_path = root / "checkpoint1_cache_sensitivity.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            (
                "runtime",
                "program",
                "variant",
                "ipc",
                "cycles",
                "cycle_reduction_percent_vs_baseline",
                "l1d_miss_rate_percent",
                "llc_miss_rate_percent",
            )
        )
        for row in rows:
            base = baseline[(row.runtime, row.program)]
            writer.writerow(
                (
                    row.runtime,
                    row.program,
                    row.variant,
                    f"{row.ipc:.4f}",
                    row.cycles,
                    f"{100 * (base.cycles - row.cycles) / base.cycles:.2f}",
                    f"{100 * row.l1d_misses / row.l1d_accesses:.2f}" if row.l1d_accesses else "NA",
                    f"{100 * row.llc_misses / row.llc_accesses:.2f}" if row.llc_accesses else "NA",
                )
            )

    tex_lines = [
        r"\noindent\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{lllrrrrr}",
        r"\toprule",
        r"Runtime & Workload & Configuration & IPC & Cycles & L1D miss (\%) & LLC miss (\%) & Cycle reduction (\%) \\",
        r"\midrule",
    ]
    for row in rows:
        base = baseline[(row.runtime, row.program)]
        cycle_reduction = 100 * (base.cycles - row.cycles) / base.cycles
        variant_name = {
            "baseline": "Baseline",
            "l1d_capacity": "4x L1D capacity",
            "llc_capacity": "4x LLC capacity",
        }[row.variant]
        l1d_miss_rate = (
            100 * row.l1d_misses / row.l1d_accesses
            if row.l1d_accesses
            else 0.0
        )
        llc_miss_rate = (
            100 * row.llc_misses / row.llc_accesses
            if row.llc_accesses
            else 0.0
        )
        tex_lines.append(
            f"{row.runtime.title()} & {row.program} & {variant_name} & {row.ipc:.4f}"
            f" & {row.cycles} & {l1d_miss_rate:.2f} & {llc_miss_rate:.2f}"
            f" & {cycle_reduction:+.2f} \\\\"
        )
    tex_lines.extend((r"\bottomrule", r"\end{tabular}%", "}", r"\par\medskip"))
    for runtime in RUNTIMES:
        reductions = [
            100
            * (baseline[(runtime, row.program)].cycles - row.cycles)
            / baseline[(runtime, row.program)].cycles
            for row in rows
            if row.runtime == runtime and row.variant != "baseline"
        ]
        tex_lines.append(
            f"\\noindent {runtime.title()}: the largest cycle reduction across these workloads "
            f"under either 4$\\times$ capacity change was {max(reductions):.2f}\\%. "
            "These tests do not identify a cache-capacity level as dominant.\\\\"
        )
    (root / "checkpoint1_cache_sensitivity.tex").write_text(
        "\n".join(tex_lines) + "\n", encoding="utf-8"
    )
    write_cycle_reduction_plot(root / "checkpoint1_cache_plots.tex", rows)
    print(f"Wrote {csv_path}")


if __name__ == "__main__":
    main()
