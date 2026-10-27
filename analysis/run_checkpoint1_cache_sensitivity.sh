#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
mkdir -p results/sensitivity

for language in python java; do
  for program in Sequential BranchPredictable BranchUnpredictable PointerChase DynamicDispatch; do
    trace="traces/${language}_${program}_skip5000000_1000000.champsim"
    cp "results/${language}_${program}_skip5000000_1000000.txt" \
      "results/sensitivity/${language}_${program}_baseline.txt"
  done
done

for variant in l1d_capacity llc_capacity; do
  case "$variant" in
    l1d_capacity) simulator="./Champsim/bin/champsim_l1d_capacity" ;;
    llc_capacity) simulator="./Champsim/bin/champsim_llc_capacity" ;;
  esac
  for language in python java; do
    for program in Sequential BranchPredictable BranchUnpredictable PointerChase DynamicDispatch; do
      trace="traces/${language}_${program}_skip5000000_1000000.champsim"
      result="results/sensitivity/${language}_${program}_${variant}.txt"
      echo "Simulating $language $program ($variant)"
      "$simulator" \
        --warmup-instructions 100000 \
        --simulation-instructions 899000 \
        "$trace" > "$result" 2>&1
    done
  done
done
