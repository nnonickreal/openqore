from typing import List
from .ui import Field


class ModuleBase:
    """Base class for advanced (python) firmware patch modules."""

    name = "unnamed"
    chip = "generic"
    version = "0.1"
    description = ""
    author = ""

    # stage 1: fields independent from firmware content (e.g. base address,
    # toggles, target sample rate...)
    def get_static_fields(self, ctx) -> List[Field]:
        return []

    # stage 2: analyze the loaded firmware (after static values are known)
    def prepare(self, fw: bytearray, ctx, static_values: dict) -> None:
        pass

    # stage 3: fields that depend on the analysis performed in prepare()
    # (e.g. one field per found sound prompt)
    def get_dynamic_fields(self, fw: bytearray, ctx, static_values: dict) -> List[Field]:
        return []

    # stage 4: actually patch the firmware and return it
    def run(self, fw: bytearray, values: dict, ctx) -> bytearray:
        raise NotImplementedError

    # optional: override the "does this need repacking" auto-detection
    def requires_repack_hint(self, firmware_path: str):
        return None  # None = let the core decide automatically