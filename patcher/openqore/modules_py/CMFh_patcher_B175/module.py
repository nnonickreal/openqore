import os
import platform
import shutil
import stat
import struct
import subprocess
from pathlib import Path

from openqore.core import thumb2, downloader, archives, paths
from openqore.core.module_base import ModuleBase
from openqore.core.ui import Field

ALIGN = 4
# Map of known case IDs to human-readable names for UI clarity

KNOWN_PROMPTS = {
    0:  "POWER ON",
    1:  "POWER OFF",
    13: "PAIRING",
    21: "INCOMING CALL",
    27: "CONNECTED",
    28: "DISCONNECT",
    37: "BT MUTE (keep original)",
    51: "ANC OFF",
    52: "ANC ON",
    53: "TRANSPARENCY ON",
    54: "LOW BATTERY",
    56: "FIND ME",
    57: "VOLUME DOWN",
    58: "VOLUME UP",
    59: "VOLUME DOWN MAX",
    60: "VOLUME UP MAX",
    61: "DOUBLE KEY",
    62: "TRIPLE KEY",
    63: "CONCERT MODE",
    64: "CINEMA MODE",
    65: "GAME MODE",
    66: "3D OFF",
    67: "BASS TUNING",
    68: "TREBLE TUNING",
    69: "MIC OFF",
    70: "MIC ON",
    71: "WARNING",
    # Aliases
    55: "UX_AUD_ID_DIRAC",
    6:  "NUM_3", 10: "NUM_7", 11: "NUM_8",
    30: "BT_ALEXA_START",
    4:  "NUM_1", 5: "NUM_2", 9: "NUM_6",
    17: "BT_CALL_REFUSE", 18: "BT_CALL_OVER",
    20: "BT_CALL_HUNG_UP",
    31: "FIND_MY_BUDS", 32: "TILE_FIND", 33: "BT_ALEXA_STOP",
    19: "BT_CALL_ANSWER",
    16: "BT_PAIRING_FAIL",
    3:  "NUM_0", 7: "NUM_4", 8: "NUM_5", 12: "NUM_9", 14: "BT_PAIRING", 29: "BT_WARNING",
    23: "BT_CHARGE_PLEASE", 24: "BT_CHARGE_FINISH",
    15: "BT_PAIRING_SUC",
}


def format_group_display(cases):
    primary = min(cases)
    primary_name = KNOWN_PROMPTS.get(primary, f"ID_{primary:02d}")
    aliases = sorted([c for c in cases if c != primary])
    if aliases:
        alias_names = [KNOWN_PROMPTS.get(c, f"ID_{c:02d}") for c in aliases]
        return f"{primary_name} [aliases: {', '.join(alias_names)}]"
    return primary_name


def read_u32_le(buf, off):
    return struct.unpack_from("<I", buf, off)[0]


def write_u32_le(buf, off, val):
    struct.pack_into("<I", buf, off, val)


def decode_size_instr(fw, off):
    h1, h2 = struct.unpack_from("<HH", fw, off)
    if (h1 & 0xFBF0) == 0xF240:
        i = (h1 >> 10) & 1
        imm4 = h1 & 0xF
        imm3 = (h2 >> 12) & 0x7
        rd = (h2 >> 8) & 0xF
        imm8 = h2 & 0xFF
        imm16 = (imm4 << 12) | (i << 11) | (imm3 << 8) | imm8
        return rd, imm16
    elif (h1 & 0xFBEF) == 0xF04F:
        rd = (h2 >> 8) & 0xF
        return rd, 0
    raise ValueError(f"unrecognized size instruction at file offset 0x{off:x}")


def is_thumb32(h1):
    """True if this halfword starts a 32-bit Thumb-2 instruction."""
    return (h1 & 0xE000) == 0xE000 and (h1 & 0x1800) != 0x0000


def is_block_terminator(h1, wide, h2=None):
    """
    Detects instructions that end a case-handler's linear flow:
      - 16-bit unconditional B (T2)
      - 32-bit unconditional B.W (T4)
      - BL / BL.W (function call, nothing useful follows in these handlers)
    Conditional branches (e.g. BNE.W to the error path) are NOT terminators,
    because execution falls through to the size/pointer setup on the "not taken" path.
    """
    if not wide:
        return (h1 & 0xF800) == 0xE000  # unconditional B (T2)
    if (h1 & 0xF800) != 0xF000:
        return False
    # bits 15,14,12 of h2: B.W unconditional -> 0x9000, BL/BLX -> 0xD000
    tag = h2 & 0xD000
    return tag in (0x9000, 0xD000)


def analyze_prompt_block(fw, start_off, base_address):
    """
    Scans a single case-handler starting at start_off, looking for:
      - a literal pool pointer to the audio blob (ldr rX,[pc,#imm] -> ROM address)
      - an explicit size-setting instruction (movw / mov.w)
    Stops as soon as it reaches the end of *this* handler (unconditional branch
    or call), so it can never accidentally read instructions that belong to the
    next case in the switch table.
    """
    pc = start_off
    found_target = None
    found_ptr = None
    found_size = None

    for _ in range(30):
        if pc >= len(fw) - 4:
            break

        h1 = struct.unpack_from("<H", fw, pc)[0]
        wide = is_thumb32(h1)
        h2 = struct.unpack_from("<H", fw, pc + 2)[0] if wide else None

        # ldr rX, [pc, #imm]  (16-bit literal load)
        if not wide and (h1 & 0xf800) == 0x4800:
            imm8 = h1 & 0xff
            va_instr = base_address + pc
            pc_align = (va_instr + 4) & ~3
            lit_va = pc_align + (imm8 << 2)
            lit_off = lit_va - base_address
            if 0 <= lit_off <= len(fw) - 4:
                val = read_u32_le(fw, lit_off)
                # Ensure it points to flash ROM
                if base_address + 0x10000 <= val < base_address + len(fw) and found_ptr is None:
                    found_target = val
                    found_ptr = lit_va

        # movw rX, #imm  (F240 encoding)
        if wide and (h1 & 0xfbf0) == 0xf240:
            try:
                _rd, imm = thumb2.decode_movw_thumb2(fw[pc:pc + 4])
                if imm > 0x100 and found_size is None:
                    found_size = base_address + pc
            except ValueError:
                pass
        # mov.w rX, #0  (F04F encoding)
        elif wide and (h1 & 0xfbef) == 0xf04f and found_size is None:
            found_size = base_address + pc

        # FIX: stop before we bleed into the next case's machine code.
        if is_block_terminator(h1, wide, h2):
            break

        pc += 4 if wide else 2

        if found_ptr is not None and found_size is not None:
            return found_target, found_ptr, found_size

    return found_target, found_ptr, found_size


def generate_patch_map(fw, base_address, log):
    best_tbh_offset = 0
    max_unique_targets = 0
    best_groups = {}

    for i in range(0, len(fw) - 4, 2):
        if fw[i] == 0xdf and fw[i + 1] == 0xe8:
            op2 = fw[i + 2]
            if (op2 & 0xf0) in (0x00, 0x10) and fw[i + 3] == 0xf0:
                is_tbh = (op2 & 0xf0) == 0x10
                rm = op2 & 0x0f
                max_case = 0
                pc = i - 2
                while pc >= max(0, i - 60):
                    if 0x28 <= fw[pc + 1] <= 0x2f and (fw[pc + 1] - 0x28) == rm:
                        max_case = fw[pc]
                        break
                    pc -= 2
                if max_case < 10 or max_case > 250:
                    continue

                table_start = i + 4
                tbh_pc = i + 4
                num_cases = max_case + 1
                if table_start + (num_cases * (2 if is_tbh else 1)) > len(fw):
                    continue

                current_groups = {}
                for case_idx in range(num_cases):
                    offset = (struct.unpack_from("<H", fw, table_start + case_idx * 2)[0] * 2
                              if is_tbh else fw[table_start + case_idx] * 2)
                    target_file_off = tbh_pc + offset
                    if not (0 <= target_file_off < len(fw)):
                        continue

                    target, ptr, size = analyze_prompt_block(fw, target_file_off, base_address)
                    if target is not None:
                        if target not in current_groups:
                            current_groups[target] = {"cases": set(), "ptrs": set(), "size_instrs": set()}
                        current_groups[target]["cases"].add(case_idx)
                        current_groups[target]["ptrs"].add(ptr)
                        if size is not None:
                            current_groups[target]["size_instrs"].add(size)

                # FIX: a single "size" instruction address must belong to exactly
                # one target. If two different targets both claim the same
                # instruction address, our block analysis walked across a case
                # boundary somewhere (or the layout is genuinely ambiguous) --
                # in either case it is NOT safe to patch that instruction, so we
                # strip it from every group that claims it instead of silently
                # letting one group's patch clobber another's.
                size_owner = {}
                ambiguous = set()
                for tgt, data in current_groups.items():
                    for s in data["size_instrs"]:
                        if s in size_owner and size_owner[s] != tgt:
                            ambiguous.add(s)
                        else:
                            size_owner[s] = tgt

                if ambiguous:
                    log(f"[debug] switch@0x{i:x}: dropping {len(ambiguous)} ambiguous "
                        f"size-instruction(s) shared by multiple targets: "
                        + ", ".join(f"0x{a:x}" for a in sorted(ambiguous)))

                # Filter valid groups (must have at least one explicit,
                # unambiguously-owned size instruction)
                valid_groups = {}
                for tgt, data in current_groups.items():
                    clean_sizes = sorted(s for s in data["size_instrs"] if s not in ambiguous)
                    if clean_sizes:
                        valid_groups[tgt] = {
                            "cases": sorted(data["cases"]),
                            "ptrs": sorted(data["ptrs"]),
                            "size_instrs": clean_sizes,
                        }

                unique_targets = len(valid_groups)
                if unique_targets > max_unique_targets:
                    max_unique_targets = unique_targets
                    best_groups = valid_groups
                    best_tbh_offset = i

    if max_unique_targets > 0:
        log(f"[debug] found switch at 0x{best_tbh_offset:x} with {max_unique_targets} unique audio blobs.")

    return best_groups, best_tbh_offset


def find_sample_rate_candidates(fw, base_address, anchor_va, forbidden_offsets=frozenset()):
    candidates = []
    fw_len = len(fw)
    prompt_str_pool_offs = set()
    string_keys = [
        b"[%s]: sample rate:",
        b"sample rate: %d",
        b"app_play_audio_onoff",
        b"Audio prompt stream state",
    ]
    for s_key in string_keys:
        pos = 0
        while True:
            idx = fw.find(s_key, pos)
            if idx == -1:
                break
            str_va = base_address + idx
            str_va_bytes = struct.pack("<I", str_va)
            p_pos = 0
            while True:
                p_idx = fw.find(str_va_bytes, p_pos)
                if p_idx == -1:
                    break
                prompt_str_pool_offs.add(p_idx)
                p_pos = p_idx + 4
            pos = idx + len(s_key)

    for off in range(0, max(0, fw_len - 12), 2):
        # FIX: never treat an instruction that we already use as a per-case
        # "size" instruction as a candidate for the global sample-rate patch.
        if off in forbidden_offsets:
            continue

        va = base_address + off
        h1 = struct.unpack_from("<H", fw, off)[0]
        is_orig = False
        is_patched = False
        rd = -1

        if (h1 & 0xF800) == 0x4800:
            cand_rd = (h1 >> 8) & 0x7
            h2 = struct.unpack_from("<H", fw, off + 2)[0]
            if h2 == (0x6800 | (cand_rd << 3) | cand_rd):
                is_orig = True
                rd = cand_rd
        elif (h1 & 0xFBF0) == 0xF240:
            h2 = struct.unpack_from("<H", fw, off + 2)[0]
            cand_rd = (h2 >> 8) & 0xF
            if cand_rd < 8:
                is_patched = True
                rd = cand_rd

        if not (is_orig or is_patched):
            continue

        score = 0
        h3 = struct.unpack_from("<H", fw, off + 4)[0]
        has_str_sp = ((h3 & 0xF800) == 0x9000 and ((h3 >> 8) & 0x7) == rd)
        if has_str_sp:
            score += 50
            if off + 8 < fw_len:
                h4 = struct.unpack_from("<H", fw, off + 6)[0]
                h5 = struct.unpack_from("<H", fw, off + 8)[0]
                if (h4 & 0xF800) == 0x4800:
                    rd2 = (h4 >> 8) & 0x7
                    if (h5 & 0xF800) == 0x9000 and ((h5 >> 8) & 0x7) == rd2:
                        score += 50

        if rd == 3:
            score += 20

        for pool_off in prompt_str_pool_offs:
            dist = pool_off - off
            if 0 < dist < 0x300:
                score += 200
                break

        # FIX: anchor_va must be a virtual address, not a raw file offset,
        # otherwise this distance heuristic is meaningless.
        delta = va - anchor_va
        if 0 < delta < 0x2000:
            score += 40
            score += max(0, 30 - int(abs(delta - 0x990) / 64))
        elif delta < 0:
            score -= 50

        if score > 60:
            candidates.append((score, off, rd, is_patched))

    candidates.sort(key=lambda c: c[0], reverse=True)
    return candidates


def patch_prompt_sample_rate_dynamic(fw, ctx, target_rate, anchor_va, forbidden_offsets, log):
    candidates = find_sample_rate_candidates(fw, ctx.base_address, anchor_va, forbidden_offsets)
    if not candidates:
        log("[warning] could not find app_play_audio_onoff sample rate instruction.")
        return -1

    best_score, match_off, rd, is_patched = candidates[0]
    va = ctx.base_address + match_off

    if is_patched:
        log(f"[info] sample rate instruction at 0x{va:x} was already patched (score={best_score}).")
    else:
        log(f"[info] located app_play_audio_onoff sample rate dereference at 0x{va:x} (score={best_score}).")

    fw[match_off:match_off + 4] = thumb2.encode_movw_thumb2(rd, target_rate & 0xFFFF)
    log(f"[patch] sample rate hardcoded at 0x{va:x} "
        f"(r{rd} <- {target_rate} Hz, RAM lookup removed).")
    return match_off


def run_cmd(cmd):
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        raise RuntimeError(f"binary not found: {cmd[0]}")
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", errors="replace").strip())
    return p.stdout


def encode_wav_to_sbc(ffmpeg_bin, input_path, sample_rate):
    cmd = [ffmpeg_bin, "-y", "-v", "error", "-i", str(input_path),
           "-ar", str(sample_rate), "-ac", "1", "-b:a", "180k", "-f", "sbc", "-"]
    data = run_cmd(cmd)
    if not data:
        raise RuntimeError("ffmpeg returned empty data")
    return data


FFMPEG_URLS = {
    "Windows": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    "Linux":   "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
}


def ensure_ffmpeg(module_name: str, auto_download: bool = True, on_progress=None, log=print) -> str:
    found = downloader.find_on_host("ffmpeg")
    if found:
        log(f"[ffmpeg] found on host: {found}")
        return found

    target_dir = paths.bin_dir(module_name) / "ffmpeg"
    exe_name = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
    existing = target_dir / exe_name
    if existing.exists():
        log(f"[ffmpeg] using previously downloaded copy: {existing}")
        return str(existing)

    if not auto_download:
        raise RuntimeError(
            "ffmpeg not found on this system and automatic download is disabled "
            "(enable 'auto_download_ffmpeg' or install ffmpeg manually and add it to PATH)."
        )

    system = platform.system()
    url = FFMPEG_URLS.get(system)
    if not url:
        raise RuntimeError(f"no known ffmpeg build url for '{system}'; install ffmpeg manually.")

    archive_path = target_dir / url.split("/")[-1]
    downloader.download_file(url, archive_path, on_progress=on_progress, log=log)

    log("[ffmpeg] extracting...")
    extract_tmp = target_dir / "_extract"
    archives.extract_archive(archive_path, extract_tmp)

    found_bin = archives.find_file_in_dir(extract_tmp, exe_name)
    if not found_bin:
        raise RuntimeError("could not locate ffmpeg binary inside the downloaded archive.")

    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(found_bin, existing)
    if system != "Windows":
        st = os.stat(existing)
        os.chmod(existing, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    shutil.rmtree(extract_tmp, ignore_errors=True)
    archive_path.unlink(missing_ok=True)
    log(f"[ffmpeg] installed to {existing}")
    return str(existing)


class BesGenericModule(ModuleBase):
    name = "CMF Headphone Pro Audio Dynamic Patcher"
    chip = "bes1502p"
    version = "1.0"
    description = "dynamic prompt mapper and sample rate patcher"
    author = "nnonick"

    def __init__(self):
        super().__init__()
        self.patch_map = {}
        self.tbh_offset = 0  # file offset of the switch table (NOT a VA)

    def get_static_fields(self, ctx):
        return [
            Field(id="base_address", label="firmware base address", kind="choice",
                  choices=[(0x2c020000, "without OTA boot (base 0x2c020000)"),
                           (0x2c000000, "with OTA boot (base 0x2c000000)")],
                  default=0x2c020000),
            Field(id="sounds_dir", label="folder with replacement WAV files", kind="string", default="sounds_src"),
            Field(id="target_sample_rate", label="target sample rate for prompts (Hz)", kind="int",
                  min=8000, max=48000, default=32000),
            Field(id="auto_download_ffmpeg",
                  label="automatically download ffmpeg if not found on this system",
                  kind="bool", default=True),
        ]

    def prepare(self, fw, ctx, static_values):
        ctx.base_address = static_values["base_address"]
        ctx.log(f"[info] Scanning firmware dynamically (base=0x{ctx.base_address:x})...")
        self.patch_map, self.tbh_offset = generate_patch_map(fw, ctx.base_address, ctx.log)

        if not self.patch_map:
            ctx.log("[error] Could not dynamically map prompt blocks in the firmware.")

    def get_dynamic_fields(self, fw, ctx, static_values):
        fields = []
        sounds_dir = static_values.get("sounds_dir", "sounds_src")

        sorted_targets = sorted(self.patch_map.keys(), key=lambda t: min(self.patch_map[t]["cases"]))

        for tgt in sorted_targets:
            data = self.patch_map[tgt]
            primary_case = min(data["cases"])
            wav_name = f"ID_{primary_case:02d}.wav"
            has_file = (Path(sounds_dir) / wav_name).exists()

            label = f"{wav_name} = {format_group_display(data['cases'])}"
            if has_file:
                label += " (source file found)"
            else:
                label += " (no source file)"

            fields.append(Field(
                id=f"sound::{tgt}",
                label=label,
                kind="choice",
                choices=[("keep", "keep original"),
                         ("replace", "replace with file from sounds_dir"),
                         ("silence", "mute (firmware size = 0)")],
                default="replace" if has_file else "keep",
            ))
        return fields

    def run(self, fw, values, ctx):
        if not self.patch_map:
            ctx.log("[error] Nothing to patch, aborting.")
            return fw

        base_address = ctx.base_address
        sounds_dir = values.get("sounds_dir", "sounds_src")
        target_rate = values.get("target_sample_rate", 32000)

        needs_ffmpeg = any(values.get(f"sound::{tgt}") == "replace" for tgt in self.patch_map)
        ffmpeg_bin = None
        if needs_ffmpeg:
            ffmpeg_bin = ensure_ffmpeg(
                self.chip,
                auto_download=values.get("auto_download_ffmpeg", True),
                on_progress=ctx.progress,
                log=ctx.log,
            )

        cur = max(0, len(fw) - 0)
        ctx.log(f"Append offset: 0x{cur:x} (va=0x{base_address + cur:x})")

        patched = 0
        sorted_targets = sorted(self.patch_map.keys(), key=lambda t: min(self.patch_map[t]["cases"]))

        for tgt in sorted_targets:
            data = self.patch_map[tgt]
            primary_case = min(data["cases"])
            wav_name = f"ID_{primary_case:02d}.wav"
            action = values.get(f"sound::{tgt}", "keep")

            if action == "keep":
                continue

            ctx.log(f"\n=== {wav_name} : {format_group_display(data['cases'])} ({action}) ===")

            if action == "silence":
                for size_va in data["size_instrs"]:
                    size_off = ctx.va_to_off(size_va)
                    rd, _ = decode_size_instr(fw, size_off)
                    fw[size_off:size_off + 4] = thumb2.encode_movw_thumb2(rd, 0)
                    ctx.log(f"[patch] Size forced to 0 at 0x{size_off:x} (muted)")
                patched += 1
                continue

            wav_path = Path(sounds_dir) / wav_name
            if not wav_path.exists():
                ctx.log(f"[warning] {wav_name}: source file not found in '{sounds_dir}', skipping.")
                continue

            # Используем моно (ffmpeg сам подберёт Bitpool ~31-53)
            sbc = encode_wav_to_sbc(ffmpeg_bin, wav_path, target_rate)
            if len(sbc) > 0xFFFF:
                ctx.log(f"[error] {wav_name}: SBC size 0x{len(sbc):x} > 0xffff, skipping.")
                continue

            end = cur + len(sbc)
            fw[cur:end] = sbc
            new_va = base_address + cur
            ctx.log(f"Write: file_off=0x{cur:x}..0x{end:x} (size={len(sbc)})")

            # Переписываем все указатели (aliases) на новый файл
            for ptr_va in data["ptrs"]:
                ptr_off = ctx.va_to_off(ptr_va)
                old_ptr = read_u32_le(fw, ptr_off)
                write_u32_le(fw, ptr_off, new_va)
                ctx.log(f"Ptr patch: pool@0x{ptr_va:x} {old_ptr:#010x} -> {new_va:#010x}")

            # Обновляем все инструкции инициализации размера
            for size_va in data["size_instrs"]:
                size_off = ctx.va_to_off(size_va)
                rd, old_size = decode_size_instr(fw, size_off)
                fw[size_off:size_off + 4] = thumb2.encode_movw_thumb2(rd, len(sbc))
                ctx.log(f"Size patch: instr@0x{size_off:x} 0x{old_size:x} -> 0x{len(sbc):x}")

            cur = end
            pad = (ALIGN - (cur % ALIGN)) % ALIGN
            if pad:
                fw[cur:cur + pad] = b"\x00" * pad
                cur += pad
            patched += 1

        ctx.log(f"\n[info] Patched {patched} prompt group(s). Firmware size is now {len(fw)} bytes.")

        ctx.log("\n=== Sample Rate ===")
        # FIX: anchor must be a virtual address (tbh_offset was a raw file offset).
        anchor_va = base_address + self.tbh_offset

        # FIX: never let the sample-rate scanner touch instructions that are
        # already owned by per-case size patches (this used to be the source
        # of "phantom" size patches like 0x800 -> 0x7d00).
        forbidden_offsets = set()
        for data in self.patch_map.values():
            for size_va in data["size_instrs"]:
                forbidden_offsets.add(ctx.va_to_off(size_va))

        patch_prompt_sample_rate_dynamic(fw, ctx, target_rate, anchor_va, forbidden_offsets, ctx.log)

        return fw