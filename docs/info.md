## How it works

TinyMAC is a 2x2 output-stationary systolic array that multiplies a 2x4 INT8 matrix A by a 4x2 INT8 matrix B into a 2x2 matrix C with 20-bit signed accumulators (C = A x B, or C += A x B in accumulate mode). Matrices are loaded and results read over a register-addressed SPI mode 0 slave. A sticky overflow flag, an on-chip LFSR/MISR built-in self-test (BIST) with a golden signature, a cycle counter and an 8-bit debug bus support silicon validation.

## How to test

1. Release reset and check that the HEARTBEAT output (uo[6]) blinks.
2. Read register 0x02 over SPI; it returns the constant 0xA5.
3. Burst-write A (8 bytes) then B (8 bytes) starting at address 0x10.
4. Write CTRL (0x00) = 0x03 to start with cleared accumulators, or 0x01 to accumulate.
5. Wait for DONE (uo[2]) or poll STATUS (0x01).
6. Burst-read 12 bytes from 0x20 to get C (3 bytes per element, little-endian, sign-extended).
7. Press BIST_GO (ui[3]) for a one-button self-test; BIST_PASS (uo[5]) goes high on success.

SPI is mode 0, MSB first, SCK at most clk/4. Reads insert one dummy byte after the command byte.

## External hardware

An SPI master (for example a microcontroller or the Tiny Tapeout demo board RP2040) and optionally a button on BIST_GO.
