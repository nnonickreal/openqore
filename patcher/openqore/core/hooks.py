import struct


class HookContext:
    """Base toolkit shared by the JSON engine and by advanced python modules:
    signature search/replace, instruction writes, logging, end-of-image
    allocation, VA<->file-offset conversion, plus an optional progress
    callback slot that CLI/GUI frontends can attach for long operations
    (e.g. downloads)."""

    def __init__(self, fw: bytearray, base_address: int = 0, logger=None):
        self.fw = fw
        self.base_address = base_address
        self._log = logger or print
        self.injections = []
        self.progress = None  # callable(done, total, percent) or None

    def log(self, msg: str):
        self._log(msg)

    # ---- addressing ----
    def va_to_off(self, va: int) -> int:
        off = va - self.base_address
        if off < 0:
            raise ValueError(f"va 0x{va:x} below base 0x{self.base_address:x}")
        return off

    def off_to_va(self, off: int) -> int:
        return self.base_address + off

    # ---- raw read/write ----
    def read_u32(self, off: int) -> int:
        return struct.unpack_from("<I", self.fw, off)[0]

    def write_u32(self, off: int, value: int) -> None:
        struct.pack_into("<I", self.fw, off, value)

    def read_bytes(self, off: int, length: int) -> bytes:
        return bytes(self.fw[off:off + length])

    def write_bytes(self, off: int, data: bytes) -> None:
        self.fw[off:off + len(data)] = data

    # ---- signature search ----
    @staticmethod
    def _parse_hex(pattern) -> bytes:
        if isinstance(pattern, (bytes, bytearray)):
            return bytes(pattern)
        return bytes.fromhex(pattern.replace(" ", ""))

    def find_signature(self, pattern, mask=None, start=0, end=None, find_all=False):
        pat = self._parse_hex(pattern)
        msk = self._parse_hex(mask) if mask else b"\xff" * len(pat)
        if len(msk) != len(pat):
            raise ValueError("mask length must match pattern length")
        end = len(self.fw) if end is None else end
        results = []
        off = max(0, start)
        limit = min(end, len(self.fw)) - len(pat)
        while off <= limit:
            ok = True
            for i in range(len(pat)):
                if (self.fw[off + i] & msk[i]) != pat[i]:
                    ok = False
                    break
            if ok:
                if not find_all:
                    return off
                results.append(off)
            off += 1
        return results if find_all else None

    # ---- signature replace ----
    def replace_signature(self, pattern, mask=None, replace=b"", occurrence="first"):
        pat = self._parse_hex(pattern)
        rep = self._parse_hex(replace)
        if len(rep) != len(pat):
            self.log(f"[warning] replace length ({len(rep)}) != pattern length ({len(pat)})")

        hits = self.find_signature(pattern, mask, find_all=True)
        if not hits:
            self.log(f"[warning] signature not found: {pat.hex()}")
            return []

        if occurrence == "first":
            targets = hits[:1]
        elif occurrence == "all":
            targets = hits
        elif isinstance(occurrence, int):
            targets = [hits[occurrence]]
        else:
            targets = hits[:1]

        for off in targets:
            self.write_bytes(off, rep)
            self.log(f"[patch] replaced signature at 0x{off:x} (va=0x{self.off_to_va(off):x})")
        return targets

    def write_instruction(self, off: int, instr_bytes: bytes, comment: str = ""):
        old = self.read_bytes(off, len(instr_bytes))
        self.write_bytes(off, instr_bytes)
        self.log(f"[patch] instruction at 0x{off:x}: {old.hex()} -> {instr_bytes.hex()} {comment}")

    def allocate_at_end(self, data: bytes, align: int = 4, back_offset: int = 0):
        base_off = max(0, len(self.fw) - back_offset)
        end = base_off + len(data)
        self.fw[base_off:end] = data
        pad = (align - (end % align)) % align
        if pad:
            self.fw[end:end + pad] = b"\x00" * pad
            end += pad
        va = self.off_to_va(base_off)
        self.injections.append((base_off, end, va))
        self.log(f"[alloc] injected {len(data)} bytes at file_off=0x{base_off:x} (va=0x{va:x})")
        return base_off, va