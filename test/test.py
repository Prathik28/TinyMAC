# SPDX-License-Identifier: Apache-2.0
# TinyMAC tests: reset, SPI framing, registers, systolic compute.

import os
import random

import numpy as np

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

import fcov
from model import LFSR_SEED, ab_bytes, bist, c_from_bytes, lfsr_step, matmul

SCK, CS_N, MOSI = 0x01, 0x02, 0x04


class Spi:
    """Bit-banged SPI mode 0 master driving ui_in[2:0]; samples MISO (uo_out[0])."""

    def __init__(self, dut, half=8):
        self.dut = dut
        self.half = half  # clk cycles per SCK half period
        self.extra = 0  # other ui_in bits (BIST_GO, DBG_EN, DBG_SEL)

    def pins(self, sck, cs, mosi):
        self.dut.ui_in.value = self.extra | (SCK if sck else 0) | (0 if cs else CS_N) | (MOSI if mosi else 0)

    async def xfer(self, tx, abort_after_bits=None):
        if abort_after_bits is not None:
            fcov.hit("spi_abort")
        rx, nbits = [], 0
        self.pins(0, True, 0)
        await ClockCycles(self.dut.clk, 4)
        for byte in tx:
            val = 0
            for i in range(7, -1, -1):
                if abort_after_bits is not None and nbits == abort_after_bits:
                    break
                self.pins(0, True, (byte >> i) & 1)
                await ClockCycles(self.dut.clk, self.half)
                val = (val << 1) | (int(self.dut.uo_out.value) & 1)
                self.pins(1, True, (byte >> i) & 1)
                await ClockCycles(self.dut.clk, self.half)
                nbits += 1
            else:
                rx.append(val)
                continue
            break
        self.pins(0, True, 0)
        await ClockCycles(self.dut.clk, 4)
        self.pins(0, False, 0)  # CS_N high
        await ClockCycles(self.dut.clk, 6)
        return rx

    async def write(self, addr, data):
        fcov.on_write(addr & 0x7F, list(data), self.half)
        await self.xfer([addr & 0x7F] + list(data))

    async def read(self, addr, n):
        fcov.on_read(addr, n, self.half)
        rx = await self.xfer([0x80 | addr, 0x00] + [0x00] * n)
        assert rx[1] == 0x00, "dummy byte must be 0x00"
        return rx[2:]


async def setup(dut, half=8):
    cocotb.start_soon(Clock(dut.clk, 50, unit="ns").start())  # 20 MHz
    dut.ena.value = 1
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    spi = Spi(dut, half)
    cocotb.start_soon(fcov.monitor(dut))
    spi.pins(0, False, 0)
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)
    return spi


@cocotb.test()
async def test_reset(dut):
    spi = await setup(dut)
    assert int(dut.uo_out.value) == 0
    assert int(dut.uio_oe.value) == 0
    assert int(dut.uio_out.value) == 0
    assert await spi.read(0x02, 1) == [0xA5]
    assert await spi.read(0x03, 1) == [0x00]
    assert await spi.read(0x10, 16) == [0] * 16


@cocotb.test()
async def test_spi_scratch(dut):
    spi = await setup(dut)
    for v in (0x00, 0xFF, 0x5A, 0xA5, 0x01, 0x80):
        await spi.write(0x03, [v])
        assert await spi.read(0x03, 1) == [v]
    # auto-increment: write 0x02 (ID, read-only) then 0x03 -> only SCRATCH changes
    await spi.write(0x02, [0x11, 0x22])
    assert await spi.read(0x02, 2) == [0xA5, 0x22]


@cocotb.test()
async def test_ab_registers(dut):
    spi = await setup(dut)
    a = [(i * 37 + 5) & 0xFF for i in range(8)]
    b = [(0xFF - i * 29) & 0xFF for i in range(8)]
    await spi.write(0x10, a + b)  # burst of 16
    assert await spi.read(0x10, 8) == a
    assert await spi.read(0x18, 8) == b
    assert await spi.read(0x10, 16) == a + b
    await spi.write(0x13, [0x7F])
    a[3] = 0x7F
    assert await spi.read(0x10, 16) == a + b


@cocotb.test()
async def test_unmapped_and_readonly(dut):
    spi = await setup(dut)
    for addr in (0x04, 0x0F, 0x34, 0x40, 0x7F):
        await spi.write(addr, [0xFF])
        assert await spi.read(addr, 1) == [0x00]
    # C region is read-only and reads zero for now (compute core pending)
    await spi.write(0x20, [0xAB] * 12)
    assert await spi.read(0x20, 12) == [0] * 12
    assert await spi.read(0x30, 4) == [0] * 4


@cocotb.test()
async def test_spi_abort(dut):
    spi = await setup(dut)
    await spi.write(0x03, [0x42])
    # CS_N rises mid data byte: the partial byte must not be written
    await spi.xfer([0x03, 0xFF], abort_after_bits=12)
    assert await spi.read(0x03, 1) == [0x42]
    # CS_N rises mid command byte: next transaction still decodes cleanly
    await spi.xfer([0x83], abort_after_bits=5)
    assert await spi.read(0x02, 1) == [0xA5]


@cocotb.test()
async def test_spi_fast_write(dut):
    # SCK = clk/4 (half period of 2 clk cycles): writes must still work
    spi = await setup(dut, half=2)
    await spi.write(0x10, list(range(1, 17)))
    spi.half = 8
    assert await spi.read(0x10, 16) == list(range(1, 17))


@cocotb.test()
async def test_debug_bus(dut):
    spi = await setup(dut)
    await spi.write(0x03, [0x3C])
    spi.extra = 0x10 | (0b11 << 5)  # DBG_EN=1, DBG_SEL=11 (last byte received)
    spi.pins(0, False, 0)
    await ClockCycles(dut.clk, 6)
    assert int(dut.uio_oe.value) == 0xFF
    await spi.write(0x03, [0x77])
    assert int(dut.uio_out.value) == 0x77
    spi.extra = 0x00
    spi.pins(0, False, 0)
    await ClockCycles(dut.clk, 6)
    assert int(dut.uio_oe.value) == 0x00
    assert int(dut.uio_out.value) == 0x00


# ---------------------------------------------------------------- compute

BUSY, DONE, OVF, BIST_DONE, BIST_PASS = 0x02, 0x04, 0x08, 0x10, 0x20  # uo_out bits


async def pin_monitor(dut, stats):
    """Runs alongside SPI traffic: counts BUSY cycles, checks BUSY/DONE exclusivity."""
    while True:
        await ClockCycles(dut.clk, 1)
        pins = int(dut.uo_out.value)
        if pins & BUSY and pins & DONE:
            stats["both"] += 1
        stats["busy"] += bool(pins & BUSY)


async def run_matmul(dut, spi, a, b, clear=True):
    """Load A/B, start, wait for DONE, read C. Returns (C, STATUS, CYCLE_CNT, busy cycles seen on pin)."""
    await spi.write(0x10, ab_bytes(a, b))
    stats = {"busy": 0, "both": 0}
    mon = cocotb.start_soon(pin_monitor(dut, stats))
    await spi.write(0x00, [0x03 if clear else 0x01])
    for _ in range(200):
        pins = int(dut.uo_out.value)
        if pins & DONE and not pins & BUSY:
            break
        await ClockCycles(dut.clk, 1)
    else:
        raise AssertionError("DONE never rose")
    mon.cancel()
    assert stats["both"] == 0, "BUSY and DONE high together"
    c = c_from_bytes(await spi.read(0x20, 12))
    status = (await spi.read(0x01, 1))[0]
    cyc = await spi.read(0x30, 2)
    return c, status, cyc[0] | (cyc[1] << 8), stats["busy"]


def rand_mat(rng, shape):
    return rng.integers(-128, 128, size=shape)


@cocotb.test()
async def test_matmul_directed(dut):
    spi = await setup(dut, half=6)
    eye_a = np.array([[1, 0, 0, 0], [0, 1, 0, 0]])
    rng = np.random.default_rng(1)
    b_rand = rand_mat(rng, (4, 2))
    cases = {
        "identity": (eye_a, b_rand),
        "zero": (np.zeros((2, 4), int), np.zeros((4, 2), int)),
        "all -128": (np.full((2, 4), -128), np.full((4, 2), -128)),
        "all +127": (np.full((2, 4), 127), np.full((4, 2), 127)),
        "-128 x +127": (np.full((2, 4), -128), np.full((4, 2), 127)),
        "mixed signs": (np.array([[1, -1, 127, -128], [-5, 6, -7, 8]]),
                        np.array([[-1, 2], [3, -4], [-128, 127], [100, -100]])),
        "distinct": (np.arange(1, 9).reshape(2, 4), np.arange(-4, 4).reshape(4, 2)),
    }
    for name, (a, b) in cases.items():
        c, status, cyc, busy_cycles = await run_matmul(dut, spi, a, b)
        exp, ovf = matmul(a, b)
        assert np.array_equal(c, exp), f"{name}: got {c.tolist()} expected {exp.tolist()}"
        assert status == 0x02, f"{name}: STATUS {status:#04x}"  # DONE only
        assert cyc == 7 and busy_cycles == 7, f"{name}: cycles {cyc}/{busy_cycles}"
        dut._log.info(f"{name}: C = {c.tolist()} ok")


@cocotb.test()
async def test_matmul_random(dut):
    spi = await setup(dut, half=5)
    n = int(os.environ.get("RANDOM_N", "1000"))
    rng = np.random.default_rng(2026)
    for it in range(n):
        a, b = rand_mat(rng, (2, 4)), rand_mat(rng, (4, 2))
        c, status, _, _ = await run_matmul(dut, spi, a, b)
        exp, _ = matmul(a, b)
        assert np.array_equal(c, exp), f"case {it}: A={a.tolist()} B={b.tolist()} got {c.tolist()}"
        assert status == 0x02
    dut._log.info(f"{n} random matrix pairs match NumPy")


@cocotb.test()
async def test_accumulate(dut):
    spi = await setup(dut, half=6)
    rng = np.random.default_rng(7)
    for trial in range(5):
        acc = None
        for run in range(4):  # K = 16
            a, b = rand_mat(rng, (2, 4)), rand_mat(rng, (4, 2))
            if trial == 0:  # worst case magnitude
                a, b = np.full((2, 4), -128), np.full((4, 2), -128)
            c, status, _, _ = await run_matmul(dut, spi, a, b, clear=(run == 0))
            acc, ovf = matmul(a, b, acc, clear=(run == 0))
            assert not ovf
            assert np.array_equal(c, acc), f"trial {trial} run {run}: got {c.tolist()} expected {acc.tolist()}"
            assert status == 0x02, f"STATUS {status:#04x} (OVF must stay clear for K=16)"


@cocotb.test()
async def test_overflow(dut):
    spi = await setup(dut, half=6)
    a, b = np.full((2, 4), -128), np.full((4, 2), -128)  # +65536 per run
    acc = None
    for run in range(8):
        c, status, _, _ = await run_matmul(dut, spi, a, b, clear=(run == 0))
        acc, ovf = matmul(a, b, acc, clear=(run == 0))
        assert np.array_equal(c, acc)
        assert bool(status & 0x04) == ovf, f"run {run}: STATUS {status:#04x}, model ovf {ovf}"
    assert ovf and c[0, 0] == -(1 << 19)  # 8 x 65536 = 2^19 wraps to -2^19
    assert int(dut.uo_out.value) & OVF
    # sticky: a fresh, non-overflowing run does not clear it
    c, status, _, _ = await run_matmul(dut, spi, np.ones((2, 4), int), np.ones((4, 2), int))
    assert np.array_equal(c, np.full((2, 2), 4)) and status & 0x04
    # CLR_FLAGS clears OVF and DONE
    await spi.write(0x00, [0x08])
    assert (await spi.read(0x01, 1))[0] == 0x00
    assert not int(dut.uo_out.value) & (OVF | DONE)
    # overflow in the negative direction: -128 x 127 = -16256 per product
    acc = None
    for run in range(9):
        c, status, _, _ = await run_matmul(dut, spi, a, np.full((4, 2), 127), clear=(run == 0))
        acc, ovf = matmul(a, np.full((4, 2), 127), acc, clear=(run == 0))
        assert np.array_equal(c, acc) and bool(status & 0x04) == ovf
    assert ovf


@cocotb.test()
async def test_debug_compute(dut):
    spi = await setup(dut, half=6)
    a = np.array([[3, 0, 0, 0], [0, 0, 0, 0]])
    b = np.array([[-7, 0], [0, 0], [0, 0], [0, 0]])
    await run_matmul(dut, spi, a, b)
    spi.extra = 0x10 | (0b01 << 5)  # DBG_SEL=01: C[0][0][7:0]
    spi.pins(0, False, 0)
    await ClockCycles(dut.clk, 6)
    assert int(dut.uio_out.value) == (-21) & 0xFF
    spi.extra = 0x10  # DBG_SEL=00: {state, k, BUSY, DONE, OVF, BIST_PASS}
    spi.pins(0, False, 0)
    await ClockCycles(dut.clk, 6)
    assert int(dut.uio_out.value) == 0b00_00_0_1_0_0


# ---------------------------------------------------------------- BIST

async def wait_bist(dut, limit=3000):
    for n in range(limit):
        if int(dut.uo_out.value) & BIST_DONE:
            return n
        await ClockCycles(dut.clk, 1)
    raise AssertionError("BIST_DONE never rose")


def final_lfsr():
    x = LFSR_SEED
    for _ in range(64 * 8):
        x = lfsr_step(x)
    return x


@cocotb.test()
async def test_bist(dut):
    spi = await setup(dut, half=6)
    sig, ab_last, c_last = bist()
    dut._log.info(f"model signature {sig:#06x}")

    # --- start from CTRL.BIST_START ---
    await spi.write(0x00, [0x04])
    await wait_bist(dut)
    pins = int(dut.uo_out.value)
    assert pins & BIST_PASS, "BIST_PASS pin low"
    assert not pins & (BUSY | DONE | OVF), f"pins {pins:#04x}: BIST must not set DONE/OVF"
    assert (await spi.read(0x01, 1))[0] == 0x18  # BIST_DONE | BIST_PASS
    raw = await spi.read(0x30, 4)
    cycles, rtl_sig = raw[0] | raw[1] << 8, raw[2] | raw[3] << 8
    dut._log.info(f"BIST took {cycles} cycles, signature {rtl_sig:#06x}")
    assert rtl_sig == sig, f"RTL signature {rtl_sig:#06x} != model {sig:#06x}"
    assert 1200 <= cycles <= 1500
    # BIST leaves its last operands and results behind, exactly as the model predicts
    assert await spi.read(0x10, 16) == ab_last
    assert np.array_equal(c_from_bytes(await spi.read(0x20, 12)), c_last)

    # debug bus DBG_SEL=10 shows LFSR[7:0]
    spi.extra = 0x10 | (0b10 << 5)
    spi.pins(0, False, 0)
    await ClockCycles(dut.clk, 6)
    assert int(dut.uio_out.value) == final_lfsr() & 0xFF
    spi.extra = 0

    # CLR_FLAGS clears BIST_DONE / BIST_PASS
    await spi.write(0x00, [0x08])
    assert (await spi.read(0x01, 1))[0] == 0x00
    assert not int(dut.uo_out.value) & (BIST_DONE | BIST_PASS)

    # --- start from the BIST_GO pin (synchronised + edge detected) ---
    spi.extra = 0x08
    spi.pins(0, False, 0)
    await ClockCycles(dut.clk, 20)
    assert int(dut.uo_out.value) & BUSY
    await wait_bist(dut)
    # holding the button does not retrigger
    await ClockCycles(dut.clk, 50)
    assert not int(dut.uo_out.value) & BUSY
    spi.extra = 0
    spi.pins(0, False, 0)
    assert int(dut.uo_out.value) & BIST_PASS
    assert (await spi.read(0x32, 2)) == [sig & 0xFF, sig >> 8]

    # a normal run still works afterwards and sets DONE
    a, b = np.arange(-4, 4).reshape(2, 4), np.arange(8).reshape(4, 2)
    c, status, cyc, _ = await run_matmul(dut, spi, a, b)
    assert np.array_equal(c, matmul(a, b)[0]) and status == 0x1A and cyc == 7


@cocotb.test()
async def test_busy_ignore(dut):
    spi = await setup(dut, half=4)  # writes are safe at clk/8
    sig, ab_last, _ = bist()
    await spi.write(0x00, [0x04])  # start BIST (~1400 cycles of BUSY)
    assert int(dut.uo_out.value) & BUSY
    await spi.write(0x10, [0x55, 0x55, 0x55, 0x55])  # A: ignored
    await spi.write(0x00, [0x01])  # START: ignored
    await spi.write(0x00, [0x08])  # CLR_FLAGS: ignored
    await spi.write(0x03, [0x99])  # SCRATCH: allowed while busy
    assert int(dut.uo_out.value) & BUSY, "BIST finished before the busy writes completed"
    await wait_bist(dut)
    spi.half = 6
    status = (await spi.read(0x01, 1))[0]
    assert status == 0x18, f"STATUS {status:#04x}: START/CLR_FLAGS must be ignored while busy"
    assert (await spi.read(0x32, 2)) == [sig & 0xFF, sig >> 8], "busy writes corrupted BIST"
    assert await spi.read(0x10, 16) == ab_last
    assert await spi.read(0x03, 1) == [0x99]


@cocotb.test()
async def test_bist_pin_ignored_while_busy(dut):
    """A BIST_GO pin edge while BUSY must not restart or disturb the running BIST."""
    spi = await setup(dut, half=6)
    sig, _, _ = bist()
    await spi.write(0x00, [0x04])  # BIST from register
    await ClockCycles(dut.clk, 50)
    assert int(dut.uo_out.value) & BUSY
    spi.extra = 0x08  # rising edge on the BIST_GO pin while busy
    spi.pins(0, False, 0)
    await ClockCycles(dut.clk, 10)
    spi.extra = 0
    spi.pins(0, False, 0)
    await wait_bist(dut)
    assert (await spi.read(0x32, 2)) == [sig & 0xFF, sig >> 8], "pin edge disturbed the running BIST"
    assert (await spi.read(0x01, 1))[0] == 0x18


@cocotb.test()
async def test_done_cleared_by_bist(dut):
    """Regression for the formal counterexample: run -> DONE high -> BIST must drop DONE."""
    spi = await setup(dut, half=6)
    await run_matmul(dut, spi, np.ones((2, 4), int), np.ones((4, 2), int))
    assert int(dut.uo_out.value) & DONE
    spi.extra = 0x08  # BIST_GO pin
    spi.pins(0, False, 0)
    for _ in range(1500):
        await ClockCycles(dut.clk, 1)
        pins = int(dut.uo_out.value)
        assert not (pins & BUSY and pins & DONE), "BUSY and DONE high together"
        if pins & BIST_DONE:
            break
    spi.extra = 0
    spi.pins(0, False, 0)
    assert int(dut.uo_out.value) & BIST_PASS and not int(dut.uo_out.value) & DONE


@cocotb.test(skip=os.environ.get("GATES") == "yes")  # needs RTL hierarchy
async def test_bist_fail_detected(dut):
    """Fault injection: flip one accumulator bit mid-BIST. The signature must
    change, BIST_PASS must stay low, and a later clean BIST must pass again."""
    spi = await setup(dut, half=6)
    golden, _, _ = bist()

    await spi.write(0x00, [0x04])  # BIST_START
    # wait for a compute run inside the BIST, let it get going, then corrupt PE11
    for _ in range(400):
        await ClockCycles(dut.clk, 1)
        if int(dut.user_project.u_core.state.value) == 1:  # S_RUN
            break
    else:
        raise AssertionError("BIST never started a compute run")
    await ClockCycles(dut.clk, 3)
    dut.user_project.u_core.pe11.acc.value = int(dut.user_project.u_core.pe11.acc.value) ^ 1
    await wait_bist(dut)

    pins = int(dut.uo_out.value)
    assert pins & BIST_DONE, "BIST_DONE must still rise on a failing run"
    assert not pins & BIST_PASS, "BIST_PASS must stay low when the signature is wrong"
    assert (await spi.read(0x01, 1))[0] == 0x08  # BIST_DONE set, BIST_PASS clear
    raw = await spi.read(0x32, 2)
    bad_sig = raw[0] | raw[1] << 8
    assert bad_sig != golden, "a corrupted run must not give the golden signature"
    dut._log.info(f"fault injected: signature {bad_sig:#06x} (golden {golden:#06x})")

    # recovery: a clean BIST passes again
    await spi.write(0x00, [0x08])  # CLR_FLAGS
    await spi.write(0x00, [0x04])
    await wait_bist(dut)
    assert int(dut.uo_out.value) & BIST_PASS
    assert (await spi.read(0x32, 2)) == [golden & 0xFF, golden >> 8]


@cocotb.test()
async def test_heartbeat(dut):
    """HEARTBEAT is bit 21 of a free-running counter: low after reset, then rises."""
    await setup(dut, half=6)
    HB = 0x40
    assert not int(dut.uo_out.value) & HB
    for chunk in range((1 << 21) // (1 << 16) + 2):
        await ClockCycles(dut.clk, 1 << 16)
        if int(dut.uo_out.value) & HB:
            dut._log.info(f"heartbeat high after ~{(chunk + 1) << 16} cycles")
            return
    raise AssertionError("HEARTBEAT never rose within 2^21 + margin cycles")


@cocotb.test()
async def test_zz_functional_coverage(dut):
    """Runs last: report the functional coverage collected by all earlier tests."""
    frac, text = fcov.summary()
    dut._log.info("\n" + text)
    with open("fcov_report.txt", "w") as f:
        f.write(text + "\n")
    assert frac >= 0.95, f"functional coverage {100 * frac:.1f} % is below 95 %"
