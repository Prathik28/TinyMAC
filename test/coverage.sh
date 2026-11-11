#!/usr/bin/env bash
# Code coverage (line / branch / expression / toggle) of the RTL tests, using Verilator.
# Usage: cd test && ./coverage.sh      (needs the cocotb venv active)
set -euo pipefail
rm -rf sim_build/cov coverage.dat cov_annot
RANDOM_N=${RANDOM_N:-20} make SIM=verilator SIM_BUILD=sim_build/cov \
  EXTRA_ARGS="--coverage --timing -Wno-fatal -Wno-DECLFILENAME --public-flat-rw"
verilator_coverage --annotate-all --annotate-min 1 --annotate cov_annot coverage.dat
echo "Lines that were never hit are marked %000000 in cov_annot/*.v"
