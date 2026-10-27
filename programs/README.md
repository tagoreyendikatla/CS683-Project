# Checkpoint-1 microbenchmarks

The Python and Java directories contain matching deterministic workloads for
contrasting basic memory access, branch behavior, pointer chasing, and dynamic
dispatch:

| Program | Intended behavior |
| --- | --- |
| `Sequential` | Streaming through a 65,536-element array/list |
| `BranchPredictable` | A strongly biased conditional branch |
| `BranchUnpredictable` | A conditional driven by a deterministic pseudo-random sequence |
| `PointerChase` | Dependent pointer loads through an 8,192-node object cycle |
| `DynamicDispatch` | Repeated calls through four operation implementations |

Run all programs and collect traces/results from the project root with
`make checkpoint1`. The default trace, warmup, and simulation instruction
counts are controlled by `TRACE_INSTRUCTIONS`, `WARMUP_INSTRUCTIONS`, and
`SIMULATION_INSTRUCTIONS` in the root Makefile. `TRACE_SKIP_INSTRUCTIONS`
lets you skip runtime startup instructions before tracing; the skip count is
included in each trace/result filename. Select a language subset with
`CHECKPOINT_LANGUAGES=python` or `CHECKPOINT_LANGUAGES=java`; both run by
default. Java runs use `-Xshare:off`, Serial GC, and uncompressed object/class
pointers to avoid HotSpot mappings that conflict with Intel PIN; JIT remains
enabled. These options are configurable through `JAVA_OPTS`. The tracer follows
the Java thread explicitly named `checkpoint-main` by each benchmark, so JVM
background threads are not represented. The trace length must exceed the
combined warmup and simulation counts by at least `TRACE_MARGIN_INSTRUCTIONS`
to avoid replaying the trace tail.
For a single workload, use `make PROGRAM=PointerChase run-python` or
`make PROGRAM=PointerChase run-java`.

Each result is a ChampSim simulation of an instruction trace, not wall-clock
runtime on the host. Short traces are useful for checking the setup, but final
comparisons should use longer traces and repeated runs to capture enough of the
workload rather than mostly runtime startup. The native traces include
interpreter/runtime execution, so source-level operation patterns are not
isolated. Compare cache miss statistics, branch statistics, IPC, and
retirement-stall counters across repeated runs.

For checkpoint-1 stall classification, rebuild ChampSim after changes to its
sources and run `analysis/run_checkpoint1_simulations.sh`. The added counters
partition zero-retirement ROI cycles by whether the ROB head is blocked on an
issued, outstanding load. This is a ChampSim-model retirement-blocking metric,
not a hardware-independent stall decomposition. `analysis/summarize_checkpoint1.py`
validates the ten result files and generates the metrics, stall table, and
paired contrasts.

To run the workload cache-capacity sensitivity experiment, configure and build
the L1D and LLC variants from `Champsim`:

```sh
./config.sh champsim_config.json analysis/checkpoint1_l1d_capacity.json
make
./config.sh champsim_config.json analysis/checkpoint1_llc_capacity.json
make
./config.sh champsim_config.json
make
```

Then run `analysis/run_checkpoint1_cache_sensitivity.sh` and
`python3 analysis/summarize_cache_sensitivity.py`. The sensitivity variants
increase one cache's capacity by 4x without changing its latency; they are
comparative model experiments, not proof of uniquely attributable real-hardware
cycles. Build configurations are generated from the baseline config, so rerun
`./config.sh champsim_config.json && make` afterward to restore the baseline
`bin/champsim`.
