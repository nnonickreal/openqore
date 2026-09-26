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

STEREO_SEARCH_BACK = 256
STEREO_SEARCH_FWD = 16384
ALIGN = 4
INJECT_BACK_OFFSET = 0

SR_PATTERN = bytes([0x4F, 0xF4, 0x7A, 0x50])   # mov.w rX, #16000 (modified-immediate)
SR_MASK    = bytes([0xFF, 0xFF, 0xFF, 0xF0])


def read_u32_le(buf, off):
    return struct.unpack_from("<I", buf, off)[0]


def write_u32_le(buf, off, val):
    struct.pack_into("<I", buf, off, val)


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
           "-ar", str(sample_rate), "-ac", "2", "-b:a", "258k", "-f", "sbc", "-"]
    data = run_cmd(cmd)
    if not data:
        raise RuntimeError("ffmpeg returned empty data")
    return data


def analyze_prompt_block(fw, start_off, base_address):
    pc = start_off
    found_ptr = None
    found_size = None
    for _ in range(30):
        if pc >= len(fw) - 4:
            break
        instr16 = struct.unpack_from("<H", fw, pc)[0]

        if (instr16 & 0xf800) == 0x4800:
            imm8 = instr16 & 0xff
            va_instr = base_address + pc
            pc_align = (va_instr + 4) & ~3
            lit_va = pc_align + (imm8 << 2)
            lit_off = lit_va - base_address
            if 0 <= lit_off <= len(fw) - 4:
                val = read_u32_le(fw, lit_off)
                if base_address + 0x10000 <= val < base_address + len(fw) and found_ptr is None:
                    found_ptr = lit_va

        if (instr16 & 0xfbf0) == 0xf240:
            try:
                _rd, imm = thumb2.decode_movw_thumb2(fw[pc:pc + 4])
                if imm > 0x100 and found_size is None:
                    found_size = base_address + pc
            except ValueError:
                pass
        elif (instr16 & 0xfbef) == 0xf04f and found_size is None:
            found_size = base_address + pc

        pc += 4 if ((instr16 & 0xe000) == 0xe000 and (instr16 & 0x1800) != 0x0000) else 2

        if found_ptr is not None and found_size is not None:
            return found_ptr, found_size
    return found_ptr, found_size


def generate_patch_map(fw, base_address, log):
    best_map, best_unique_ptrs, best_tbh_offset = {}, 0, 0

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

                current_map = {}
                for case_idx in range(num_cases):
                    offset = (struct.unpack_from("<H", fw, table_start + case_idx * 2)[0] * 2
                              if is_tbh else fw[table_start + case_idx] * 2)
                    target_file_off = tbh_pc + offset
                    if not (0 <= target_file_off < len(fw)):
                        continue
                    ptr, size = analyze_prompt_block(fw, target_file_off, base_address)
                    if ptr is not None and size is not None:
                        current_map[f"ID_{case_idx:02d}.wav"] = {"ptr_pool_addr": ptr, "size_instr_addr": size}

                unique_ptrs = len(set(x["ptr_pool_addr"] for x in current_map.values()))
                if unique_ptrs > 0:
                    log(f"[debug] found switch at 0x{i:x} with {unique_ptrs} valid audio cases.")
                if unique_ptrs > best_unique_ptrs:
                    best_unique_ptrs, best_map, best_tbh_offset = unique_ptrs, current_map, i

    return best_map, best_tbh_offset


def patch_prompt_sample_rate_dynamic(fw, tbh_offset, target_rate, log):
    matches = thumb2.find_masked_all(fw, SR_PATTERN, SR_MASK, 0, len(fw))
    if not matches:
        log("[warning] could not find sample rate pattern.")
        return -1
    match_off = matches[0] if len(matches) == 1 else min(matches, key=lambda x: abs(x - tbh_offset))
    if len(matches) > 1:
        log(f"[debug] {len(matches)} sample-rate candidates, picked closest to switch (0x{match_off:x}).")
    rd = fw[match_off + 3] & 0x0F
    fw[match_off:match_off + 4] = thumb2.encode_movw_thumb2(rd, target_rate & 0xFFFF)
    log(f"[patch] sample rate patched at 0x{match_off:x} (r{rd} -> {target_rate}).")
    return match_off


def find_stereo_chain(fw, tbh_offset):
    search_start = max(0, tbh_offset - STEREO_SEARCH_BACK)
    search_end = min(len(fw), tbh_offset + STEREO_SEARCH_FWD)
    candidates = thumb2.find_masked_all(fw, thumb2.LSR1_PATTERN, thumb2.LSR1_MASK, search_start, search_end)
    if not candidates:
        candidates = thumb2.find_masked_all(fw, thumb2.LSR1_PATTERN, thumb2.LSR1_MASK, 0, len(fw))

    for pos1 in candidates:
        decoded = thumb2.decode_lsr1(fw, pos1)
        if decoded is None:
            continue
        half_reg, len_reg = decoded

        sub_hits = []
        off, end2 = pos1, min(pos1 + 2048, len(fw) - 4)
        while off < end2:
            d = thumb2.decode_subw(fw, off)
            if d is not None and d[1] == half_reg:
                sub_hits.append((off, d[0], d[2]))
            off += 2

        add_hit = None
        for pos2, _sub_rd, cnt_reg in sub_hits:
            off, end3 = pos2, min(pos2 + 64, len(fw) - 4)
            while off < end3:
                d = thumb2.decode_addw_lsl1(fw, off)
                if d is not None and d[2] == cnt_reg:
                    add_hit = off
                    break
                off += 2
            if add_hit is not None:
                break
        if add_hit is None:
            continue

        lsrs_hit = None
        off, end4 = pos1, min(pos1 + 2048, len(fw) - 2)
        while off < end4:
            d = thumb2.decode_lsrs2(fw, off)
            if d is not None and d[1] == len_reg:
                lsrs_hit = (off, d[0])
                break
            off += 2
        if lsrs_hit is None:
            continue

        pos4, _mixer_len_reg = lsrs_hit
        bl_off = thumb2.find_bl_after(fw, pos4 + 2, max_search=24)
        if bl_off is None:
            continue
        mixer_target = thumb2.decode_bl_target_offset(fw, bl_off)
        if mixer_target is None or mixer_target < 0 or mixer_target + 14 > len(fw):
            continue

        return {"pos1": pos1, "half_reg": half_reg, "len_reg": len_reg,
                "pos_add": add_hit, "pos_lsrs": pos4, "mixer_target": mixer_target}
    return None


def apply_stereo_patches(fw, tbh_offset, sr_offset, log):
    log("\n=== stereo patches (dynamic structure search) ===")
    chain = find_stereo_chain(fw, tbh_offset)
    if chain is None:
        log("[warning] could not dynamically find the mono/stereo mixer structure.")
    else:
        pos1 = chain["pos1"]
        fw[pos1:pos1 + 4] = thumb2.encode_mov_w_noshift(chain["half_reg"], chain["len_reg"])
        log(f"[patch] 1. len/2 division disabled (0x{pos1:x})")

        thumb2.strip_addw_shift(fw, chain["pos_add"])
        log(f"[patch] 2. offset*2 multiplication disabled (0x{chain['pos_add']:x})")

        pos4 = chain["pos_lsrs"]
        d = thumb2.decode_lsrs2(fw, pos4)
        if d is not None:
            rd, rm = d
            fw[pos4:pos4 + 2] = thumb2.encode_mov_reg(rd, rm)
            log(f"[patch] 3. length division for mixer disabled (0x{pos4:x})")

        mixer_off = chain["mixer_target"]
        memcpy_payload = b'\x00\x2a\x03\xd0\x01\x3a\x8b\x5c\x83\x54\xf9\xe7\x70\x47'
        fw[mixer_off:mixer_off + len(memcpy_payload)] = memcpy_payload
        log(f"[patch] 4. mixer function replaced with direct stereo copy (0x{mixer_off:x})")

    if sr_offset != -1:
        lo, hi = max(0, sr_offset - 256), min(len(fw), sr_offset + 256)
        found_cache = None
        off = lo
        while off < hi - 4:
            if fw[off] == 0x4F and fw[off + 1] == 0xF4 and fw[off + 2] == 0x80 and (fw[off + 3] & 0xF0) == 0x60:
                found_cache = off
                break
            off += 2
        if found_cache is not None:
            reg_byte = fw[found_cache + 3]
            fw[found_cache:found_cache + 4] = bytes([0x4F, 0xF4, 0x00, reg_byte])
            log(f"[patch] 5. cache buffer size expanded to 2048 bytes (0x{found_cache:x})")
        else:
            log("[warning] could not find the cache size instruction near the sample rate.")
    else:
        log("[warning] skipping cache patch because sample rate was not found.")


def sort_key(name):
    try:
        return int(Path(name).stem.split("_")[1])
    except Exception:
        return 10 ** 9


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
    name = "bes2300 universal sound prompt patcher"
    chip = "bes2300"
    version = "1.1"
    description = "sound prompt replacement, sample rate & mono->stereo patches."
    author = "nnonick"

    def __init__(self):
        super().__init__()
        self.patch_map = {}
        self.tbh_offset = 0

    def get_static_fields(self, ctx):
        return [
            Field(id="base_address", label="firmware base address", kind="choice",
                  choices=[(0x3c018000, "without OTA boot (base 0x3c018000)"),
                           (0x3c000000, "with OTA boot (base 0x3c000000)")],
                  default=0x3c018000),
            Field(id="sounds_dir", label="folder with replacement WAV files", kind="string", default="sounds_src"),
            Field(id="apply_stereo", label="apply mono -> stereo mixer patch", kind="bool", default=True),
            Field(id="target_sample_rate", label="target sample rate for prompts", kind="choice",
                  choices=[(16000, "16000 Hz"),
                           (32000, "32000 Hz"),
                           (48000, "48000 Hz")],
                  default=48000),
            Field(id="auto_download_ffmpeg",
                  label="automatically download ffmpeg if not found on this system",
                  kind="bool", default=True),
        ]

    def prepare(self, fw, ctx, static_values):
        ctx.base_address = static_values["base_address"]
        ctx.log(f"[info] scanning firmware for the sound_manager switch (base=0x{ctx.base_address:x})...")
        self.patch_map, self.tbh_offset = generate_patch_map(fw, ctx.base_address, ctx.log)
        if self.patch_map:
            ctx.log(f"[info] found switch at 0x{self.tbh_offset:x} with {len(self.patch_map)} prompt slot(s).")
        else:
            ctx.log("[error] could not dynamically find prompt blocks in the firmware.")

    def get_dynamic_fields(self, fw, ctx, static_values):
        fields = []
        sounds_dir = static_values.get("sounds_dir", "sounds_src")
        for fn in sorted(self.patch_map.keys(), key=sort_key):
            has_file = (Path(sounds_dir) / fn).exists()
            fields.append(Field(
                id=f"sound::{fn}",
                label=f"{fn}" + (" (source file found)" if has_file else " (no source file)"),
                kind="choice",
                choices=[("keep", "keep original"),
                         ("replace", "replace with file from sounds_dir"),
                         ("silence", "mute (firmware size = 0)")],
                default="replace" if has_file else "silence",
            ))
        return fields

    def run(self, fw, values, ctx):
        if not self.patch_map:
            ctx.log("[error] nothing to patch, aborting.")
            return fw

        base_address = ctx.base_address
        sounds_dir = values.get("sounds_dir", "sounds_src")
        target_rate = int(values.get("target_sample_rate", 48000))
        apply_stereo = values.get("apply_stereo", True)

        needs_ffmpeg = any(values.get(f"sound::{fn}") == "replace" for fn in self.patch_map)
        ffmpeg_bin = None
        if needs_ffmpeg:
            ffmpeg_bin = ensure_ffmpeg(
                self.chip,
                auto_download=values.get("auto_download_ffmpeg", True),
                on_progress=ctx.progress,   # wired to CLI progress-bar or GUI progress bar
                log=ctx.log,
            )

        cur = max(0, len(fw) - 0)
        ctx.log(f"append offset: 0x{cur:x} (va=0x{base_address + cur:x})")

        seen_ptrs, patched = set(), 0

        for fn in sorted(self.patch_map.keys(), key=sort_key):
            action = values.get(f"sound::{fn}", "keep")
            entry = self.patch_map[fn]
            ptr_pool_va = entry["ptr_pool_addr"]

            if action == "keep":
                continue
            if ptr_pool_va in seen_ptrs:
                ctx.log(f"\n[skip] {fn}: shares the same handler as an already-patched prompt.")
                continue

            ctx.log(f"\n=== {fn} ({action}) ===")

            if action == "silence":
                size_off = ctx.va_to_off(entry["size_instr_addr"])
                old_instr = bytes(fw[size_off:size_off + 4])
                try:
                    rd, _ = thumb2.decode_movw_thumb2(old_instr)
                except ValueError:
                    hw1, hw2 = struct.unpack("<HH", old_instr)
                    rd = (hw2 >> 8) & 0xf if (hw1 & 0xfbef) == 0xf04f else 0
                fw[size_off:size_off + 4] = thumb2.encode_movw_thumb2(rd, 0)
                ctx.log(f"[patch] size forced to 0 at 0x{size_off:x} (muted)")
                seen_ptrs.add(ptr_pool_va)
                patched += 1
                continue

            wav_path = Path(sounds_dir) / fn
            if not wav_path.exists():
                ctx.log(f"[warning] {fn}: source file not found in '{sounds_dir}', skipping.")
                continue

            seen_ptrs.add(ptr_pool_va)
            sbc = encode_wav_to_sbc(ffmpeg_bin, wav_path, target_rate)
            if len(sbc) > 0xFFFF:
                ctx.log(f"[error] {fn}: sbc size 0x{len(sbc):x} > 0xffff, skipping.")
                continue

            end = cur + len(sbc)
            fw[cur:end] = sbc
            new_va = base_address + cur
            ctx.log(f"write: file_off=0x{cur:x}..0x{end:x} (size={len(sbc)})")

            ptr_off = ctx.va_to_off(ptr_pool_va)
            old_ptr = read_u32_le(fw, ptr_off)
            write_u32_le(fw, ptr_off, new_va)
            ctx.log(f"ptr patch: 0x{ptr_pool_va:x} {old_ptr:#010x} -> {new_va:#010x}")

            size_off = ctx.va_to_off(entry["size_instr_addr"])
            old_instr = bytes(fw[size_off:size_off + 4])
            try:
                rd, _ = thumb2.decode_movw_thumb2(old_instr)
            except ValueError:
                hw1, hw2 = struct.unpack("<HH", old_instr)
                rd = (hw2 >> 8) & 0xf if (hw1 & 0xfbef) == 0xf04f else 0
            fw[size_off:size_off + 4] = thumb2.encode_movw_thumb2(rd, len(sbc))
            ctx.log(f"size patch: 0x{size_off:x} -> 0x{len(sbc):x}")

            cur = end
            pad = (ALIGN - (cur % ALIGN)) % ALIGN
            if pad:
                fw[cur:cur + pad] = b"\x00" * pad
                cur += pad
            patched += 1

        ctx.log(f"\n[info] patched {patched} prompt(s). firmware size is now {len(fw)} bytes.")

        ctx.log("\n=== sample rate ===")
        sr_offset = patch_prompt_sample_rate_dynamic(fw, self.tbh_offset, target_rate, ctx.log)

        if apply_stereo:
            apply_stereo_patches(fw, self.tbh_offset, sr_offset, ctx.log)
        else:
            ctx.log("\n[info] stereo mixer patch skipped by user choice.")

        return fw