# SPDX-License-Identifier: Apache-2.0
"""Bit-accurate Python reference model of the TinyMAC datapath."""

import numpy as np

ACC_BITS = 20
ACC_MIN, ACC_MAX = -(1 << (ACC_BITS - 1)), (1 << (ACC_BITS - 1)) - 1


def wrap(v, bits=ACC_BITS):
    """Two's-complement wrap of an integer to `bits` bits."""
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def s8(b):
    return b - 256 if b & 0x80 else b


def matmul(a, b, acc=None, clear=True):
    """C = A x B (clear) or C += A x B, with 20-bit wrap and overflow detection.

    a: 2x4, b: 4x2 signed ints in [-128, 127]. Products are added in k order,
    exactly as each PE does. Returns (2x2 np.int64 array, overflow flag).
    """
    a = np.asarray(a, dtype=np.int64)
    b = np.asarray(b, dtype=np.int64)
    c = np.zeros((2, 2), dtype=np.int64) if clear or acc is None else np.array(acc, dtype=np.int64)
    ovf = False
    for i in range(2):
        for j in range(2):
            s = int(c[i, j])
            for k in range(4):
                exact = s + int(a[i, k]) * int(b[k, j])
                if not ACC_MIN <= exact <= ACC_MAX:
                    ovf = True
                s = wrap(exact)
            c[i, j] = s
    # sanity: without overflow the result must equal plain NumPy
    if not ovf:
        base = np.zeros((2, 2), dtype=np.int64) if clear or acc is None else np.array(acc, dtype=np.int64)
        assert np.array_equal(c, base + a @ b)
    return c, ovf


def ab_bytes(a, b):
    """Register-file byte order: A row-major (0x10..0x17) then B row-major (0x18..0x1F)."""
    return [int(x) & 0xFF for x in np.asarray(a).flatten()] + [int(x) & 0xFF for x in np.asarray(b).flatten()]


def c_from_bytes(raw):
    """12 bytes from 0x20 -> 2x2 signed (3-byte little-endian, sign-extended)."""
    c = np.zeros((2, 2), dtype=np.int64)
    for n in range(4):
        v = raw[3 * n] | (raw[3 * n + 1] << 8) | (raw[3 * n + 2] << 16)
        c[n // 2, n % 2] = wrap(v, 24)
    return c
