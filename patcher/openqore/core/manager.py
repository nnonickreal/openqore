import subprocess
import sys
from pathlib import Path

from . import repack_common, json_engine, module_loader, downloader, firmware_archive
from .ui import Field, ask_console
from .hooks import HookContext


def print_banner():
    print("=" * 60)
    print("  qorepatcher by nnonick (1.0.0-rc1)")
    print("=" * 60)
    print()


def _console_progress(done, total, percent):
    total_disp = total or done
    bar_len = 30
    filled = int(bar_len * (percent / 100)) if total else 0
    bar = "#" * filled + "-" * (bar_len - filled)
    print(f"\r[{bar}] {percent:5.1f}% ({done}/{total_disp})", end="", flush=True)
    if total and done >= total:
        print()


def interactive_download_from_archive() -> str | None:
    default_url = firmware_archive.DEFAULT_CATALOG_URL
    print("\n--- Firmware Archive ---")
    custom_url = input(f"Enter catalog URL or path [Enter = default]: ").strip()
    catalog_source = custom_url if custom_url else default_url

    try:
        vendors = firmware_archive.fetch_catalog(catalog_source)
    except Exception as e:
        print(f"[error] Failed to load catalog: {e}")
        return None

    if not vendors:
        print("[error] Catalog contains no vendors.")
        return None

    selected_vendor = None
    if len(vendors) == 1:
        selected_vendor = vendors[0]
    else:
        print("\nSelect vendor:")
        for idx, v in enumerate(vendors, 1):
            count = len(v.get("devices", []))
            print(f"  {idx}. {v.get('name', 'Unknown')} ({count} devices)")

        while True:
            choice = input(f"Select vendor (1-{len(vendors)}, or 0 to cancel): ").strip()
            if choice == "0":
                return None
            try:
                v_idx = int(choice) - 1
                if 0 <= v_idx < len(vendors):
                    selected_vendor = vendors[v_idx]
                    break
            except ValueError:
                pass
            print("[error] invalid choice.")

    devices = selected_vendor.get("devices", [])
    if not devices:
        print(f"[error] no devices listed for {selected_vendor.get('name')}.")
        return None

    print(f"\nselect {selected_vendor.get('name')} Model:")
    for idx, dev in enumerate(devices, 1):
        tag = dev.get("model_code") or dev.get("chip")
        tag_info = f" ({tag})" if tag else ""
        print(f"  {idx}. {dev.get('name', 'Unknown')}{tag_info}")

    while True:
        choice = input(f"select model (1-{len(devices)}, or 0 to cancel): ").strip()
        if choice == "0":
            return None
        try:
            dev_idx = int(choice) - 1
            if 0 <= dev_idx < len(devices):
                selected_dev = devices[dev_idx]
                break
        except ValueError:
            pass
        print("[error] invalid choice.")

    firmwares = selected_dev.get("firmwares", [])
    if not firmwares:
        print("[error] no firmware versions available for this model.")
        return None

    print(f"\navailable firmware versions for {selected_dev.get('name')}:")
    for idx, fw_info in enumerate(firmwares, 1):
        notes = f" - {fw_info.get('notes').replace(chr(10), ' ')}" if fw_info.get("notes") else ""
        print(f"  {idx}. v{fw_info.get('version', 'unknown')}{notes}")

    while True:
        choice = input(f"select version (1-{len(firmwares)}, or 0 to cancel): ").strip()
        if choice == "0":
            return None
        try:
            fw_idx = int(choice) - 1
            if 0 <= fw_idx < len(firmwares):
                selected_fw = firmwares[fw_idx]
                break
        except ValueError:
            pass
        print("[error] invalid choice.")

    fw_url = selected_fw["url"]
    expected_crc = selected_fw.get("crc32")
    dev_name_clean = "".join(c if c.isalnum() else "_" for c in selected_dev.get("name", "fw"))
    dest_name = f"{dev_name_clean}_{selected_fw.get('version', 'fw')}.bin"
    fw_dir = Path.home() / ".openqore" / "bin" / "firmwares"
    fw_dir.mkdir(parents=True, exist_ok=True)
    dest_path = fw_dir / dest_name

    while True:
        print(f"\n[download] downloading {dest_path.name}...")
        try:
            firmware_archive.download_firmware(
                fw_url, dest_path, on_progress=_console_progress, log=print
            )
        except Exception as e:
            print(f"[error] download failed: {e}")
            retry = input("retry download? [Y/n]: ").strip().lower()
            if retry not in ("", "y", "yes"):
                return None
            continue

        print("\n[check] verifying firmware CRC32...")
        valid, msg = firmware_archive.verify_firmware_crc(dest_path, expected_crc)
        if valid:
            print(f"[success] {msg}")
            return str(dest_path)
        else:
            print(f"[error] {msg}")
            retry = input("CRC check failed! re-download the file? [Y/n]: ").strip().lower()
            if retry not in ("", "y", "yes"):
                print("[warning] proceeding with unverified firmware.")
                return str(dest_path)


def choose_firmware_file(prompt="firmware files found") -> str | None:
    fw_dir = Path.home() / ".openqore" / "bin" / "firmwares"
    
    local_bins = list(Path(".").glob("*.bin")) + list(Path(".").glob("*.dfu"))
    cached_bins = list(fw_dir.glob("*.bin")) if fw_dir.exists() else []
    
    bin_files = sorted(set(local_bins + cached_bins), key=lambda p: p.name)
    
    print(f"\n{prompt}:")
    idx = 1
    for f in bin_files:
        location = " (archive)" if fw_dir in f.parents else ""
        print(f"  {idx}. {f.name}{location}")
        idx += 1

    custom_idx = idx
    print(f"  {custom_idx}. enter custom file path")
    archive_idx = idx + 1
    print(f"  {archive_idx}. 🌐 download from online archive (catalog)")

    while True:
        choice = input(f"select an option (1-{archive_idx}): ").strip()
        try:
            c = int(choice)
        except ValueError:
            print("[error] invalid choice.")
            continue

        if 1 <= c <= len(bin_files):
            return str(bin_files[c - 1])
        if c == custom_idx:
            path = input("enter path to the firmware file: ").strip()
            return path if path else None
        if c == archive_idx:
            return interactive_download_from_archive()
        print("[error] invalid choice.")


def ask_packed_flag(fw_path: str) -> bool:
    auto = repack_common.detect_packed(fw_path)
    guess = "packed" if auto else "unpacked (raw)"
    print(f"\n[auto-detect] firmware appears to be {guess.upper()} (LZMA header check).")
    raw = input("is the firmware packed? [enter = accept auto-detect, y/n = override]: ").strip().lower()
    if raw == "":
        return auto
    return raw in ("y", "yes")


def select_module():
    json_models = module_loader.list_json_models()
    py_modules = module_loader.list_py_modules()
    entries = []

    print("\navailable patch modules:")
    idx = 1
    for m in json_models:
        print(f"  {idx}. [simple/json]  {m['name']}")
        desc_line = m.get("description", "").strip().split("\n")[0]
        if len(desc_line) > 75:
            desc_line = desc_line[:72] + "..."
        if desc_line:
            print(f"     └─ {desc_line}")
        entries.append(("json", m))
        idx += 1

    for m in py_modules:
        print(f"  {idx}. [advanced/py]  {m['name']}  (chip: {m['chip']})")
        desc_line = m.get("description", "").strip().split("\n")[0]
        if len(desc_line) > 75:
            desc_line = desc_line[:72] + "..."
        if desc_line:
            print(f"     └─ {desc_line}")
        entries.append(("py", m))
        idx += 1

    if not entries:
        print("  (none found — put .json files into modules_json/ or python modules into modules_py/)")
        return None

    print("\nenter '<num>' to select, or '? <num>' to view module full description.")
    while True:
        raw = input(f"select a module (1-{len(entries)}): ").strip()
        if not raw:
            continue

        if raw.startswith(("?", "info", "help")):
            parts = raw.split()
            if len(parts) > 1 and parts[1].isdigit():
                i = int(parts[1])
                if 1 <= i <= len(entries):
                    m = entries[i - 1][1]
                    print(f"\n=== {m['name']} ===")
                    print(f"Type: {entries[i - 1][0].upper()}")
                    if "chip" in m:
                        print(f"Chip: {m['chip']}")
                    print(f"\nDescription:\n{m.get('description', 'No description.')}\n")
                    continue
            print("[error] usage: ? <number>")
            continue

        try:
            i = int(raw)
        except ValueError:
            print("[error] invalid choice.")
            continue
        if 1 <= i <= len(entries):
            return entries[i - 1]
        print("[error] out of range.")


def _finalize_output(fw: bytearray, original_path: str, requires_repack, was_packed: bool, log):
    out_stem = Path(original_path).stem
    out_dir = Path(original_path).parent
    final_out = out_dir / f"{out_stem}_patched.bin"

    do_repack = was_packed if requires_repack == "auto" else bool(requires_repack)

    if do_repack:
        raw_tmp = out_dir / f"{out_stem}_patched_raw.tmp"
        Path(raw_tmp).write_bytes(fw)
        repack_common.repack(raw_tmp, final_out, log=log)
        Path(raw_tmp).unlink(missing_ok=True)
    else:
        Path(final_out).write_bytes(fw)

    log(f"\n[success] saved: {final_out}")


def run_json_module(model_entry, fw_path: str, packed: bool):
    log = print
    model = model_entry["data"]

    tmp_raw = fw_path
    if packed:
        tmp_raw = fw_path + ".unpacked.tmp"
        repack_common.unpack(fw_path, tmp_raw, log=log)

    fw = bytearray(Path(tmp_raw).read_bytes())

    base_address = 0
    if "base_address_choices" in model:
        choices = [(int(c["value"], 0), c["label"]) for c in model["base_address_choices"]]
        f = Field(id="__base", label="firmware base address", kind="choice", choices=choices, default=choices[0][0])
        base_address = ask_console([f])["__base"]
    elif "base_address" in model:
        base_address = int(model["base_address"], 0)

    fields = json_engine.collect_fields(model)
    values = ask_console(fields) if fields else {}

    fw = json_engine.apply_model(model, fw, base_address, values, log=log)
    _finalize_output(fw, fw_path, model.get("requires_repack", "auto"), packed, log)

    if tmp_raw != fw_path:
        Path(tmp_raw).unlink(missing_ok=True)


def run_py_module(module_entry, fw_path: str, packed: bool):
    log = print
    module = module_entry["cls"]()

    tmp_raw = fw_path
    if packed:
        tmp_raw = fw_path + ".unpacked.tmp"
        repack_common.unpack(fw_path, tmp_raw, log=log)

    fw = bytearray(Path(tmp_raw).read_bytes())
    ctx = HookContext(fw, base_address=0, logger=log)
    ctx.progress = _console_progress

    static_fields = module.get_static_fields(ctx)
    static_values = ask_console(static_fields) if static_fields else {}
    if "base_address" in static_values:
        ctx.base_address = static_values["base_address"]

    module.prepare(fw, ctx, static_values)

    dynamic_fields = module.get_dynamic_fields(fw, ctx, static_values)
    dynamic_values = ask_console(dynamic_fields) if dynamic_fields else {}

    values = {**static_values, **dynamic_values}
    fw = module.run(fw, values, ctx)

    requires_repack = module.requires_repack_hint(fw_path)
    if requires_repack is None:
        requires_repack = "auto"

    _finalize_output(fw, fw_path, requires_repack, packed, log)

    if tmp_raw != fw_path:
        Path(tmp_raw).unlink(missing_ok=True)


def menu_patch_firmware():
    fw_path = choose_firmware_file()
    if not fw_path or not Path(fw_path).exists():
        return

    packed = ask_packed_flag(fw_path)

    selection = select_module()
    if selection is None:
        return
    kind, entry = selection

    try:
        if kind == "json":
            run_json_module(entry, fw_path, packed)
        else:
            run_py_module(entry, fw_path, packed)
    except Exception as e:
        print(f"[error] patch failed: {e}")


def menu_manual_pack_unpack():
    print("\n  1. unpack (decompress) firmware")
    print("  2. pack (repack) firmware")
    choice = input("select (1-2): ").strip()
    fw_path = choose_firmware_file()
    if not fw_path or not Path(fw_path).exists():
        print("[error] file not found.")
        return
    out_path = input("output file path: ").strip()
    if not out_path:
        print("[error] no output path given.")
        return
    try:
        if choice == "1":
            repack_common.unpack(fw_path, out_path)
        elif choice == "2":
            chunk_raw = input("chunk size in bytes [131072]: ").strip()
            repack_common.repack(fw_path, out_path, chunk_size=int(chunk_raw) if chunk_raw else 131072)
        else:
            print("[error] invalid choice.")
    except Exception as e:
        print(f"[error] {e}")


def menu_update_modules():
    repo = input("github repo (owner/name) [enter for default]: ").strip() or "nnonickreal/openqore/modules/modules.json"
    try:
        downloader.update_modules_from_github(repo)
    except Exception as e:
        print(f"[error] update failed: {e}")


def print_menu():
    print("\nselect an option:")
    print("  1. patch firmware (select module & download firmware)")
    print("  2. manually pack/unpack firmware")
    print("  3. update modules database from github")
    print("  4. exit")
    print()


def main() -> int:
    print_banner()
    while True:
        print_menu()
        try:
            choice = input("select an option (1-5): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n[info] exiting...")
            return 0

        if choice == "1":
            menu_patch_firmware()
            input("\npress enter to continue...")
        elif choice == "2":
            menu_manual_pack_unpack()
            input("\npress enter to continue...")
        elif choice == "3":
            menu_update_modules()
            input("\npress enter to continue...")
        elif choice == "4":
            print("\n[info] exiting...")
            return 0
        else:
            print("[error] invalid option.")