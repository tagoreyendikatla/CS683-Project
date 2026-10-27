#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

for language in python java; do
  for program in Sequential BranchPredictable BranchUnpredictable PointerChase DynamicDispatch; do
    trace="traces/${language}_${program}_skip5000000_1000000.champsim"
    result="results/${language}_${program}_skip5000000_1000000.txt"
    echo "Simulating $language $program"
    ./Champsim/bin/champsim \
      --warmup-instructions 100000 \
      --simulation-instructions 899000 \
      "$trace" > "$result" 2>&1
  done
done
