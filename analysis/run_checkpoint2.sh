#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

languages=(python java)
programs=(Sequential BranchPredictable BranchUnpredictable PointerChase DynamicDispatch)
llc_variants=(checkpoint2_llc_512kb checkpoint2_llc_1mb checkpoint2_llc_4mb checkpoint2_llc_16mb)
prefetch_variants=(checkpoint2_prefetch_next_line checkpoint2_prefetch_ip_stride)

require_file() {
  if [[ ! -f "$1" ]]; then
    echo "Required input is missing: $1" >&2
    exit 1
  fi
}

for language in "${languages[@]}"; do
  for program in "${programs[@]}"; do
    require_file "traces/${language}_${program}_skip5000000_1000000.champsim"
    require_file "results/${language}_${program}_skip5000000_1000000.txt"
    require_file "results/sensitivity/${language}_${program}_llc_capacity.txt"
  done
done

mkdir -p results/checkpoint2/llc_sweep results/checkpoint2/prefetcher
for language in "${languages[@]}"; do
  for program in "${programs[@]}"; do
    cp "results/${language}_${program}_skip5000000_1000000.txt" \
      "results/checkpoint2/llc_sweep/${language}_${program}_2mb.txt"
    cp "results/sensitivity/${language}_${program}_llc_capacity.txt" \
      "results/checkpoint2/llc_sweep/${language}_${program}_8mb.txt"
  done
  cp "results/${language}_PointerChase_skip5000000_1000000.txt" \
    "results/checkpoint2/prefetcher/${language}_PointerChase_no_prefetch.txt"
done

restore_baseline() {
  (
    cd Champsim
    ./config.sh champsim_config.json
    make
  )
}

on_exit() {
  status=$?
  trap - EXIT
  if ! restore_baseline; then
    echo "Warning: failed to restore the baseline ChampSim build configuration." >&2
    if [[ "$status" -eq 0 ]]; then
      status=1
    fi
  fi
  exit "$status"
}
trap on_exit EXIT

run_simulations() {
  local simulator="$1"
  local output_dir="$2"
  local language program trace output
  for language in "${languages[@]}"; do
    for program in "${programs[@]}"; do
      trace="traces/${language}_${program}_skip5000000_1000000.champsim"
      output="${output_dir}/${language}_${program}_${3}.txt"
      echo "Simulating ${language} ${program} (${3})"
      "$simulator" \
        --warmup-instructions 100000 \
        --simulation-instructions 899000 \
        "$trace" > "$output" 2>&1
      grep -q "ChampSim completed all CPUs" "$output" || {
        echo "ChampSim did not complete successfully; see $output" >&2
        exit 1
      }
    done
  done
}

for variant in "${llc_variants[@]}"; do
  echo "Building ${variant}"
  (
    cd Champsim
    ./config.sh champsim_config.json "../analysis/${variant}.json"
    make
    cp bin/champsim "bin/champsim_${variant}"
  )
  case "$variant" in
    checkpoint2_llc_512kb) capacity=512kb ;;
    checkpoint2_llc_1mb) capacity=1mb ;;
    checkpoint2_llc_4mb) capacity=4mb ;;
    checkpoint2_llc_16mb) capacity=16mb ;;
  esac
  run_simulations "./Champsim/bin/champsim_${variant}" \
    "results/checkpoint2/llc_sweep" "$capacity"
done

for variant in "${prefetch_variants[@]}"; do
  echo "Building ${variant}"
  (
    cd Champsim
    ./config.sh champsim_config.json "../analysis/${variant}.json"
    make
    cp bin/champsim "bin/champsim_${variant}"
  )
  prefetcher="${variant#checkpoint2_prefetch_}"
  for language in "${languages[@]}"; do
    trace="traces/${language}_PointerChase_skip5000000_1000000.champsim"
    output="results/checkpoint2/prefetcher/${language}_PointerChase_${prefetcher}.txt"
    echo "Simulating ${language} PointerChase (${prefetcher})"
    "./Champsim/bin/champsim_${variant}" \
      --warmup-instructions 100000 \
      --simulation-instructions 899000 \
      "$trace" > "$output" 2>&1
    grep -q "ChampSim completed all CPUs" "$output" || {
      echo "ChampSim did not complete successfully; see $output" >&2
      exit 1
    }
  done
done

echo "Checkpoint 2 simulations complete."
