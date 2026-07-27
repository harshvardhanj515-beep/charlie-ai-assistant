"""
pc_control_extensions.py

New actions for Charlie: power control, wifi/bluetooth, volume, clipboard,
screenshot, and window focus.

IMPORTANT: open_app and open_url are deliberately NOT defined here anymore.
pc_control_module.py already has its own correct implementations of both —
they normalize app names against APP_PATHS, redirect URL entries to the
right handler, and launch with subprocess.Popen(list_form) instead of an
unquoted shell string. A duplicate open_app used to live in this file and
get silently prioritized ahead of the real one (execute() checks
EXTRA_ACTIONS before its own elif chain), which broke every app whose path
contains a space — i.e. basically every real Windows path, including
Chrome, Antigravity, and any http(s) entry like ChatGPT. Don't reintroduce
open_app/open_url here; extend the versions in pc_control_module.py instead.

Install:
    pip install pycaw comtypes pyperclip pillow pygetwindow

Windows-only (uses shutdown.exe, netsh, ctypes user32, powershell). If you're
not on Windows, the power/wifi/bluetooth functions need OS-specific swaps
(noted inline).
"""

import os
import sys
import time
import subprocess

sys.path.append("..")
from charlie.core.settings import APP_PATHS, BROWSER_PATHS


# ---------------------------------------------------------------------------
# Power control
# ---------------------------------------------------------------------------

def shutdown(params):
    subprocess.run("shutdown /s /t 5", shell=True)
    return {
        "success": True,
        "cancelable": True,
        "message": "Shutting down in 5 seconds. Say 'cancel' to stop it.",
    }


def restart(params):
    subprocess.run("shutdown /r /t 5", shell=True)
    return {
        "success": True,
        "cancelable": True,
        "message": "Restarting in 5 seconds. Say 'cancel' to stop it.",
    }


def cancel_power_action(params):
    result = subprocess.run("shutdown /a", shell=True, capture_output=True, text=True)
    ok = result.returncode == 0
    return {"success": ok, "message": "Cancelled." if ok else "Nothing to cancel."}


def sleep(params):
    subprocess.run("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True)
    return {"success": True}


def lock_screen(params):
    import ctypes
    ctypes.windll.user32.LockWorkStation()
    return {"success": True}


# ---------------------------------------------------------------------------
# Window focus
# ---------------------------------------------------------------------------
# Bring an already-open app's window to the foreground instead of launching
# a duplicate instance. Falls back to pc_control_module's real open_app if
# nothing matching is currently open.

def focus_app(params):
    try:
        import pygetwindow as gw
    except ImportError:
        return {"success": False, "message": "pygetwindow isn't installed — run: pip install pygetwindow"}

    query = params.get("app_name", "").strip().lower()
    if not query:
        return {"success": False, "message": "No app name given."}

    matching_titles = [t for t in gw.getAllTitles() if t.strip() and query in t.lower()]
    if not matching_titles:
        # Nothing open matching that name — launch it via the real open_app
        # in pc_control_module.py. Imported here (not at module top) to
        # avoid a circular import, since pc_control_module imports
        # EXTRA_ACTIONS from this file.
        from charlie.modules.pc_control_module import open_app as pc_open_app
        ok = pc_open_app(params.get("app_name", ""))
        return {"success": ok}

    try:
        win = gw.getWindowsWithTitle(matching_titles[0])[0]
        if win.isMinimized:
            win.restore()
        win.activate()
        return {"success": True}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ---------------------------------------------------------------------------
# Wifi / Bluetooth
# ---------------------------------------------------------------------------

def wifi_toggle(params):
    state = params.get("state", "on").lower()
    admin_state = "enabled" if state == "on" else "disabled"
    result = subprocess.run(
        f'netsh interface set interface name="Wi-Fi" admin={admin_state}',
        shell=True, capture_output=True, text=True,
    )
    return {"success": result.returncode == 0, "message": result.stdout or result.stderr}


def wifi_connect(params):
    ssid = params.get("ssid", "")
    if not ssid:
        return {"success": False, "message": "No network name given."}
    result = subprocess.run(
        f'netsh wlan connect name="{ssid}"',
        shell=True, capture_output=True, text=True,
    )
    return {"success": result.returncode == 0, "message": result.stdout or result.stderr}


def bluetooth_toggle(params):
    state = params.get("state", "on").lower()
    ps_verb = "Enable" if state == "on" else "Disable"
    cmd = (
        f'powershell -Command "Get-PnpDevice -Class Bluetooth | '
        f'{ps_verb}-PnpDevice -Confirm:$false"'
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return {
        "success": result.returncode == 0,
        "message": "Note: this needs Charlie to be run as administrator.",
    }


def bluetooth_connect(params):
    subprocess.run("start ms-settings:bluetooth", shell=True)
    return {
        "success": True,
        "message": "Opened Bluetooth settings — pairing isn't reliably scriptable on Windows, so you'll need to tap the device.",
    }


# ---------------------------------------------------------------------------
# Volume
# ---------------------------------------------------------------------------

def _get_volume_interface():
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def set_volume(params):
    try:
        level = max(0, min(100, int(params.get("level", 50))))
        vol = _get_volume_interface()
        vol.SetMasterVolumeLevelScalar(level / 100.0, None)
        return {"success": True}
    except Exception as e:
        return {"success": False, "message": str(e)}


def mute_toggle(params):
    try:
        vol = _get_volume_interface()
        current = vol.GetMute()
        vol.SetMute(0 if current else 1, None)
        return {"success": True}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ---------------------------------------------------------------------------
# Screenshot
# ---------------------------------------------------------------------------

def screenshot(params):
    try:
        from PIL import ImageGrab
        out_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "screenshots")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"screenshot_{int(time.time())}.png")
        ImageGrab.grab().save(path)
        return {"success": True, "path": path}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ---------------------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------------------

def clipboard_get(params):
    import pyperclip
    try:
        return {"success": True, "text": pyperclip.paste()}
    except Exception as e:
        return {"success": False, "message": str(e), "text": ""}


def clipboard_set(params):
    import pyperclip
    try:
        pyperclip.copy(params.get("text", ""))
        return {"success": True}
    except Exception as e:
        return {"success": False, "message": str(e)}


EXTRA_ACTIONS = {
    "shutdown": shutdown,
    "restart": restart,
    "cancel_power_action": cancel_power_action,
    "sleep": sleep,
    "lock_screen": lock_screen,
    "focus_app": focus_app,
    "wifi_toggle": wifi_toggle,
    "wifi_connect": wifi_connect,
    "bluetooth_toggle": bluetooth_toggle,
    "bluetooth_connect": bluetooth_connect,
    "set_volume": set_volume,
    "mute_toggle": mute_toggle,
    "screenshot": screenshot,
    "clipboard_get": clipboard_get,
    "clipboard_set": clipboard_set,
}
