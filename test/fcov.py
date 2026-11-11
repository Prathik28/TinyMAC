# SPDX-License-Identifier: Apache-2.0
# Functional coverage for TinyMAC: a list of named behaviours ("bins") that the
# testbench must exercise. Bins are hit either by the SPI helper (register accesses)
# or by a clock-by-clock monitor of internal signals (RTL simulation only).
import os

from cocotb.triggers import RisingEdge

GL = os.environ.get("GATES") == "yes"  # gate-level netlist has no RTL hierarchy

BINS = {
    # --- register writes ---
    "w_ctrl": "write CTRL (0x00)",
    "w_scratch": "write SCRATCH (0x03)",
    "w_A": "write an A byte (0x10-0x17)",
    "w_B": "write a B byte (0x18-0x1F)",
    "w_readonly": "write to a read-only register (ID/STATUS/C/CYCLE/SIG), must be ignored",
    "w_unmapped": "write to an unmapped address, must be ignored",
    # --- register reads ---
    "r_status": "read STATUS (0x01)",
    "r_id": "read ID (0x02)",
    "r_scratch": "read SCRATCH (0x03)",
    "r_A": "read back an A byte",
    "r_B": "read back a B byte",
    "r_C00": "read C[0][0] (0x20-0x22)",
    "r_C01": "read C[0][1] (0x23-0x25)",
    "r_C10": "read C[1][0] (0x26-0x28)",
    "r_C11": "read C[1][1] (0x29-0x2B)",
    "r_cycle_lo": "read CYCLE_CNT low (0x30)",
    "r_cycle_hi": "read CYCLE_CNT high (0x31)",
    "r_sig_lo": "read BIST_SIG low (0x32)",
    "r_sig_hi": "read BIST_SIG high (0x33)",
    "r_unmapped": "read an unmapped address (returns 0)",
    # --- SPI protocol ---
    "spi_burst_write": "burst write of more than one data byte",
    "spi_burst_read": "burst read of more than one data byte",
    "spi_abort": "CS_N released in the middle of a byte",
    "spi_fast_write": "write at SCK = clk/4",
    "spi_slow_read": "read at SCK <= clk/8",
    # --- compute core ---
    "state_idle": "core in IDLE",
    "state_run": "core in RUN",
    "state_done": "core in DONE",
    "run_clear": "run started with CLEAR_ACC (C = A x B)",
    "run_accumulate": "run started without CLEAR_ACC (C += A x B)",
    "ovf_pe00": "overflow in PE00",
    "ovf_pe01": "overflow in PE01",
    "ovf_pe10": "overflow in PE10",
    "ovf_pe11": "overflow in PE11",
    "flag_ovf": "sticky OVF flag set",
    "flag_done": "DONE flag set",
    "clr_flags_active": "CLR_FLAGS issued while a flag was set",
    "mac_min_min": "-128 x -128 operand pair in PE00",
    "mac_max_max": "+127 x +127 operand pair in PE00",
    "mac_min_max": "-128 x +127 operand pair in PE00",
    "write_while_busy": "SPI write attempted while BUSY (must be ignored)",
    "ctrl_while_busy": "CTRL write attempted while BUSY (must be ignored)",
    # --- BIST ---
    "bist_from_reg": "BIST started from CTRL.BIST_START",
    "bist_from_pin": "BIST started from the BIST_GO pin",
    "bist_pin_while_busy": "BIST_GO pin edge while BUSY (must be ignored)",
    "bist_active": "BIST running",
    "bist_pass": "BIST finished with BIST_PASS",
    "bist_fail": "BIST finished without BIST_PASS (fault detected)",
    # --- debug bus ---
    "dbg_sel0": "debug bus enabled, DBG_SEL=00",
    "dbg_sel1": "debug bus enabled, DBG_SEL=01",
    "dbg_sel2": "debug bus enabled, DBG_SEL=10",
    "dbg_sel3": "debug bus enabled, DBG_SEL=11",
    "dbg_hiz": "debug bus disabled, uio outputs released",
}

hits = {b: 0 for b in BINS}


def hit(name):
    hits[name] += 1  # KeyError on a typo is deliberate


def _int(sig):
    try:
        return int(sig.value)
    except ValueError:  # X/Z during reset
        return None


def on_write(addr, data, half):
    for a in range(addr, addr + len(data)):  # the address auto-increments in a burst
        if a == 0x00:
            hit("w_ctrl")
        elif a == 0x03:
            hit("w_scratch")
        elif 0x10 <= a <= 0x17:
            hit("w_A")
        elif 0x18 <= a <= 0x1F:
            hit("w_B")
        elif a in (0x01, 0x02) or 0x20 <= a <= 0x33:
            hit("w_readonly")
        else:
            hit("w_unmapped")
    if len(data) > 1:
        hit("spi_burst_write")
    if half <= 2:
        hit("spi_fast_write")


def on_read(addr, n, half):
    for a in range(addr, addr + n):
        if a == 0x01:
            hit("r_status")
        elif a == 0x02:
            hit("r_id")
        elif a == 0x03:
            hit("r_scratch")
        elif 0x10 <= a <= 0x17:
            hit("r_A")
        elif 0x18 <= a <= 0x1F:
            hit("r_B")
        elif 0x20 <= a <= 0x2B:
            hit(("r_C00", "r_C01", "r_C10", "r_C11")[(a - 0x20) // 3])
        elif a == 0x30:
            hit("r_cycle_lo")
        elif a == 0x31:
            hit("r_cycle_hi")
        elif a == 0x32:
            hit("r_sig_lo")
        elif a == 0x33:
            hit("r_sig_hi")
        else:
            hit("r_unmapped")
    if n > 1:
        hit("spi_burst_read")
    if half >= 4:
        hit("spi_slow_read")


async def monitor(dut):
    """Sample internal signals every clock (RTL simulation only)."""
    if GL:
        return
    u = dut.user_project
    c = u.u_core
    pes = {"pe00": c.pe00, "pe01": c.pe01, "pe10": c.pe10, "pe11": c.pe11}
    while True:
        await RisingEdge(dut.clk)
        if _int(dut.rst_n) != 1:
            continue
        st, busy = _int(u.core_state), _int(u.busy)
        ctrl, wr_en, wr_addr = _int(u.ctrl_pulse), _int(u.wr_en), _int(u.wr_addr)
        done, ovf = _int(u.done), _int(u.ovf)
        if None in (st, busy, ctrl, wr_en, wr_addr, done, ovf):
            continue
        hit(("state_idle", "state_run", "state_done")[st]) if st < 3 else None
        for name, pe in pes.items():
            if _int(pe.ovf) == 1:
                hit("ovf_" + name)
        if ovf:
            hit("flag_ovf")
        if done:
            hit("flag_done")
        bist_done, bist_pass = _int(u.bist_done), _int(u.bist_pass)
        if ctrl & 0x8 and (done or ovf or bist_done):
            hit("clr_flags_active")
        if wr_en and busy:
            hit("write_while_busy")
            if wr_addr == 0x00:
                hit("ctrl_while_busy")
        go = ctrl & 1 and not busy
        if go:
            hit("run_accumulate" if not ctrl & 2 else "run_clear")
        edge = _int(u.bist_go_edge)
        if ctrl & 4 and not busy:
            hit("bist_from_reg")
        if edge and not busy and not ctrl & 1:
            hit("bist_from_pin")
        if edge and busy:
            hit("bist_pin_while_busy")
        if _int(u.bist_active):
            hit("bist_active")
        if bist_done:
            hit("bist_pass" if bist_pass else "bist_fail")
        a, b = _int(c.a_feed0), _int(c.b_feed0)
        if a is not None and b is not None and st == 1:
            if (a, b) == (0x80, 0x80):
                hit("mac_min_min")
            elif (a, b) == (0x7F, 0x7F):
                hit("mac_max_max")
            elif (a, b) in ((0x80, 0x7F), (0x7F, 0x80)):
                hit("mac_min_max")
        if _int(u.dbg_en):
            hit("dbg_sel%d" % _int(u.dbg_sel))
        elif _int(dut.uio_oe) == 0:
            hit("dbg_hiz")


def summary(rtl_only_ok=True):
    skip = {b for b in BINS if GL and b not in _SPI_BINS}
    live = [b for b in BINS if b not in skip]
    got = [b for b in live if hits[b]]
    lines = [f"functional coverage: {len(got)}/{len(live)} bins = {100.0 * len(got) / len(live):.1f} %"]
    for b in live:
        lines.append(f"  [{'x' if hits[b] else ' '}] {b:22s} {hits[b]:7d}  {BINS[b]}")
    return len(got) / len(live), "\n".join(lines)


_SPI_BINS = {b for b in BINS if b.startswith(("w_", "r_", "spi_"))}
