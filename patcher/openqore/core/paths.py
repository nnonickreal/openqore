from pathlib import Path


def home_dir() -> Path:
    p = Path.home() / ".openqore"
    p.mkdir(parents=True, exist_ok=True)
    return p


def bin_dir(module_name: str) -> Path:
    p = home_dir() / "bin" / module_name
    p.mkdir(parents=True, exist_ok=True)
    return p


def modules_json_dir() -> Path:
    p = home_dir() / "modules_json"
    p.mkdir(parents=True, exist_ok=True)
    return p


def modules_py_dir() -> Path:
    p = home_dir() / "modules_py"
    p.mkdir(parents=True, exist_ok=True)
    return p


def cache_dir() -> Path:
    p = home_dir() / "cache"
    p.mkdir(parents=True, exist_ok=True)
    return p