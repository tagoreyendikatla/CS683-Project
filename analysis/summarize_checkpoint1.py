#!/usr/bin/env python3
"""Extract comparable metrics from ChampSim checkpoint-1 output files."""

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path


PROGRAMS = (
    "Sequential",
    "BranchPredictable",
    "BranchUnpredictable",
    "PointerChase",
    "DynamicDispatch",
)
LANGUAGES = ("python", "java")
SIMULATION_INSTRUCTION_TOLERANCE = 16


@dataclass(frozen=True)
class Result:
    language: str
    program: str
    ipc: float
    instructions: int
    cycles: int
    zero_retire_cycles: int
    memory_wait_cycles: int
    pipeline_wait_cycles: int
    branch_accuracy: float | None
    branch_mpki: float | None
    conditional_mpki: float | None
    indirect_mpki: float | None
    indirect_call_mpki: float | None
    l1d_accesses: int
    l1d_misses: int
    l1d_miss_latency: float | None
    llc_accesses: int
    llc_misses: int
    llc_miss_latency: float | None

    @property
    def l1d_miss_rate(self) -> float:
        return self.l1d_misses / self.l1d_accesses if self.l1d_accesses else 0.0

    @property
    def llc_miss_rate(self) -> float:
        return self.llc_misses / self.llc_accesses if self.llc_accesses else 0.0


def required_match(pattern: str, text: str, label: str, path: Path) -> re.Match[str]:
    match = re.search(pattern, text, re.MULTILINE)
    if match is None:
        raise ValueError(f"Missing {label} in ChampSim result: {path}")
    return match


def parse_result(path: Path, language: str, program: str) -> Result:
    text = path.read_text(encoding="utf-8", errors="replace")
    if "ChampSim completed all CPUs" not in text:
        raise ValueError(f"Incomplete ChampSim output: {path}")
    core = required_match(
        r"^CPU 0 cumulative IPC:\s*([\d.]+)\s+instructions:\s*(\d+)\s+cycles:\s*(\d+)",
        text,
        "core IPC statistics",
        path,
    )
    branch = required_match(
        r"^CPU 0 Branch Prediction Accuracy:\s*([\d.]+)%\s+MPKI:\s*([\d.]+)",
        text,
        "branch prediction statistics",
        path,
    )
    stalls = required_match(
        r"^CPU 0 zero-retire stall cycles:\s*(\d+)\s+memory-wait:\s*(\d+).*?"
        r"pipeline/other:\s*(\d+)",
        text,
        "retirement-stall breakdown",
        path,
    )
    zero_retire_cycles, memory_wait_cycles, pipeline_wait_cycles = map(
        int, stalls.groups()
    )
    if zero_retire_cycles != memory_wait_cycles + pipeline_wait_cycles:
        raise ValueError(f"Inconsistent retirement-stall counters in ChampSim result: {path}")
    conditional = required_match(
        r"^BRANCH_CONDITIONAL:\s*([\d.]+)",
        text,
        "conditional branch MPKI",
        path,
    )
    indirect = required_match(
        r"^BRANCH_INDIRECT:\s*([\d.]+)",
        text,
        "indirect branch MPKI",
        path,
    )
    indirect_call = required_match(
        r"^BRANCH_INDIRECT_CALL:\s*([\d.]+)",
        text,
        "indirect call MPKI",
        path,
    )

    def cache_metrics(
        name: str, *, absent_means_no_traffic: bool = False
    ) -> tuple[int, int]:
        match = re.search(
            rf"^cpu0->{name} TOTAL\s+ACCESS:\s*(\d+)\s+HIT:\s*(\d+)\s+MISS:\s*(\d+)",
            text,
            re.MULTILINE,
        )
        if match is None:
            if absent_means_no_traffic:
                return 0, 0
            raise ValueError(f"Missing {name} access statistics in ChampSim result: {path}")
        return int(match.group(1)), int(match.group(3))

    def miss_latency(name: str) -> float | None:
        match = re.search(
            rf"^cpu0->{name} AVERAGE MISS LATENCY:\s*([\d.]+)\s+cycles",
            text,
            re.MULTILINE,
        )
        return float(match.group(1)) if match else None

    l1d_accesses, l1d_misses = cache_metrics("cpu0_L1D")
    _, l1i_misses = cache_metrics("cpu0_L1I")
    llc_accesses, llc_misses = cache_metrics(
        "LLC",
        absent_means_no_traffic=l1d_misses == 0 and l1i_misses == 0,
    )
    return Result(
        language=language,
        program=program,
        ipc=float(core.group(1)),
        instructions=int(core.group(2)),
        cycles=int(core.group(3)),
        zero_retire_cycles=zero_retire_cycles,
        memory_wait_cycles=memory_wait_cycles,
        pipeline_wait_cycles=pipeline_wait_cycles,
        branch_accuracy=float(branch.group(1)),
        branch_mpki=float(branch.group(2)),
        conditional_mpki=float(conditional.group(1)),
        indirect_mpki=float(indirect.group(1)),
        indirect_call_mpki=float(indirect_call.group(1)),
        l1d_accesses=l1d_accesses,
        l1d_misses=l1d_misses,
        l1d_miss_latency=miss_latency("cpu0_L1D"),
        llc_accesses=llc_accesses,
        llc_misses=llc_misses,
        llc_miss_latency=miss_latency("LLC"),
    )


def latex_escape(value: str) -> str:
    return value.replace("_", r"\_")


def write_csv(path: Path, results: list[Result]) -> None:
    fields = (
        "language",
        "program",
        "ipc",
        "instructions",
        "cycles",
        "zero_retire_cycles",
        "memory_wait_cycles",
        "pipeline_wait_cycles",
        "memory_wait_percent_of_cycles",
        "pipeline_wait_percent_of_cycles",
        "branch_accuracy_percent",
        "branch_mpki",
        "conditional_mpki",
        "indirect_branch_mpki",
        "indirect_call_mpki",
        "l1d_accesses",
        "l1d_misses",
        "l1d_miss_rate_percent",
        "l1d_average_miss_latency_cycles",
        "llc_accesses",
        "llc_misses",
        "llc_miss_rate_percent",
        "llc_average_miss_latency_cycles",
    )
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fields)
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "language": result.language,
                    "program": result.program,
                    "ipc": f"{result.ipc:.4f}",
                    "instructions": result.instructions,
                    "cycles": result.cycles,
                    "zero_retire_cycles": result.zero_retire_cycles,
                    "memory_wait_cycles": result.memory_wait_cycles,
                    "pipeline_wait_cycles": result.pipeline_wait_cycles,
                    "memory_wait_percent_of_cycles": f"{100 * result.memory_wait_cycles / result.cycles:.2f}",
                    "pipeline_wait_percent_of_cycles": f"{100 * result.pipeline_wait_cycles / result.cycles:.2f}",
                    "branch_accuracy_percent": f"{result.branch_accuracy:.2f}",
                    "branch_mpki": f"{result.branch_mpki:.3f}",
                    "conditional_mpki": f"{result.conditional_mpki:.3f}",
                    "indirect_branch_mpki": f"{result.indirect_mpki:.3f}",
                    "indirect_call_mpki": f"{result.indirect_call_mpki:.3f}",
                    "l1d_accesses": result.l1d_accesses,
                    "l1d_misses": result.l1d_misses,
                    "l1d_miss_rate_percent": f"{100 * result.l1d_miss_rate:.2f}",
                    "l1d_average_miss_latency_cycles": (
                        f"{result.l1d_miss_latency:.1f}"
                        if result.l1d_miss_latency is not None
                        else "NA"
                    ),
                    "llc_accesses": result.llc_accesses,
                    "llc_misses": result.llc_misses,
                    "llc_miss_rate_percent": f"{100 * result.llc_miss_rate:.2f}",
                    "llc_average_miss_latency_cycles": (
                        f"{result.llc_miss_latency:.1f}"
                        if result.llc_miss_latency is not None
                        else "NA"
                    ),
                }
            )


def write_results_table(path: Path, results: list[Result]) -> None:
    lines = [
        r"\noindent\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{llrrrrrrrrr}",
        r"\toprule",
        r"Runtime & Workload & IPC & Branch MPKI & Conditional MPKI & Indirect-call MPKI & Accuracy (\%) & L1D miss (\%) & L1D latency & LLC miss (\%) & LLC latency \\",
        r"\midrule",
    ]
    for result in results:
        l1d_latency = (
            f"{result.l1d_miss_latency:.1f}"
            if result.l1d_miss_latency is not None
            else "--"
        )
        llc_latency = (
            f"{result.llc_miss_latency:.1f}"
            if result.llc_miss_latency is not None
            else "--"
        )
        lines.append(
            f"{result.language.title()} & {latex_escape(result.program)}"
            f" & {result.ipc:.4f} & {result.branch_mpki:.3f}"
            f" & {result.conditional_mpki:.3f} & {result.indirect_call_mpki:.3f}"
            f" & {result.branch_accuracy:.2f}"
            f" & {100 * result.l1d_miss_rate:.2f}"
            f" & {l1d_latency}"
            f" & {100 * result.llc_miss_rate:.2f}"
            f" & {llc_latency} \\\\"
        )
    lines.extend((r"\bottomrule", r"\end{tabular}%", "}"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_stalls_table(path: Path, results: list[Result]) -> None:
    lines = [
        r"\noindent\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{llrrr}",
        r"\toprule",
        r"Runtime & Workload & Zero-retire cycles (\%) & Memory-wait (\%) & Pipeline/other (\%) \\",
        r"\midrule",
    ]
    for result in results:
        lines.append(
            f"{result.language.title()} & {latex_escape(result.program)}"
            f" & {100 * result.zero_retire_cycles / result.cycles:.2f}"
            f" & {100 * result.memory_wait_cycles / result.cycles:.2f}"
            f" & {100 * result.pipeline_wait_cycles / result.cycles:.2f} \\\\"
        )
    lines.extend((r"\bottomrule", r"\end{tabular}%", "}"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_memory_wait_plot(path: Path, results: list[Result]) -> None:
    by_key = {(result.language, result.program): result for result in results}
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
        r"  bar width=10pt,",
        r"  symbolic x coords={Sequential,BranchPredictable,BranchUnpredictable,PointerChase,DynamicDispatch},",
        r"  xtick=data,",
        r"  xticklabels={Sequential,Predictable,Unpredictable,Pointer chase,Dispatch},",
        r"  x tick label style={rotate=20,anchor=east,font=\small},",
        r"  ylabel={Memory-wait share (\% of cycles)},",
        r"  ymin=0, ymax=80,",
        r"  ytick={0,20,40,60,80},",
        r"  grid=major,",
        r"  legend style={at={(0.5,1.02)},anchor=south,legend columns=2,draw=none},",
        r"]",
    ]
    for language in LANGUAGES:
        coordinates = " ".join(
            f"({program},{100 * by_key[(language, program)].memory_wait_cycles / by_key[(language, program)].cycles:.2f})"
            for program in programs
        )
        lines.append(r"\addplot coordinates {" + coordinates + "};")
    lines.extend(
        (
            r"\legend{Python,Java}",
            r"\end{axis}",
            r"\end{tikzpicture}",
            r"\caption{Memory-wait share by workload, using the simulator rule described in the text.}",
            r"\label{fig:memory-wait}",
            r"\end{figure}",
        )
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_findings(path: Path, results: list[Result]) -> None:
    by_key = {(result.language, result.program): result for result in results}
    lines: list[str] = []
    for language in LANGUAGES:
        predictable = by_key.get((language, "BranchPredictable"))
        unpredictable = by_key.get((language, "BranchUnpredictable"))
        if predictable and unpredictable:
            mpki_delta = unpredictable.branch_mpki - predictable.branch_mpki
            ipc_delta = unpredictable.ipc - predictable.ipc
            lines.append(
                f"\\textbf{{{language.title()} branch-pattern contrast.}} "
                f"The unpredictable-pattern trace has "
                f"{mpki_delta:+.3f} branch MPKI and {ipc_delta:+.4f} IPC "
                f"relative to the predictable-pattern trace. "
                "This is a trace-level contrast, not a direct count of cycles lost to branch mispredictions."
            )

        sequential = by_key.get((language, "Sequential"))
        pointer = by_key.get((language, "PointerChase"))
        if sequential and pointer:
            l1d_delta = 100 * (pointer.l1d_miss_rate - sequential.l1d_miss_rate)
            llc_delta = 100 * (pointer.llc_miss_rate - sequential.llc_miss_rate)
            lines.append(
                f"\\textbf{{{language.title()} memory-pattern contrast.}} "
                f"The pointer-chase trace differs from sequential access by "
                f"{l1d_delta:+.2f} percentage points in L1D miss rate and "
                f"{llc_delta:+.2f} percentage points in LLC miss rate. "
                "Dependent-load latency is not equivalent to total memory-stall cycles."
            )

    if not lines:
        lines.append(
            "The required paired workloads are incomplete, so no paired contrasts were generated."
        )
    path.write_text("\n\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument("--traces-dir", type=Path, default=Path("traces"))
    parser.add_argument("--trace-skip", type=int, default=5_000_000)
    parser.add_argument("--trace-instructions", type=int, default=1_000_000)
    parser.add_argument("--simulation-instructions", type=int, default=899_000)
    parser.add_argument("--output-dir", type=Path, default=Path("."))
    args = parser.parse_args()

    results: list[Result] = []
    missing: list[Path] = []
    suffix = f"skip{args.trace_skip}_{args.trace_instructions}.txt"
    for language in LANGUAGES:
        for program in PROGRAMS:
            result_path = args.results_dir / f"{language}_{program}_{suffix}"
            trace_path = args.traces_dir / f"{language}_{program}_{suffix.removesuffix('.txt')}.champsim"
            if not result_path.is_file():
                missing.append(result_path)
                continue
            expected_bytes = args.trace_instructions * 64
            actual_bytes = trace_path.stat().st_size if trace_path.is_file() else -1
            if actual_bytes != expected_bytes:
                raise SystemExit(
                    f"Incomplete trace {trace_path}: expected {expected_bytes} bytes "
                    f"for {args.trace_instructions} instructions, got {actual_bytes}."
                )
            result = parse_result(result_path, language, program)
            minimum_instructions = args.simulation_instructions
            maximum_instructions = (
                args.simulation_instructions + SIMULATION_INSTRUCTION_TOLERANCE
            )
            if not minimum_instructions <= result.instructions <= maximum_instructions:
                raise SystemExit(
                    f"Unexpected simulation length in {result_path}: expected "
                    f"{minimum_instructions} to {maximum_instructions} instructions, "
                    f"got {result.instructions}."
                )
            results.append(result)

    if missing:
        missing_list = "\n".join(f"  - {path}" for path in missing)
        raise SystemExit(f"Missing {len(missing)} expected ChampSim result(s):\n{missing_list}")
    if len(results) != len(LANGUAGES) * len(PROGRAMS):
        raise SystemExit("Expected exactly one complete result for each language/workload pair.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "checkpoint1_metrics.csv", results)
    write_results_table(args.output_dir / "checkpoint1_results.tex", results)
    write_stalls_table(args.output_dir / "checkpoint1_stalls.tex", results)
    write_memory_wait_plot(args.output_dir / "checkpoint1_plots.tex", results)
    write_findings(args.output_dir / "checkpoint1_findings.tex", results)
    print(
        f"Summarized {len(results)} ChampSim results into "
        f"{args.output_dir / 'checkpoint1_metrics.csv'}"
    )


if __name__ == "__main__":
    main()
