from pathlib import Path
from ..tools import unpack as _unpack_tool
from ..tools import repack as _repack_tool

MAGIC = b"\xff\xff\xff\xff"


def detect_packed(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            header = f.read(20)

        if b"\x5d\x00\x00" in header or b"LZMA" in header:
            return True

        return False
    except Exception:
        return False


def unpack(in_path, out_path, extra_data_file=None, log=print):
    kwargs = {}
    if extra_data_file is not None:
        kwargs["extra_data_file"] = extra_data_file
    return _unpack_tool.unpack_firmware(str(in_path), str(out_path), log=log, **kwargs)


def repack(in_path, out_path, chunk_size=_repack_tool.DEFAULT_CHUNK_SIZE, extra_data_file=None, log=print):
    kwargs = {}
    if extra_data_file is not None:
        kwargs["extra_data_file"] = extra_data_file
    return _repack_tool.pack_firmware(str(in_path), str(out_path), chunk_size, log=log, **kwargs)