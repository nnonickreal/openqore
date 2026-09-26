import sys
from pathlib import Path

import webview

from .bridge import Api

ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def resource_path(*parts):
    if hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS) / "openqore" / "gui" / "assets"
    else:
        base = ASSETS_DIR
    return str(base.joinpath(*parts))


def run_gui():
    if sys.platform == "win32":
        import ctypes
        app_id = "nnonick.openqore.patcher"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)

    api = Api()
    icon_file = resource_path("icon.ico")

    window = webview.create_window(
        "openqore patcher",
        url=resource_path("index.html"),
        js_api=api,
        width=880,
        height=780,
        min_size=(720, 620),
        background_color="#000000",
    )
    api.set_window(window)

    if Path(icon_file).exists():
        webview.start(icon=icon_file, debug=False)
    else:
        webview.start(debug=False)