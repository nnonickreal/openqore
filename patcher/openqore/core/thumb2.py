import struct

# ================= thumb-2 movw (t3) =================
def decode_movw_thumb2(instr4: bytes) -> tuple[int, int]:
    if len(instr4) != 4:
        raise ValueError("instr4 must be exactly 4 bytes")
    hw1, hw2 = struct.unpack("<HH", instr4)

    if (hw1 & 0xf800) != 0xf000:
        raise ValueError("not a 32-bit thumb-2 instruction prefix")
    if (hw1 & 0xfbf0) != 0xf240:
        raise ValueError(f"not movw(t3): hw1=0x{hw1:04x}")

    i = (hw1 >> 10) & 0x1
    imm4 = hw1 & 0xf
    imm3 = (hw2 >> 12) & 0x7
    rd = (hw2 >> 8) & 0xf
    imm8 = hw2 & 0xff

    imm16 = (imm4 << 12) | (i << 11) | (imm3 << 8) | imm8
    return rd, imm16


def encode_movw_thumb2(rd: int, imm16: int) -> bytes:
    if not (0 <= rd <= 15):
        raise ValueError("rd must be 0..15")
    if not (0 <= imm16 <= 0xffff):
        raise ValueError("imm16 must be 0..0xffff")

    imm4 = (imm16 >> 12) & 0xf
    i = (imm16 >> 11) & 0x1
    imm3 = (imm16 >> 8) & 0x7
    imm8 = imm16 & 0xff

    hw1 = 0xf240 | (i << 10) | imm4
    hw2 = (imm3 << 12) | (rd << 8) | imm8
    return struct.pack("<HH", hw1, hw2)


# ================= generic masked-pattern matching =================
def match_masked(fw, off: int, pattern: bytes, mask: bytes) -> bool:
    if off < 0 or off + len(pattern) > len(fw):
        return False
    for i in range(len(pattern)):
        if (fw[off + i] & mask[i]) != pattern[i]:
            return False
    return True


def find_masked_all(fw, pattern: bytes, mask: bytes, start: int, end: int, step: int = 2):
    start = max(0, start)
    end = min(end, len(fw) - len(pattern))
    res = []
    off = start
    while off < end:
        if match_masked(fw, off, pattern, mask):
            res.append(off)
        off += step
    return res


# ---- lsr.w rd, rm, #1 ----
LSR1_PATTERN = bytes([0x4F, 0xEA, 0x50, 0x00])
LSR1_MASK    = bytes([0xEF, 0xFF, 0xF0, 0xF0])


def decode_lsr1(fw, off: int):
    if not match_masked(fw, off, LSR1_PATTERN, LSR1_MASK):
        return None
    rm = fw[off + 2] & 0x0F
    rd = fw[off + 3] & 0x0F
    return rd, rm


def encode_mov_w_noshift(rd: int, rm: int) -> bytes:
    return bytes([0x4F, 0xEA, rm & 0x0F, rd & 0x0F])


# ---- sub.w rd, rn, rm ----
SUBW_PATTERN = bytes([0xA0, 0xEB, 0x00, 0x00])
SUBW_MASK    = bytes([0xE0, 0xFF, 0xF0, 0xF0])


def decode_subw(fw, off: int):
    if not match_masked(fw, off, SUBW_PATTERN, SUBW_MASK):
        return None
    rn = fw[off] & 0x0F
    rm = fw[off + 2] & 0x0F
    rd = fw[off + 3] & 0x0F
    return rd, rn, rm


# ---- add.w rd, rn, rm, lsl #1 ----
ADDW_LSL1_PATTERN = bytes([0x00, 0xEB, 0x40, 0x00])
ADDW_LSL1_MASK    = bytes([0xE0, 0xFF, 0xF0, 0xF0])


def decode_addw_lsl1(fw, off: int):
    if not match_masked(fw, off, ADDW_LSL1_PATTERN, ADDW_LSL1_MASK):
        return None
    rn = fw[off] & 0x0F
    rm = fw[off + 2] & 0x0F
    rd = fw[off + 3] & 0x0F
    return rd, rn, rm


def strip_addw_shift(fw, off: int) -> None:
    fw[off + 2] = fw[off + 2] & 0x0F


# ---- lsrs rd, rm, #2 (thumb-1) ----
LSRS2_PATTERN = bytes([0x80, 0x08])
LSRS2_MASK    = bytes([0xC0, 0xFF])


def decode_lsrs2(fw, off: int):
    if not match_masked(fw, off, LSRS2_PATTERN, LSRS2_MASK):
        return None
    b0 = fw[off]
    rm = (b0 >> 3) & 0x7
    rd = b0 & 0x7
    return rd, rm


def encode_mov_reg(rd: int, rm: int) -> bytes:
    byte0 = ((rd >> 3 & 1) << 7) | ((rm & 0xF) << 3) | (rd & 0x7)
    return bytes([byte0, 0x46])


# ---- bl (thumb-2) ----
def is_bl_opcode(fw, off: int) -> bool:
    if off + 4 > len(fw):
        return False
    hw1 = struct.unpack_from("<H", fw, off)[0]
    hw2 = struct.unpack_from("<H", fw, off + 2)[0]
    return (hw1 & 0xF800) == 0xF000 and (hw2 & 0xD000) == 0xD000


def decode_bl_target_offset(fw, off: int):
    if not is_bl_opcode(fw, off):
        return None
    hw1 = struct.unpack_from("<H", fw, off)[0]
    hw2 = struct.unpack_from("<H", fw, off + 2)[0]
    s = (hw1 >> 10) & 1
    j1 = (hw2 >> 13) & 1
    j2 = (hw2 >> 11) & 1
    i1 = (~(j1 ^ s)) & 1
    i2 = (~(j2 ^ s)) & 1
    imm10 = hw1 & 0x3FF
    imm11 = hw2 & 0x7FF
    imm32 = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
    if s:
        imm32 -= (1 << 25)
    return off + 4 + imm32


def find_bl_after(fw, start: int, max_search: int = 40):
    end = min(start + max_search, len(fw) - 4)
    off = start
    while off < end:
        if is_bl_opcode(fw, off):
            return off
        off += 2
    return None