"""Online update check: reads the latest version from the RAF Pictures website."""
import json
import os
import re
import sys
import threading
import time
import urllib.request

import bpy


#----CONSTANTS----
UPDATE_URL = "https://rafpictures.vercel.app/updates/raf-scatter.json"
DOWNLOAD_PAGE = "https://rafpictures.vercel.app/raf-scatter.html"
_CHECK_INTERVAL = 24 * 60 * 60
_TIMEOUT = 6.0
_MAX_BYTES = 16 * 1024
_MAX_MESSAGE = 200
_VERSION_RE = re.compile(r"^\d+(\.\d+){1,3}$")
_STATE_FILE = "update_check.json"
_POLL_SECONDS = 0.25

STATUS_IDLE = 'IDLE'
STATUS_CHECKING = 'CHECKING'
STATUS_LATEST = 'LATEST'
STATUS_AVAILABLE = 'AVAILABLE'
STATUS_ERROR = 'ERROR'


#----MODULE STATE----
state = {
    "status": STATUS_IDLE,
    "version": "",
    "url": DOWNLOAD_PAGE,
    "message": "",
    "checked": 0.0,
    "error": "",
}
_pending = []
_lock = threading.Lock()
_thread = None


#----VERSIONS----
def installed_version():
    """Version of the installed add-on as a tuple."""
    package = __package__.rpartition(".")[0]
    return tuple(sys.modules[package].bl_info.get("version", (0, 0, 0)))


def installed_version_text():
    return ".".join(str(number) for number in installed_version())


def _parse_version(text):
    return tuple(int(part) for part in text.split("."))


def online_allowed():
    """False when the user turned off Allow Online Access in Blender."""
    return bool(getattr(bpy.app, "online_access", True))


#----REMOTE DATA----
def _state_path():
    folder = bpy.utils.user_resource('SCRIPTS', path="presets/raf_scatter", create=True)
    return os.path.join(folder, _STATE_FILE)


def _clean(data):
    """Keep only valid fields of the website's answer; raise ValueError when it is unusable."""
    if not isinstance(data, dict):
        raise ValueError("unexpected answer")
    version = str(data.get("version", "")).strip()
    if not _VERSION_RE.match(version):
        raise ValueError("no version in the answer")
    url = str(data.get("url", "")).strip()
    if not url.startswith("https://"):
        url = DOWNLOAD_PAGE
    message = " ".join(str(data.get("message", "")).split())[:_MAX_MESSAGE]
    return {"version": version, "url": url, "message": message}


def _fetch():
    request = urllib.request.Request(
        UPDATE_URL, headers={"User-Agent": f"RAF-Scatter/{installed_version_text()}"},
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
        return _clean(json.loads(response.read(_MAX_BYTES).decode("utf-8")))


def _worker():
    try:
        result = {"ok": True, **_fetch()}
    except Exception as exc:
        result = {"ok": False, "error": str(exc) or exc.__class__.__name__}
    with _lock:
        _pending.append(result)


#----STATE----
def _apply(result):
    state["checked"] = time.time()
    if not result["ok"]:
        state["status"] = STATUS_ERROR
        state["error"] = result["error"]
        return
    state.update(version=result["version"], url=result["url"], message=result["message"], error="")
    newer = _parse_version(result["version"]) > installed_version()
    state["status"] = STATUS_AVAILABLE if newer else STATUS_LATEST
    _save_state()


def _save_state():
    data = {key: state[key] for key in ("version", "url", "message", "checked")}
    try:
        with open(_state_path(), "w", encoding="utf-8") as handle:
            json.dump(data, handle)
    except OSError:
        pass


def load_state():
    """Show the result of the last check until a new one finishes."""
    try:
        with open(_state_path(), encoding="utf-8") as handle:
            data = json.load(handle)
        cleaned = _clean(data)
        checked = float(data.get("checked", 0.0))
    except (OSError, ValueError, TypeError):
        return
    state.update(cleaned, checked=checked)
    newer = _parse_version(cleaned["version"]) > installed_version()
    state["status"] = STATUS_AVAILABLE if newer else STATUS_LATEST


def _redraw_preferences():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'PREFERENCES':
                area.tag_redraw()


def _poll_result():
    with _lock:
        results = _pending[:]
        _pending.clear()
    if not results:
        return _POLL_SECONDS
    _apply(results[-1])
    _redraw_preferences()
    return None


#----CHECK----
def is_checking():
    return _thread is not None and _thread.is_alive()


def start_check():
    """Ask the website for the latest version in the background; False when not allowed."""
    global _thread
    if not online_allowed() or is_checking():
        return False
    state["status"] = STATUS_CHECKING
    _thread = threading.Thread(target=_worker, name="raf_scatter_update_check", daemon=True)
    _thread.start()
    if not bpy.app.timers.is_registered(_poll_result):
        bpy.app.timers.register(_poll_result, first_interval=_POLL_SECONDS)
    return True


def check_due():
    return time.time() - state["checked"] >= _CHECK_INTERVAL


def _startup_check():
    from ..preferences import get_addon_prefs
    prefs = get_addon_prefs()
    if prefs is not None and prefs.check_updates and check_due():
        start_check()
    return None


#----REGISTRATION----
def register():
    load_state()
    if not bpy.app.background:
        bpy.app.timers.register(_startup_check, first_interval=5.0)


def unregister():
    for timer in (_startup_check, _poll_result):
        if bpy.app.timers.is_registered(timer):
            bpy.app.timers.unregister(timer)
