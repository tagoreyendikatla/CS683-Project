#!/usr/bin/env python3
"""Focused tests for parsing checkpoint 2 ChampSim output."""

import tempfile
import unittest
from pathlib import Path

from summarize_checkpoint2 import parse


class ParseOutputTests(unittest.TestCase):
    def test_extracts_core_cache_and_prefetch_counters(self) -> None:
        sample = """\
ChampSim completed all CPUs
CPU 0 cumulative IPC: 0.9000 instructions: 899000 cycles: 1000000
CPU 0 zero-retire stall cycles: 500000 memory-wait: 400000 (40.00% of cycles) pipeline/other: 100000 (10.00% of cycles)
cpu0->cpu0_L1D TOTAL        ACCESS:        100 HIT:         80 MISS:         20 MISS_MERGE:          0
cpu0->cpu0_L1I TOTAL        ACCESS:        100 HIT:         95 MISS:          5 MISS_MERGE:          0
cpu0->LLC TOTAL        ACCESS:         20 HIT:          5 MISS:         15 MISS_MERGE:          0
cpu0->cpu0_L1D PREFETCH REQUESTED:         12 ISSUED:         10 USEFUL:          4 USELESS:          3
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "output.txt"
            path.write_text(sample, encoding="utf-8")
            run = parse(path)

        self.assertEqual(run.cycles, 1_000_000)
        self.assertEqual(run.l1d_misses, 20)
        self.assertEqual(run.llc_misses, 15)
        self.assertEqual(run.prefetch_issued, 10)
        self.assertEqual(run.prefetch_useful, 4)
        self.assertEqual(run.memory_wait_percent, 40.0)

    def test_rejects_incomplete_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "output.txt"
            path.write_text("CPU 0 cumulative IPC: 1.0", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Incomplete ChampSim output"):
                parse(path)


if __name__ == "__main__":
    unittest.main()
