import json
import urllib.request
import zlib
from pathlib import Path
from . import downloader

DEFAULT_CATALOG_URL = "https://raw.githubusercontent.com/nnonickreal/openBES/main/archive/firmwares.json"
MARKER = b"CRC32_OF_IMAGE=0x"

def fetch_catalog(source_url_or_path: str = DEFAULT_CATALOG_URL) -> list:
    source = source_url_or_path.strip()
    if source.startswith(("http://", "https://")):
        req = urllib.request.Request(source, headers={"User-Agent": downloader.USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    else:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Catalog file not found: {source}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

    if isinstance(data, dict):
        if "vendors" in data:
            return data["vendors"]
        devices = data.get("devices") or data.get("headphones") or data.get("firmwares") or []
        return [{"name": "Generic", "devices": devices}] if devices else []
    elif isinstance(data, list):
        if data and "devices" in data[0]:
            return data
        return [{"name": "Generic", "devices": data}]
    return []


def verify_firmware_crc(file_path: Path | str, expected_catalog_crc: str = None) -> tuple[bool, str]:
    data = Path(file_path).read_bytes()
    pos = len(data)
    marker_pos = -1
    expected_crc = None

    while True:
        idx = data.rfind(MARKER, 0, pos)
        if idx == -1:
            break

        crc_end = idx + len(MARKER) + 8
        if crc_end <= len(data):
            hex_candidate = data[idx + len(MARKER):crc_end].decode("ascii", errors="replace")
            try:
                expected_crc = int(hex_candidate, 16)
                marker_pos = idx
                break
            except ValueError:
                pass

        pos = idx

    if marker_pos != -1 and expected_crc is not None:
        actual_crc = zlib.crc32(data[:marker_pos + len(MARKER)]) & 0xFFFFFFFF
        if actual_crc == expected_crc:
            return True, f"CRC32 OK: 0x{actual_crc:08X}"

        if expected_crc == 0:
            return True, f"CRC32 OK (bypassed stub 0x00000000, calculated: 0x{actual_crc:08X})"

        last_magic = data.rfind(b"\xff\xff\xff\xff", 0, marker_pos)
        if last_magic != -1:
            actual_crc_sub = zlib.crc32(data[last_magic:marker_pos + len(MARKER)]) & 0xFFFFFFFF
            if actual_crc_sub == expected_crc:
                return True, f"CRC32 OK (from image start @0x{last_magic:x}): 0x{actual_crc_sub:08X}"

        return False, f"CRC32 mismatch! Expected 0x{expected_crc:08X}, calculated 0x{actual_crc:08X}"

    if expected_catalog_crc:
        try:
            expected_val = int(expected_catalog_crc.strip().replace("0x", ""), 16)
            actual_val = zlib.crc32(data) & 0xFFFFFFFF
            if expected_val == actual_val:
                return True, f"Whole-file CRC32 OK: 0x{actual_val:08X}"
            return False, f"Catalog CRC mismatch! Expected 0x{expected_val:08X}, calculated 0x{actual_val:08X}"
        except ValueError:
            pass

    return True, "No CRC tail marker found; verification skipped"


def download_firmware(url: str, dest_path: Path | str, on_progress=None, log=print) -> str:
    return downloader.download_file(url, dest_path, on_progress=on_progress, log=log)