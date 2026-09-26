import os
import queue
import sys
import threading
import traceback
from pathlib import Path
import webbrowser

import webview

from ..core import downloader, firmware_archive, json_engine, module_loader, repack_common
from ..core.hooks import HookContext
from ..core.ui import Field

# Auto-detect and link the besota submodule if present
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BESOTA_DIR = REPO_ROOT / "besota"
if BESOTA_DIR.is_dir() and str(BESOTA_DIR) not in sys.path:
    sys.path.insert(0, str(BESOTA_DIR))

try:
    import besota_core
    import besota_gui

    BESOTA_AVAILABLE = True
except ImportError:
    besota_core = None
    besota_gui = None
    BESOTA_AVAILABLE = False


def _field_to_dict(f: Field) -> dict:
    choices = None
    if f.choices:
        choices = [list(c) if isinstance(c, (list, tuple)) else [c, str(c)] for c in f.choices]
    return {
        "id": f.id,
        "label": f.label,
        "kind": f.kind,
        "default": f.default,
        "min": f.min,
        "max": f.max,
        "choices": choices,
        "help": f.help,
    }


class Api:

    def __init__(self):
        self._window = None
        self._events = queue.Queue()
        self._session = {}
        self.besota = besota_gui.Api() if BESOTA_AVAILABLE else None

    def set_window(self, window):
        self._window = window
        if self.besota:
            self.besota._bind_window(window)

    def is_besota_available(self) -> bool:
        return BESOTA_AVAILABLE

    # ---------- event log/progress ----------
    def _emit(self, kind, **payload):
        self._events.put({"type": kind, **payload})

    def log(self, message):
        self._emit("log", message=str(message))

    def progress(self, done, total, percent):
        self._emit("progress", done=done, total=total or done, percent=percent)

    def poll_events(self):
        events = []
        for _ in range(100):
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                break
            except Exception:
                break
        return events

    # ---------- filesystem ----------
    def pick_file(self):
        """Unified file picker compatible with both openqore and besota."""
        win = self._window or webview.active_window()
        if not win:
            return None
        result = win.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=("Firmware files (*.bin;*.dfu)", "All files (*.*)"),
        )
        if not result:
            return None

        path = result[0]
        if self.besota:
            self.besota.firmware_path = path

        return {
            "path": path,
            "name": os.path.basename(path),
            "size": os.path.getsize(path),
        }

    def pick_save_path(self, default_name="firmware_patched.bin"):
        win = self._window or webview.active_window()
        if not win:
            return None
        result = win.create_file_dialog(webview.SAVE_DIALOG, save_filename=default_name)
        return result if isinstance(result, str) else (result[0] if result else None)

    def detect_packed(self, path):
        return {"packed": repack_common.detect_packed(path)}

    # ---------- module discovery ----------
    def list_modules(self):
        result = []
        for m in module_loader.list_json_models():
            result.append({
                "ref": f"json::{m['path']}",
                "name": m["name"],
                "kind": "json",
                "chip": m.get("chip", "generic"),
                "description": m.get("description", "No description available."),
            })
        for m in module_loader.list_py_modules():
            result.append({
                "ref": f"py::{m['dir']}",
                "name": m["name"],
                "kind": "py",
                "chip": m["chip"],
                "description": m.get("description", "No description available."),
            })
        return result

    # ---------- firmware catalog ----------
    def get_default_catalog_url(self):
        return firmware_archive.DEFAULT_CATALOG_URL

    def fetch_firmware_catalog(self, catalog_url=""):
        url = catalog_url.strip() if catalog_url else firmware_archive.DEFAULT_CATALOG_URL
        try:
            vendors = firmware_archive.fetch_catalog(url)
            return {"ok": True, "vendors": vendors}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def download_catalog_firmware(self, fw_url, save_filename, expected_crc=None):
        fw_dir = Path.home() / ".openqore" / "bin" / "firmwares"
        fw_dir.mkdir(parents=True, exist_ok=True)

        dest_path = fw_dir / save_filename
        try:
            firmware_archive.download_firmware(
                fw_url, dest_path, on_progress=self.progress, log=self.log
            )
            valid, msg = firmware_archive.verify_firmware_crc(dest_path, expected_crc)
            return {
                "ok": True,
                "path": str(dest_path),
                "crc_valid": valid,
                "crc_message": msg,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------- session: static fields ----------
    def _resolve_module(self, ref: str):
        kind, ident = ref.split("::", 1)
        if kind == "json":
            for m in module_loader.list_json_models():
                if str(m["path"]) == ident:
                    return "json", m
            raise ValueError("json module not found")
        for m in module_loader.list_py_modules():
            if str(m["dir"]) == ident:
                return "py", m
        raise ValueError("python module not found")

    def start_session(self, module_ref, firmware_path, packed):
        kind, m = self._resolve_module(module_ref)
        session_id = f"{id(m)}_{threading.get_ident()}_{id(object())}"
        session = {"kind": kind, "module": m, "firmware_path": firmware_path, "packed": bool(packed)}

        if kind == "json":
            model = m["data"]
            fields = []
            if "base_address_choices" in model:
                choices = [(int(c["value"], 0), c["label"]) for c in model["base_address_choices"]]
                fields.append(_field_to_dict(Field(id="__base", label="firmware base address",
                                                    kind="choice", choices=choices, default=choices[0][0])))
            fields += [_field_to_dict(f) for f in json_engine.collect_fields(model)]
        else:
            instance = m["cls"]()
            session["instance"] = instance
            ctx = HookContext(bytearray(), base_address=0, logger=self.log)
            ctx.progress = self.progress
            session["ctx"] = ctx
            fields = [_field_to_dict(f) for f in instance.get_static_fields(ctx)]

        self._session[session_id] = session
        return {"session_id": session_id, "fields": fields}

    def _validate_values(self, fields_dicts, values):
        clean = {}
        for f in fields_dicts:
            fid = f["id"]
            if fid not in values:
                clean[fid] = f.get("default")
                continue
            v = values[fid]
            if f["kind"] in ("int", "float"):
                try:
                    v = int(v) if f["kind"] == "int" else float(v)
                except (TypeError, ValueError):
                    v = f.get("default")
                else:
                    if f["min"] is not None and v < f["min"]:
                        v = f["min"]
                    if f["max"] is not None and v > f["max"]:
                        v = f["max"]
            elif f["kind"] == "bool":
                v = bool(v)
            elif f["kind"] == "choice":
                allowed = [c[0] for c in (f["choices"] or [])]
                if v not in allowed:
                    v = f.get("default")
            clean[fid] = v
        return clean

    def submit_static(self, session_id, values):
        session = self._session[session_id]
        if session["kind"] == "json":
            session["static_values"] = values
            return {"fields": []}

        instance = session["instance"]
        ctx = session["ctx"]
        static_field_dicts = [_field_to_dict(f) for f in instance.get_static_fields(ctx)]
        clean = self._validate_values(static_field_dicts, values)
        if "base_address" in clean:
            ctx.base_address = clean["base_address"]
        session["static_values"] = clean

        raw_path = session["firmware_path"]
        if session["packed"]:
            tmp_raw = raw_path + ".unpacked.tmp"
            repack_common.unpack(raw_path, tmp_raw, log=self.log)
            session["tmp_raw"] = tmp_raw
            raw_path = tmp_raw
        fw = bytearray(Path(raw_path).read_bytes())
        ctx.fw = fw
        session["fw"] = fw

        instance.prepare(fw, ctx, clean)
        dyn_fields = [_field_to_dict(f) for f in instance.get_dynamic_fields(fw, ctx, clean)]
        session["dynamic_field_dicts"] = dyn_fields
        return {"fields": dyn_fields}

    def run_patch(self, session_id, dynamic_values, output_path):
        threading.Thread(target=self._run_patch_thread,
                         args=(session_id, dynamic_values, output_path), daemon=True).start()
        return {"started": True}

    def _run_patch_thread(self, session_id, dynamic_values, output_path):
        session = self._session.get(session_id)
        if not session:
            self._emit("done", ok=False, error="session expired")
            return
        try:
            if session["kind"] == "json":
                model = session["module"]["data"]
                raw_path = session["firmware_path"]
                packed = session["packed"]
                tmp_raw = raw_path
                if packed:
                    tmp_raw = raw_path + ".unpacked.tmp"
                    repack_common.unpack(raw_path, tmp_raw, log=self.log)
                fw = bytearray(Path(tmp_raw).read_bytes())
                base_address = session.get("static_values", {}).get("__base", 0)
                fw = json_engine.apply_model(model, fw, base_address, session.get("static_values", {}), log=self.log)
                requires_repack = model.get("requires_repack", "auto")
                if tmp_raw != raw_path:
                    Path(tmp_raw).unlink(missing_ok=True)
            else:
                instance = session["instance"]
                ctx = session["ctx"]
                dyn_dicts = session.get("dynamic_field_dicts", [])
                clean_dyn = self._validate_values(dyn_dicts, dynamic_values)
                values = {**session.get("static_values", {}), **clean_dyn}
                fw = instance.run(session["fw"], values, ctx)
                requires_repack = instance.requires_repack_hint(session["firmware_path"]) or "auto"

            do_repack = session["packed"] if requires_repack == "auto" else bool(requires_repack)
            if do_repack:
                raw_tmp = output_path + ".raw.tmp"
                Path(raw_tmp).write_bytes(fw)
                repack_common.repack(raw_tmp, output_path, log=self.log)
                Path(raw_tmp).unlink(missing_ok=True)
            else:
                Path(output_path).write_bytes(fw)

            if session.get("tmp_raw"):
                Path(session["tmp_raw"]).unlink(missing_ok=True)

            self.log(f"[success] saved: {output_path}")
            self._emit("done", ok=True, output=output_path)
        except Exception as e:
            self.log(f"[error] {e}")
            self.log(traceback.format_exc())
            self._emit("done", ok=False, error=str(e))
        finally:
            self._session.pop(session_id, None)

    # ---------- besota direct proxies ----------
    def set_firmware_by_path(self, path: str):
        if self.besota:
            return self.besota.set_firmware_by_path(path)

    def scan_devices(self, name: str, duration):
        if not self.besota:
            win = self._window or webview.active_window()
            if win:
                win.evaluate_js("onScanFailed('besota submodule not installed')")
            return False
        return self.besota.scan_devices(name, duration)

    def connect(self, address: str):
        if not self.besota:
            win = self._window or webview.active_window()
            if win:
                win.evaluate_js("onConnectFailed('besota submodule not installed')")
            return False
        return self.besota.connect(address)

    def disconnect(self):
        if self.besota:
            return self.besota.disconnect()
        return True

    def start_flash(self, protocol_key: str, ota_addr_hex: str):
        if not self.besota:
            win = self._window or webview.active_window()
            if win:
                win.evaluate_js("onFlashDone('besota submodule not installed')")
            return False
        return self.besota.start_flash(protocol_key, ota_addr_hex)

    def abort(self):
        if self.besota:
            return self.besota.abort()
        return True

    def open_browser(self, url: str) -> bool:
        try:
            webbrowser.open(url)
            return True
        except Exception:
            return False