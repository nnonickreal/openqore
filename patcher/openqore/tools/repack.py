#!/usr/bin/env python3
import lzma
import struct
import sys
import zlib
from pathlib import Path

MAGIC = b"\xff\xff\xff\xff"
MARKER = b"CRC32_OF_IMAGE=0x"
DEFAULT_CHUNK_SIZE = 131072  # 128 KiB
EXTRA_DATA_FILE = "extra_data.tmp"
EXTRA_SEP_FILE = "extra_sep.tmp"

# xz preset 9 already uses a 64 MiB dictionary -> bit-for-bit equivalent to
# the original `--lzma1=dict=64MiB` override.
_LZMA_FILTERS = [{"id": lzma.FILTER_LZMA1, "preset": 9}]


def _compress_chunk(chunk: bytes) -> bytes:
    return lzma.compress(chunk, format=lzma.FORMAT_ALONE, filters=_LZMA_FILTERS)


def _update_extra_crc(
    extra_data: bytes, file_prefix: bytes, crc_scope: str = "file", log=print
) -> bytes:
    """Recalculates any CRC32_OF_IMAGE markers found in the extra data."""
    out_extra = bytearray()
    pos = 0

    while True:
        idx = extra_data.find(MARKER, pos)
        if idx == -1:
            out_extra.extend(extra_data[pos:])
            break

        # Append everything in extra_data up to and including the marker
        out_extra.extend(extra_data[pos:idx + len(MARKER)])

        # Calculate CRC up to this point
        if crc_scope == "extra":
            data_to_crc = bytes(out_extra)
        elif crc_scope == "magic":
            m_idx = out_extra.rfind(MAGIC, 0, len(out_extra) - len(MARKER))
            data_to_crc = bytes(out_extra[m_idx:]) if m_idx != -1 else bytes(out_extra)
        else:  # "file" (standard repacker logic from byte 0)
            data_to_crc = file_prefix + bytes(out_extra)

        crc = zlib.crc32(data_to_crc) & 0xFFFFFFFF
        crc_str = f"{crc:08X}".encode("ascii")
        log(f"[info] Recalculated secondary CRC in extra data: 0x{crc_str.decode('ascii')}")
        out_extra.extend(crc_str)

        # Skip the original 8-character hex CRC
        pos = idx + len(MARKER) + 8

    return bytes(out_extra)


def pack_firmware(
    in_path: str,
    out_path: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    extra_data_file: str = EXTRA_DATA_FILE,
    extra_sep_file: str = EXTRA_SEP_FILE,
    log=print,
) -> int:
    data = Path(in_path).read_bytes()
    log(f"input: {in_path} -> output: {out_path} (chunk size: {chunk_size} bytes)")

    with open(out_path, "wb") as f:
        f.write(MAGIC)
        chunks = 0
        for off in range(0, len(data), chunk_size):
            chunk = data[off:off + chunk_size]
            compressed = _compress_chunk(chunk)
            log(f"compressing chunk {chunks}... size: {len(compressed)} bytes")
            f.write(struct.pack(">I", len(compressed)))
            f.write(compressed)
            chunks += 1

        f.write(MARKER)

    # Compute primary CRC
    current = Path(out_path).read_bytes()
    crc = zlib.crc32(current) & 0xFFFFFFFF

    extra_file_path = Path(extra_data_file)
    sep_file_path = Path(extra_sep_file)

    has_extra = extra_file_path.exists()
    sep_byte = b"\x0a"
    crc_scope = "file"

    if has_extra:
        if sep_file_path.exists():
            sep_content = sep_file_path.read_text(encoding="ascii", errors="ignore").splitlines()
            if sep_content:
                first_line = sep_content[0].strip().upper()
                sep_byte = b"\x20" if first_line == "20" else b"\x0a"
            for line in sep_content[1:]:
                if line.startswith("scope="):
                    crc_scope = line.split("=", 1)[1].strip()
        else:
            # Fallback auto-detection if extra_sep.tmp is absent
            extra_sample = extra_file_path.read_bytes()[:64]
            if b"=" in extra_sample and not extra_sample.startswith(MAGIC):
                sep_byte = b"\x20"
            else:
                sep_byte = b"\x0a"

    # Write primary CRC and appropriate separator
    with open(out_path, "ab") as f:
        if has_extra and sep_byte == b"\x20":
            # Replace 0x0A with 0x20 before appending extra data
            f.write(f"{crc:08X} ".encode("ascii"))
        else:
            f.write(f"{crc:08X}\n".encode("ascii"))

    # Append extra data if available
    if has_extra:
        extra_data = extra_file_path.read_bytes()
        file_prefix = Path(out_path).read_bytes()
        processed_extra = _update_extra_crc(extra_data, file_prefix, crc_scope, log=log)
        with open(out_path, "ab") as f:
            f.write(processed_extra)
        log(
            f"[info] Appended {len(processed_extra)} bytes of extra data "
            f"(separator 0x{sep_byte.hex().upper()})"
        )

    out_size = Path(out_path).stat().st_size
    log(f"Done! Chunks packed: {chunks}. Final size: {out_size} bytes.")
    return chunks


def main(argv):
    if len(argv) < 3:
        print(f"Usage: {argv[0]} <raw_input_file> <output_ota.bin> [chunk_size_bytes]")
        return 1
    in_path, out_path = argv[1], argv[2]
    chunk_size = int(argv[3]) if len(argv) > 3 else DEFAULT_CHUNK_SIZE
    if not Path(in_path).exists():
        print(f"Error: input file '{in_path}' not found")
        return 1
    try:
        pack_firmware(in_path, out_path, chunk_size)
    except Exception as e:
        print(f"[error] {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))