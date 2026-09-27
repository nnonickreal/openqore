# openqore module system

## introduction

starting with version `1.0.0`, `qorepatcher` has been organized into a modular system to make it easier to create customizers for different headphones, given their varying codebases.

it's divided into two types:
1. **JSON** modules — a simple module that replaces hex values in the binary file based on masks and displays buttons/toggles in the interface to control this. for an example, see how the module for the Nothing Headphones (1) works.
2. **python** modules — a complex python module designed, for example, to disassemble the firmware and patch large functions (such as changing sounds or headphone settings). for an example see how the module for the `bes2300` chipsets works.

patcher already gives the basic ARM thumb disassembler functions.

### writing a JSON module

JSON modules are lightweight declarative patch descriptions. they don't require writing python code and are best suited for byte replacements, toggling flags, tweaking volume tables, or adjusting numerical values.

#### file location

place your `.json` file in:
- `modules_json/` inside the `patcher/openqore/` directory, or
- `~/.openqore/modules_json/` in your user directory (create if it doesn't exist).

#### root structure

```json
{
  "name": "headphone audio tweaker",
  "chip": "bes1600 (2700YH)",
  "description": "adjusts prompt volume levels and tuning parameters",
  "requires_repack": "auto",
  "base_address_choices": [
    { "label": "without OTA boot (base 0x34020000)", "value": "0x34020000" },
    { "label": "with OTA boot (base 0x34000000)", "value": "0x34000000" }
  ],
  "patches": []
}
```

- `name`: module name displayed in the CLI / GUI interface.
- `chip`: target chipset (e.g. `bes1502p`, `bes1600`, `generic`).
- `description`: brief description of what the module does.
- `requires_repack`: `"auto"` (decompresses and repacks if lzma/packed firmware was detected), `true`, or `false`.
- `base_address_choices` / `base_address`: defines the flash memory mapping address. you can specify a single fixed `"base_address": "0x2c020000"` or a list of choices for the user.
- `patches`: an array of patch definitions.

#### supported patch types

each entry inside `patches` must have a `type` and an optional `field` describing the UI control.

##### 1. `choice_patch`
matches a byte pattern and replaces it with one of several hex variants based on the user's dropdown choice.

```json
{
  "name": "audio_prompt_state",
  "type": "choice_patch",
  "find_hex": "049B13F0FE0F0CBF0623052378E7",
  "find_mask": "FFFFFFFFFFFFFFFFFFFFFFFFFFFF",
  "occurrence": "first",
  "variants": {
    "0": "049B13F0FE0F0CBF0623002378E7",
    "5": "049B13F0FE0F0CBF0623052378E7"
  },
  "field": {
    "id": "prompt_state",
    "label": "Prompt Volume Level",
    "kind": "choice",
    "choices": [
      [0, "0x0 (Muted)"],
      [5, "0x5 (Stock)"]
    ],
    "default": 5,
    "help": "Modifies mov.ne r3, #imm"
  }
}
```

`choices` entries can be written either as `[value, label]` json arrays (as above) or as python tuples if you're building the model programmatically — both are normalized the same way internally, so pick whichever is more convenient.

##### 2. `bool_toggle`
switches between two byte sequences depending on a boolean toggle (true / false).

```json
{
  "name": "enable_high_gain",
  "type": "bool_toggle",
  "find_hex": "002001e0",
  "replace_hex_true": "012001e0",
  "replace_hex_false": "002001e0",
  "field": {
    "id": "high_gain",
    "label": "Enable High Gain Mode",
    "kind": "bool",
    "default": false
  }
}
```

##### 3. `hex_replace`
simple unconditional search-and-replace. doesn't require a `field`.

```json
{
  "name": "disable_crc_check",
  "type": "hex_replace",
  "find_hex": "002801d1",
  "find_mask": "ffffffff",
  "replace_hex": "002801e0",
  "occurrence": "first"
}
```
`occurrence` can be `"first"`, `"all"`, or a 0-based integer index.

##### 4. `int_field_patch`
locates a pattern, calculates `instr_offset` bytes forward to an ARM thumb-2 `movw`/`mov.w` instruction, and writes the user-specified integer (up to 16 bits) into its immediate field. the destination register of the instruction is **not** chosen by the user — it's read from the existing instruction at that offset and preserved as-is, only the immediate value gets replaced.

```json
{
  "name": "sample_rate_override",
  "type": "int_field_patch",
  "signature_hex": "4ff00000",
  "signature_mask": "ffff0000",
  "instr_offset": 8,
  "field": {
    "id": "target_rate",
    "label": "Sample Rate (Hz)",
    "kind": "int",
    "min": 8000,
    "max": 48000,
    "default": 32000
  }
}
```

> **note:** the instruction located at `signature_off + instr_offset` must actually be a valid `movw`/`mov.w`. if it isn't, the patch will fail for that entry - double check your `instr_offset` in a disassembler before shipping the model.

##### 5. `inject_data`
appends raw hex bytes to the end of the firmware image, pads it to `align` boundary, and automatically updates a 32-bit pointer literal and/or a `movw` size instruction near specified signatures.

```json
{
  "name": "inject_custom_blob",
  "type": "inject_data",
  "data_hex": "001122334455",
  "align": 4,
  "back_offset": 0,
  "pointer_signature_hex": "4800",
  "pointer_literal_offset": 4,
  "size_signature_hex": "f2400000",
  "size_instr_offset": 0
}
```

- `align`: byte alignment for the padded block (default `4`).
- `back_offset`: how many bytes to step back from the current end of the image before inserting data — useful if the last few bytes of the firmware are reserved for a CRC/signature block that must never be overwritten (default `0`, meaning "append at the very end").

---

### writing a py module

python modules are used when firmware modification requires dynamic analysis: parsing switch-tables (`tbh`/`tbb`), resolving literal pools, decoding disassembly instructions, downloading external tools (like ffmpeg), or generating binary payloads on the fly.

#### folder structure

python modules are placed in subfolders under:
- `modules_py/<module_folder>/` inside the openqore project, or
- `~/.openqore/modules_py/<module_folder>/`.

each module directory must have:
```text
modules_py/
└── my_sound_patcher/
    ├── manifest.json
    └── module.py
```

##### `manifest.json`
contains metadata used by the module loader:
```json
{
  "name": "CMF Headphone Pro Audio Dynamic Patcher",
  "chip": "bes1502p",
  "version": "1.0",
  "description": "dynamically replaces prompts and patches sample rate",
  "author": "nnonick"
}
```
`name`, `chip`, and `description` here override the ones declared inside `module.py` for display purposes. `version` and `author` are currently informational only (shown in the module list) and aren't used for any compatibility checks.

#### lifecycle of a python module

every module must define a class that inherits from `openqore.core.module_base.ModuleBase`. execution happens in five sequential stages:

```text
[1. get_static_fields]      -> user inputs static settings (base address, audio dir, ...)
        │
[2. prepare]                -> module parses FW (disassembles blocks, finds targets)
        │
[3. get_dynamic_fields]     -> module builds UI dynamically (e.g. one toggle per prompt)
        │
[4. run]                    -> module modifies FW bytearray and returns it
        │
[5. requires_repack_hint]   -> module optionally overrides the repack decision
```

1. **`get_static_fields(self, ctx) -> list[Field]`**
   declares fields that do not depend on firmware content (such as base address, replacement sound folder path, target sample rate).
2. **`prepare(self, fw: bytearray, ctx: HookContext, static_values: dict) -> None`**
   called after the user selects static parameters and the firmware is unpacked into memory. use this method to scan the binary, parse jump tables, and build internal target maps.
3. **`get_dynamic_fields(self, fw: bytearray, ctx: HookContext, static_values: dict) -> list[Field]`**
   generates UI fields based on what was discovered in `prepare()`. for instance, if 20 sound prompts were located, it can return 20 selector fields.
4. **`run(self, fw: bytearray, values: dict, ctx: HookContext) -> bytearray`**
   receives the combined values (`static_values` + `dynamic_values`), performs actual memory modifications, appends payloads to the firmware, updates jump/size instructions, and returns the modified `bytearray`.
5. **`requires_repack_hint(self, firmware_path: str)`** *(optional)*
   lets the module override whether the output should be repacked. return `True`/`False` to force a decision, or `None` (default) to fall back to `"auto"` — meaning the firmware gets repacked only if it was originally detected/marked as packed.

#### UI fields (`Field`)

import `Field` from `openqore.core.ui`:
```python
Field(
    id="target_sample_rate",
    label="target sample rate for prompts (Hz)",
    kind="int",          # "int", "float", "string", "hex", "bool", "choice", or "info"
    default=32000,
    min=8000,           # optional (int/float only)
    max=48000,          # optional (int/float only)
    choices=[(32000, "32 kHz"), (44100, "44.1 kHz")],  # required for "choice"
    help="sample rate passed to the sbc encoder"
)
```

field kinds:
- `"bool"` — yes/no toggle.
- `"int"` / `"float"` — numeric input, supports `min`/`max`/`default`.
- `"choice"` — list of options, each entry is `(value, label)` (python) or `[value, label]` (json).
- `"string"` — free text input. **`min`/`max` are intentionally not supported here** — this kind is meant for raw hex patches and other complex/free-form values that don't have a meaningful numeric range.
- `"hex"` — same as `"string"`, used purely as a semantic hint that the value is expected to be a hex string.
- `"info"` — no input at all, just renders the label as a section header / informational text. useful to visually separate groups of dynamic fields.

#### available openqore core utilities

##### 1. `ctx` (`HookContext`)
passed to `prepare` and `run`. provides addressing helpers and binary operations:
- `ctx.base_address`: current base address of flash rom (e.g. `0x2c020000`).
- `ctx.va_to_off(va)` / `ctx.off_to_va(off)`: converts virtual addresses to file offsets and vice versa.
- `ctx.read_u32(off)` / `ctx.write_u32(off, val)`: read/write little-endian 32-bit words.
- `ctx.read_bytes(off, length)` / `ctx.write_bytes(off, data)`: raw byte read/write.
- `ctx.find_signature(pattern, mask=None, start=0, end=None, find_all=False)`: signature search.
- `ctx.replace_signature(pattern, mask=None, replace=b"", occurrence="first")`: search-and-replace.
- `ctx.write_instruction(off, instr_bytes, comment="")`: writes instruction bytes with debug logging.
- `ctx.allocate_at_end(data, align=4, back_offset=0)`: appends bytes to the end of the firmware (optionally stepping back `back_offset` bytes first, e.g. to avoid overwriting a trailing CRC block), pads to alignment, and returns `(offset, va)`.
- `ctx.log(msg)`: unified logging to cli console or webview UI.
- `ctx.progress`: an optional progress callback slot, `callable(done, total, percent) | None`. it's set by the cli/gui frontend, not by your module — **don't call it directly**, just pass it along as `on_progress=ctx.progress` to functions like `downloader.download_file(...)`, which already handle it being `None` safely.

##### 2. `openqore.core.thumb2`
disassembly and instruction encoding tools for ARM thumb/thumb-2:

| instruction | pattern / mask constants | decode | encode |
|---|---|---|---|
| `movw rd, #imm16` (thumb-2, t3) | — | `decode_movw_thumb2(instr4) -> (rd, imm16)` | `encode_movw_thumb2(rd, imm16) -> bytes` |
| `lsr.w rd, rm, #1` | `LSR1_PATTERN`, `LSR1_MASK` | `decode_lsr1(fw, off) -> (rd, rm) \| None` | `encode_mov_w_noshift(rd, rm) -> bytes` (removes the shift) |
| `sub.w rd, rn, rm` | `SUBW_PATTERN`, `SUBW_MASK` | `decode_subw(fw, off) -> (rd, rn, rm) \| None` | — |
| `add.w rd, rn, rm, lsl #1` | `ADDW_LSL1_PATTERN`, `ADDW_LSL1_MASK` | `decode_addw_lsl1(fw, off) -> (rd, rn, rm) \| None` | `strip_addw_shift(fw, off)` (removes `lsl #1` in-place) |
| `lsrs rd, rm, #2` (thumb-1) | `LSRS2_PATTERN`, `LSRS2_MASK` | `decode_lsrs2(fw, off) -> (rd, rm) \| None` | `encode_mov_reg(rd, rm) -> bytes` |
| `bl` (thumb-2) | — | `is_bl_opcode(fw, off) -> bool`, `decode_bl_target_offset(fw, off) -> int \| None` | — |

general-purpose helpers:
- `match_masked(fw, off, pattern, mask)`: checks if bytes at `off` match a bitmask pattern.
- `find_masked_all(fw, pattern, mask, start, end, step=2)`: scans a region for all offsets matching a masked pattern — useful when you already have the pattern/mask constants above and want to scan the whole firmware instead of a single known offset.
- `find_bl_after(fw, start, max_search=40)`: finds the nearest `bl` instruction after a given offset, scanning up to `max_search` bytes forward.

##### 3. `openqore.core.downloader` & `archives`
generic, dependency-free helpers for downloading and extracting third-party binaries. every module is expected to store its own download links internally and just call these generic functions:

- `downloader.find_on_host(binary_name)`: checks if an executable already exists in the system `PATH` (via `shutil.which`).
- `downloader.download_file(url, dest_path, threads=8, on_progress=None, log=print)`: downloads a file, automatically using up to `threads` parallel HTTP range requests when the server supports them (falls back to a single stream otherwise). pass `on_progress=ctx.progress` to wire it into the cli/gui progress bar.
- `archives.extract_archive(archive_path, extract_dir)`: unpacks `.zip`/`.tar.gz`/`.tar.xz`/`.tar.bz2`/`.tar` archives.
- `archives.find_file_in_dir(root_dir, filename)`: recursively looks for a file by name inside an extracted archive.

##### 4. `openqore.core.paths`
resolves the patcher's per-user data directory (`~/.openqore/...`), mainly used to store downloaded tools so they aren't re-downloaded on every run:

- `paths.home_dir()`: `~/.openqore`.
- `paths.bin_dir(module_name)`: `~/.openqore/bin/<module_name>` — put downloaded binaries here, namespaced by your module/chip name.
- `paths.modules_json_dir()` / `paths.modules_py_dir()`: where user-installed modules live.
- `paths.cache_dir()`: `~/.openqore/cache`, for temporary/downloaded archives.

**typical pattern for a module that needs its own external tool**:

```python
import platform, shutil
from openqore.core import downloader, archives, paths

MY_TOOL_URLS = {
    "Windows": "https://example.com/mytool-win64.zip",
    "Linux":   "https://example.com/mytool-linux-x64.tar.gz",
}

def ensure_my_tool(chip_name: str, ctx, auto_download=True) -> str:
    found = downloader.find_on_host("mytool")
    if found:
        return found

    target_dir = paths.bin_dir(chip_name) / "mytool"
    exe = target_dir / ("mytool.exe" if platform.system() == "Windows" else "mytool")
    if exe.exists():
        return str(exe)

    if not auto_download:
        raise RuntimeError("mytool not found on this system and auto-download is disabled")

    url = MY_TOOL_URLS[platform.system()]
    archive = target_dir / url.split("/")[-1]
    downloader.download_file(url, archive, on_progress=ctx.progress, log=ctx.log)
    extracted = archives.extract_archive(archive, target_dir / "_extract")
    found_bin = archives.find_file_in_dir(extracted, exe.name)
    shutil.copy2(found_bin, exe)
    return str(exe)
```

#### minimal python module template

```python
from openqore.core.module_base import ModuleBase
from openqore.core.ui import Field
from openqore.core import thumb2

class MyCustomModule(ModuleBase):
    name = "example module"
    chip = "bes1337XD"
    version = "1.0"
    description = "my first amazing custom module!! crazy"
    author = "developer"

    def get_static_fields(self, ctx):
        return [
            Field(
                id="base_address",
                label="firmware base address",
                kind="choice",
                choices=[(0x2c020000, "base 0x2c020000"), (0x2c000000, "base 0x2c000000")],
                default=0x2c020000
            ),
            Field(id="gain_multiplier", label="gain value", kind="int", min=0, max=100, default=50)
        ]

    def prepare(self, fw: bytearray, ctx, static_values: dict):
        ctx.base_address = static_values["base_address"]
        ctx.log(f"[prepare] analyzing firmware at base 0x{ctx.base_address:x}")
        # perform binary analysis, jump table resolution, etc.
        self.patch_target_off = ctx.find_signature(b"\x4f\xf0\x00\x00")

    def get_dynamic_fields(self, fw: bytearray, ctx, static_values: dict):
        fields = []
        if self.patch_target_off is not None:
            fields.append(Field(id="apply_patch", label="apply gain patch", kind="bool", default=True))
        return fields

    def run(self, fw: bytearray, values: dict, ctx):
        if not values.get("apply_patch", False) or self.patch_target_off is None:
            ctx.log("[info] nothing to patch, skipping.")
            return fw

        gain = values.get("gain_multiplier", 50)
        # encode movw r0, #gain
        patch = thumb2.encode_movw_thumb2(0, gain)
        ctx.write_instruction(self.patch_target_off, patch, comment=f"set gain to {gain}")
        ctx.log("[success] firmware successfully patched.")
        return fw

    def requires_repack_hint(self, firmware_path: str):
        return None  # "auto" — repack only if the input firmware was packed
```