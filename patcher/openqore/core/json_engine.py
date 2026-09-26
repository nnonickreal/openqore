import json
from .hooks import HookContext
from .ui import Field
from . import thumb2


def load_model(json_path) -> dict:
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _field_from_patch(p: dict):
    fdef = p.get("field")
    if not fdef:
        return None
    return Field(
        id=fdef["id"], label=fdef.get("label", fdef["id"]), kind=fdef.get("kind", "int"),
        default=fdef.get("default"), min=fdef.get("min"), max=fdef.get("max"),
        choices=fdef.get("choices"), help=fdef.get("help", ""),
    )


def collect_fields(model: dict):
    fields = []
    for p in model.get("patches", []):
        f = _field_from_patch(p)
        if f:
            fields.append(f)
    return fields


# ---- supported hook types (developer picks one per patch entry in JSON) ----

def _apply_hex_replace(ctx: HookContext, p: dict, values: dict):
    ctx.replace_signature(p["find_hex"], p.get("find_mask"), p["replace_hex"], p.get("occurrence", "first"))


def _apply_int_field_patch(ctx: HookContext, p: dict, values: dict):
    """Find a movw/mov.w-style 16-bit immediate near a signature and set it
    to a user-supplied value (register-independent)."""
    fdef = p["field"]
    value = int(values[fdef["id"]])
    sig_off = ctx.find_signature(p["signature_hex"], p.get("signature_mask"))
    if sig_off is None:
        ctx.log(f"[warning] patch '{p.get('name')}': signature not found, skipped.")
        return
    instr_off = sig_off + p.get("instr_offset", 0)
    instr = ctx.read_bytes(instr_off, 4)
    rd, _old = thumb2.decode_movw_thumb2(instr)
    ctx.write_instruction(instr_off, thumb2.encode_movw_thumb2(rd, value & 0xFFFF),
                           f"({p.get('name')}: -> {value})")


def _apply_choice_patch(ctx: HookContext, p: dict, values: dict):
    fdef = p["field"]
    key = str(values[fdef["id"]])
    variants = p["variants"]
    if key not in variants:
        ctx.log(f"[warning] patch '{p.get('name')}': no variant for value {key}")
        return
    ctx.replace_signature(p["find_hex"], p.get("find_mask"), variants[key], p.get("occurrence", "first"))


def _apply_bool_toggle(ctx: HookContext, p: dict, values: dict):
    fdef = p["field"]
    value = bool(values[fdef["id"]])
    replace_hex = p["replace_hex_true"] if value else p.get("replace_hex_false", p["find_hex"])
    ctx.replace_signature(p["find_hex"], p.get("find_mask"), replace_hex, p.get("occurrence", "first"))


def _apply_inject_data(ctx: HookContext, p: dict, values: dict):
    """Append raw bytes at the end of the image, then patch a pointer literal
    and/or a size immediate to point at the injected block."""
    data = bytes.fromhex(p["data_hex"].replace(" ", ""))
    _off, va = ctx.allocate_at_end(data, align=p.get("align", 4), back_offset=p.get("back_offset", 0))

    if "pointer_signature_hex" in p:
        sig_off = ctx.find_signature(p["pointer_signature_hex"], p.get("pointer_signature_mask"))
        if sig_off is not None:
            ctx.write_u32(sig_off + p.get("pointer_literal_offset", 0), va)

    if "size_signature_hex" in p:
        sig_off = ctx.find_signature(p["size_signature_hex"], p.get("size_signature_mask"))
        if sig_off is not None:
            instr_off = sig_off + p.get("size_instr_offset", 0)
            rd, _ = thumb2.decode_movw_thumb2(ctx.read_bytes(instr_off, 4))
            ctx.write_instruction(instr_off, thumb2.encode_movw_thumb2(rd, len(data) & 0xFFFF),
                                   "(injected data size)")


_HANDLERS = {
    "hex_replace": _apply_hex_replace,
    "int_field_patch": _apply_int_field_patch,
    "choice_patch": _apply_choice_patch,
    "bool_toggle": _apply_bool_toggle,
    "inject_data": _apply_inject_data,
}


def apply_model(model: dict, fw: bytearray, base_address: int, values: dict, log=print) -> bytearray:
    ctx = HookContext(fw, base_address=base_address, logger=log)
    for p in model.get("patches", []):
        handler = _HANDLERS.get(p["type"])
        if handler is None:
            log(f"[warning] unknown patch type '{p['type']}', skipped.")
            continue
        log(f"\n=== {p.get('name', p['type'])} ===")
        handler(ctx, p, values)
    return ctx.fw