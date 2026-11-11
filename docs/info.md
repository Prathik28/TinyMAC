## How it works

TinyMAC is a 2x2 output-stationary systolic array that multiplies a 2x4 INT8 matrix A by a 4x2 INT8 matrix B into a 2x2 matrix C with 20-bit signed accumulators (C = A x B, or C += A x B in accumulate mode). Matrices are loaded and results read over a register-addressed SPI mode 0 slave. A sticky overflow flag, an on-chip LFSR/MISR built-in self-test (BIST) with a golden signature, a cycle counter and an 8-bit debug bus support silicon validation.

A compute run takes 7 clock cycles. Each processing element (PE) multiplies the A and B bytes passing through it and adds the product to its own accumulator. A values move left to right and B values top to bottom, delayed so that matching operands meet in the right PE.

### SPI interface

Mode 0 (CPOL=0, CPHA=0), MSB first, CS_N active low. The first byte is `{R/W, addr[6:0]}` (bit 7 = 1 for a read). Writes follow with data bytes; the address auto-increments, so a burst fills consecutive registers. Reads insert one dummy byte after the command byte before data appears on MISO.

SCK limits for a clock `clk` (20 MHz specified): writes work up to `clk/4`; reads need `SCK <= clk/8` because MISO is registered behind a two-flop input synchroniser and the first data bit must be ready before the next SCK edge. At 20 MHz that is 5 MHz for writes and 2.5 MHz for reads. Slower is always fine.

### Register map

| Addr | Name | Access | Description |
|---|---|---|---|
| 0x00 | CTRL | W | bit0 START, bit1 CLEAR_ACC, bit2 BIST_START, bit3 CLR_FLAGS (self-clearing; ignored while BUSY) |
| 0x01 | STATUS | R | bit0 BUSY, bit1 DONE, bit2 OVF (sticky), bit3 BIST_DONE, bit4 BIST_PASS |
| 0x02 | ID | R | constant 0xA5 |
| 0x03 | SCRATCH | R/W | free byte for link testing (writable even while BUSY) |
| 0x10-0x17 | A | R/W | A[0][0..3], A[1][0..3], INT8, row-major |
| 0x18-0x1F | B | R/W | B[0][0..1], B[1][0..1], B[2][0..1], B[3][0..1], INT8, row-major |
| 0x20-0x2B | C | R | C00, C01, C10, C11, each 3 bytes little-endian, sign-extended from 20 bits |
| 0x30-0x31 | CYCLE_CNT | R | clock cycles of the last run (7 for a matrix run, about 1409 for BIST) |
| 0x32-0x33 | BIST_SIG | R | BIST signature; golden value is 0xB003 |

Writes to A, B and CTRL are ignored while BUSY. Unmapped addresses read 0.

### Built-in self-test

BIST_START (CTRL bit 2) or a rising edge on BIST_GO runs 64 iterations: a 16-bit LFSR (x^16+x^14+x^13+x^11+1, seed 0xACE1) generates operands, the array computes, and a 16-bit MISR folds all four results. At the end BIST_DONE is set and BIST_PASS is set only if the MISR equals the golden signature 0xB003. BIST leaves DONE and OVF alone and takes about 1409 cycles.

### Debug bus

With DBG_EN (ui[4]) high, uio[7:0] drive a debug byte selected by DBG_SEL (ui[6:5]): 00 = {state, t[1:0], BUSY, DONE, OVF, BIST_PASS}; 01 = C00[7:0]; 10 = LFSR[7:0]; 11 = last SPI byte received. With DBG_EN low, uio is high impedance (inputs).

## How to test

1. Release reset and check that HEARTBEAT (uo[6]) goes high after about 0.1 s (bit 21 of a free-running counter).
2. Read register 0x02 over SPI; it returns 0xA5. Write then read back 0x03 to check the link.
3. Burst-write A (8 bytes) then B (8 bytes) starting at address 0x10.
4. Write CTRL (0x00) = 0x03 to start with cleared accumulators, or 0x01 to accumulate onto the previous C.
5. Wait for DONE (uo[2]) or poll STATUS (0x01).
6. Burst-read 12 bytes from 0x20 to get C.
7. Press BIST_GO (ui[3]) for a one-button self-test; BIST_PASS (uo[5]) goes high on success. A wrong signature leaves it low.

### Bring-up checklist for the first chip

1. Power up, apply a 20 MHz or slower clock, pulse reset. Check HEARTBEAT.
2. SPI at low speed (for example 1 MHz): read 0x02 -> 0xA5, scratch write/read.
3. Identity test: A = [[1,0,0,0],[0,1,0,0]], B = [[1,0],[0,1],[0,0],[0,0]] gives C = [[1,0],[0,1]].
4. Run BIST; expect BIST_PASS high and 0xB003 at 0x32-0x33.
5. Raise SCK step by step (reads up to clk/8) and repeat steps 3-4 to find the SPI margin.
6. Raise the clock toward 20 MHz and repeat; note the highest clock at which BIST still passes.

## Verification

- 17 cocotb tests (SPI framing, registers, directed and 1000 random matrix multiplications against NumPy, accumulate, overflow, debug bus, BIST including fault injection, heartbeat). Gate-level simulation of the hardened netlist runs in CI.
- Line 98.3 %, branch 100 %, expression 99.3 %, toggle 97.7 % code coverage (the remainder is unused pins and unreachable bits; see `test/README.md`).
- SymbiYosys proofs (`formal/`): FSM and counter bounds, A/B/CTRL protection while busy, BUSY and DONE never both high, MISO changes only after a synchronised SCK fall, debug outputs only drive when enabled. Bounded (30 cycles) and unbounded (PDR) proofs run in CI.

## External hardware

An SPI master (for example a microcontroller or the Tiny Tapeout demo board RP2040) and optionally a button on BIST_GO.
