import importlib.util
import json
from pathlib import Path

from . import paths
from .module_base import ModuleBase

BUNDLED_ROOT = Path(__file__).resolve().parent.parent  # .../openqore


def _json_model_dirs():
    yield BUNDLED_ROOT / "modules_json"
    yield paths.modules_json_dir()


def _py_module_dirs():
    yield BUNDLED_ROOT / "modules_py"
    yield paths.modules_py_dir()


def list_json_models():
    models = []
    for d in _json_model_dirs():
        if not d.exists():
            continue
        for p in sorted(d.glob("*.json")):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                models.append({
                    "path": p,
                    "name": data.get("name", p.stem),
                    "chip": data.get("chip", "generic"),
                    "description": data.get("description", "No description provided."),
                    "data": data,
                })
            except Exception as e:
                print(f"[warning] failed to load json model {p}: {e}")
    return models


def _load_module_class(module_py_path: Path):
    spec = importlib.util.spec_from_file_location(f"openqore_module_{module_py_path.stem}", module_py_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for attr in vars(mod).values():
        if isinstance(attr, type) and issubclass(attr, ModuleBase) and attr is not ModuleBase:
            return attr
    raise RuntimeError(f"no ModuleBase subclass found in {module_py_path}")


def list_py_modules():
    modules = []
    for d in _py_module_dirs():
        if not d.exists():
            continue
        for sub in sorted(d.iterdir()):
            if not sub.is_dir():
                continue
            module_py = sub / "module.py"
            if not module_py.exists():
                continue
            manifest = {}
            manifest_path = sub / "manifest.json"
            if manifest_path.exists():
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                except Exception as e:
                    print(f"[warning] failed to load manifest for {sub}: {e}")
            try:
                cls = _load_module_class(module_py)
            except Exception as e:
                print(f"[warning] failed to load module {sub}: {e}")
                continue

            name = manifest.get("name") or getattr(cls, "name", "unnamed")
            chip = manifest.get("chip") or getattr(cls, "chip", "generic")
            description = manifest.get("description") or getattr(cls, "description", "") or "No description provided."

            modules.append({
                "dir": sub,
                "manifest": manifest,
                "cls": cls,
                "name": name,
                "chip": chip,
                "description": description,
            })
    return modules