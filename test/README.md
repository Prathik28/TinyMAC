# Sample testbench for a Tiny Tapeout project

This is a sample testbench for a Tiny Tapeout project. It uses [cocotb](https://docs.cocotb.org/en/stable/) to drive the DUT and check the outputs.
See below to get started or for more information, check the [website](https://tinytapeout.com/hdl/testing/).

## Setting up

1. Edit [Makefile](Makefile) and modify `PROJECT_SOURCES` to point to your Verilog files.
2. Edit [tb.v](tb.v) and replace `tt_um_example` with your module name.

## How to run

To run the RTL simulation:

```sh
make -B
```

To run gatelevel simulation, first harden your project and copy `../runs/wokwi/results/final/verilog/gl/{your_module_name}.v` to `gate_level_netlist.v`.

Then run:

```sh
make -B GATES=yes
```

If you wish to save the waveform in VCD format instead of FST format, edit tb.v to use `$dumpfile("tb.vcd");` and then run:

```sh
make -B FST=
```

This will generate `tb.vcd` instead of `tb.fst`.

## How to view the waveform file

Using GTKWave

```sh
gtkwave tb.fst tb.gtkw
```

Using Surfer

```sh
surfer tb.fst
```

## Coverage

`./coverage.sh` re-runs the whole suite under Verilator and prints line, branch,
expression and toggle coverage (annotated sources land in `cov_annot/`).

Measured with 17 tests: line 98.3 %, branch 100 %, expression 99.3 %, toggle 97.7 %.
Everything not covered is deliberate or unreachable:

- `uio_in`, `ui_in[7]`, `uo_out[7]`, `ena`: unused or tied off.
- `cycle_cnt[15:11]`: the longest run (BIST) is 1409 cycles, so they cannot toggle.
- the `default:` branch of the BIST FSM: unreachable by construction (formal proves it).
- heartbeat falling edge (needs 2^22 cycles) and three signature bits that are equal in
  the golden and the fault-injected signature.

`test_bist_fail_detected` injects a fault with `dut.user_project...` (RTL only) and is
skipped in gate-level runs.
