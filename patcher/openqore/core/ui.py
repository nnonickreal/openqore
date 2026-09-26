from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass
class Field:
    id: str
    label: str
    kind: str
    default: Any = None
    min: Any = None
    max: Any = None
    choices: Optional[List[Any]] = None
    help: str = ""


def _prompt_bool(f: Field) -> bool:
    default_str = "Y/n" if f.default else "y/N"
    while True:
        raw = input(f"{f.label} [{default_str}]: ").strip().lower()
        if raw == "":
            return bool(f.default)
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("[error] enter y or n")


def _prompt_number(f: Field):
    caster = int if f.kind == "int" else float
    hints = []
    if f.min is not None:
        hints.append(f"min={f.min}")
    if f.max is not None:
        hints.append(f"max={f.max}")
    if f.default is not None:
        hints.append(f"default={f.default}")
    hint_str = f" ({', '.join(hints)})" if hints else ""
    while True:
        raw = input(f"{f.label}{hint_str}: ").strip()
        if raw == "" and f.default is not None:
            return f.default
        try:
            val = caster(raw)
        except ValueError:
            print("[error] invalid number")
            continue
        if f.min is not None and val < f.min:
            print(f"[error] value must be >= {f.min}")
            continue
        if f.max is not None and val > f.max:
            print(f"[error] value must be <= {f.max}")
            continue
        return val


def _prompt_choice(f: Field):
    print(f"{f.label}:")
    norm = [tuple(c) if isinstance(c, (list, tuple)) else (c, str(c)) for c in f.choices]
    for i, (value, label) in enumerate(norm, 1):
        marker = " (default)" if f.default is not None and value == f.default else ""
        print(f"  {i}. {label}{marker}")
    while True:
        raw = input(f"select (1-{len(norm)}): ").strip()
        if raw == "" and f.default is not None:
            return f.default
        try:
            idx = int(raw)
        except ValueError:
            print("[error] invalid choice")
            continue
        if 1 <= idx <= len(norm):
            return norm[idx - 1][0]
        print("[error] out of range")


def _prompt_string(f: Field):
    hint = f" (default={f.default})" if f.default is not None else ""
    raw = input(f"{f.label}{hint}: ").strip()
    return raw if raw else f.default


def ask_console(fields: List[Field]) -> dict:
    values = {}
    for f in fields:
        if f.kind == "info":
            print(f"\n--- {f.label} ---")
            continue
        print()
        if f.help:
            print(f"  ({f.help})")
        if f.kind == "bool":
            values[f.id] = _prompt_bool(f)
        elif f.kind in ("int", "float"):
            values[f.id] = _prompt_number(f)
        elif f.kind == "choice":
            values[f.id] = _prompt_choice(f)
        else:
            values[f.id] = _prompt_string(f)
    return values