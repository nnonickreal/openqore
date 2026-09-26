#!/usr/bin/env python3
"""
OTA firmware unpacker (decompressor)

Format:
  [4 bytes magic FF FF FF FF]
  repeat:
    [4 bytes big-endian chunk_size]
    [chunk_size bytes of LZMA_ALONE ("legacy .lzma") compressed data]
  until the "size" field no longer looks like a valid chunk header
  [tail: "CRC32_OF_IMAGE=0x" + 8 hex chars + ("\n" (0x0A) or " " (0x20))]
  [optional extra data / secondary images / key-value metadata]
"""
import lzma
import struct
import sys
import zlib
from pathlib import Path

MAGIC = b"\xff\xff\xff\xff"
MARKER = b"CRC32_OF_IMAGE=0x"
EXTRA_DATA_FILE = "extra_data.tmp"
EXTRA_SEP_FILE = "extra_sep.tmp"


def unpack_firmware(
    in_path: str,
    out_path: str,
    extra_data_file: str = EXTRA_DATA_FILE,
    extra_sep_file: str = EXTRA_SEP_FILE,
    log=print,
) -> int:
    data = Path(in_path).read_bytes()
    filesize = len(data)
    if filesize < 4:
        raise ValueError("input file too small")

    if data[:4] != MAGIC:
        log(f"[warning] magic bytes mismatch (got {data[:4].hex()}, expected {MAGIC.hex()})")

    offset = 4
    chunks = 0
    out = bytearray()

    while True:
        remain = filesize - offset
        if remain < 4:
            break

        size = struct.unpack_from(">I", data, offset)[0]
        offset += 4
        remain = filesize - offset

        if size <= 0 or size > remain:
            # not a valid chunk header anymore -> this is the CRC32_OF_IMAGE tail
            offset -= 4
            break

        compressed = data[offset:offset + size]
        offset += size

        log(f"decompressing chunk {chunks} (compressed size={size} bytes)")
        out.extend(lzma.decompress(compressed, format=lzma.FORMAT_ALONE))
        chunks += 1

    Path(out_path).write_bytes(out)
    log(f"Done. Restored {chunks} chunk(s). Output: {out_path} ({len(out)} bytes)")

    # --- Extra data extraction ---
    marker_pos = data.find(MARKER, max(0, offset))
    if marker_pos == -1:
        marker_pos = data.rfind(MARKER)

    extra_file_path = Path(extra_data_file)
    sep_file_path = Path(extra_sep_file)

    if marker_pos != -1:
        crc_end = marker_pos + len(MARKER) + 8
        sep_byte = data[crc_end:crc_end + 1] if crc_end < filesize else b"\x0a"
        extra_data = data[crc_end + 1:] if (crc_end + 1) <= filesize else b""

        # Extra data exists if there is payload after separator, OR separator is 0x20
        if len(extra_data) > 0 or sep_byte == b"\x20":
            extra_file_path.write_bytes(extra_data)

            # Analyze scope if secondary CRC exists in extra data
            scope = "file"
            extra_marker_pos = extra_data.find(MARKER)
            if extra_marker_pos != -1:
                old_hex = extra_data[extra_marker_pos + len(MARKER):extra_marker_pos + len(MARKER) + 8]
                try:
                    old_val = int(old_hex, 16)
                    abs_pos = (crc_end + 1) + extra_marker_pos + len(MARKER)
                    crc_file = zlib.crc32(data[:abs_pos]) & 0xFFFFFFFF
                    crc_extra = zlib.crc32(extra_data[:extra_marker_pos + len(MARKER)]) & 0xFFFFFFFF
                    magic_idx = extra_data.rfind(MAGIC, 0, extra_marker_pos)
                    crc_magic = (
                        zlib.crc32(extra_data[magic_idx:extra_marker_pos + len(MARKER)]) & 0xFFFFFFFF
                        if magic_idx != -1
                        else None
                    )

                    if old_val == crc_extra:
                        scope = "extra"
                    elif crc_magic is not None and old_val == crc_magic:
                        scope = "magic"
                    else:
                        scope = "file"
                except ValueError:
                    scope = "file"

            sep_hex = "20" if sep_byte == b"\x20" else "0A"
            sep_file_path.write_text(f"{sep_hex}\nscope={scope}\n", encoding="ascii")
            log(
                f"[info] Extra data detected ({len(extra_data)} bytes, separator 0x{sep_hex}), "
                f"saved to '{extra_data_file}'"
            )
        else:
            # Clean up stale tmp files
            if extra_file_path.exists():
                extra_file_path.unlink()
            if sep_file_path.exists():
                sep_file_path.unlink()
    else:
        log("[warning] CRC32 marker not found in input file")
        if extra_file_path.exists():
            extra_file_path.unlink()
        if sep_file_path.exists():
            sep_file_path.unlink()

    return chunks


def main(argv):
    if len(argv) != 3:
        print(f"Usage: {argv[0]} <compressed_input> <output_file>")
        return 1
    in_path, out_path = argv[1], argv[2]
    if not Path(in_path).exists():
        print(f"Error: input file '{in_path}' not found")
        return 1
    try:
        unpack_firmware(in_path, out_path)
    except Exception as e:
        print(f"[error] {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))