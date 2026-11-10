# SPDX-License-Identifier: Apache-2.0
# TinyMAC phase 1 tests: reset, SPI framing, registers.

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

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
        await self.xfer([addr & 0x7F] + list(data))

    async def read(self, addr, n):
        rx = await self.xfer([0x80 | addr, 0x00] + [0x00] * n)
        assert rx[1] == 0x00, "dummy byte must be 0x00"
        return rx[2:]


async def setup(dut, half=8):
    cocotb.start_soon(Clock(dut.clk, 50, unit="ns").start())  # 20 MHz
    dut.ena.value = 1
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    spi = Spi(dut, half)
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
