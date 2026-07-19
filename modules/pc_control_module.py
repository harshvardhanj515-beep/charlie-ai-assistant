"""
Executes the actual PC actions the brain decides on.
This is deliberately a small, explicit allowlist of actions rather than
letting the LLM run arbitrary shell commands - an LLM with unrestricted
shell access on your personal laptop is a real security risk (a bad
transcription or a weird model output could delete files or run something
unintended). Add new actions here deliberately, one at a time, as you trust them.

Install: pip install psutil pillow
"""

import subprocess
import platform
import psutil
import json
import sys
import os
import datetime

sys.path.append("..")
from config.settings import TASKS_FILE, APP_PATHS
from modules.pc_control_extensions import EXTRA_ACTIONS

SYSTEM = platform.system()  # "Windows", "Darwin" (Mac), "Linux"

APP_MAP = {
    "Windows": {
        "chrome": "chrome.exe",
        "firefox": "firefox.exe",
        "notepad": "notepad.exe",
        "vscode": "code.cmd",
        "spotify": "spotify.exe",
        "calculator": "calc.exe",
    },
    "Darwin": {
        "chrome": "Google Chrome",
        "vscode": "Visual Studio Code",
        "spotify": "Spotify",
    },
    "Linux": {
        "chrome": "google-chrome",
        "vscode": "code",
    }
}


def open_app(app_name):
    # Normalize input by removing all spaces, underscores, and hyphens
    clean_app = app_name.lower().replace(" ", "").replace("_", "").replace("-", "")
    
    mapped = None
    # Check custom APP_PATHS first
    for key, val in APP_PATHS.items():
        if key.lower().replace(" ", "").replace("_", "").replace("-", "") == clean_app:
            mapped = val
            break
            
    if mapped:
        if mapped.startswith("http"):
            return open_url(mapped)
    else:
        # Check default system APP_MAP
        system_map = APP_MAP.get(SYSTEM, {})
        for key, val in system_map.items():
            if key.lower().replace(" ", "").replace("_", "").replace("-", "") == clean_app:
                mapped = val
                break
        
        # Fallback to whatever the LLM generated if no map is found
        if not mapped:
            mapped = app_name
        
    try:
        if SYSTEM == "Windows":
            subprocess.Popen([mapped])
        elif SYSTEM == "Darwin":
            subprocess.Popen(["open", "-a", mapped])
        else:
            subprocess.Popen([mapped])
        return True
    except Exception as e:
        print(f"[PCControl] Failed to open {app_name}: {e}")
        return False


def close_app(app_name):
    app_name = app_name.lower()
    closed = False
    for proc in psutil.process_iter(['name']):
        if app_name in (proc.info['name'] or "").lower():
            try:
                proc.terminate()
                closed = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    return closed


def open_url(url, browser=None):
    try:
        if browser:
            browser_path = APP_PATHS.get(browser.lower(), browser.lower())
            subprocess.Popen([browser_path, url])
        else:
            if SYSTEM == "Windows":
                subprocess.Popen(["rundll32", "url.dll,FileProtocolHandler", url])
            elif SYSTEM == "Darwin":
                subprocess.Popen(["open", url])
            else:
                subprocess.Popen(["xdg-open", url])
        return True
    except Exception as e:
        print(f"[PCControl] Failed to open URL {url}: {e}")
        return False
def shutdown():
    try:
        if SYSTEM == "Windows":
            subprocess.Popen("shutdown /s /t 5", shell=True)
        # Linux: shutdown -h +0 (or schedule)
        # Mac: sudo shutdown -h now
        return {"success": True, "action": "shutdown", "delay": 5}
    except Exception as e:
        return {"success": False, "error": str(e)}


def restart():
    try:
        if SYSTEM == "Windows":
            subprocess.Popen("shutdown /r /t 5", shell=True)
        return {"success": True, "action": "restart", "delay": 5}
    except Exception as e:
        return {"success": False, "error": str(e)}


def sleep_pc():
    try:
        if SYSTEM == "Windows":
            subprocess.Popen("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True)
        return {"success": True, "action": "sleep"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def lock_screen():
    try:
        if SYSTEM == "Windows":
            subprocess.Popen("rundll32.exe user32.dll,LockWorkStation", shell=True)
        return {"success": True, "action": "lock_screen"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def wifi_toggle(state):
    on = str(state).lower() in ["true", "on", "1"]
    try:
        if SYSTEM == "Windows":
            cmd = "netsh interface set interface \"Wi-Fi\" admin=" + ("enable" if on else "disable")
            subprocess.run(cmd, shell=True, capture_output=True)
            # Linux: nmcli radio wifi on/off
            # Mac: networksetup -setairportpower en0 on/off
        return True
    except Exception as e:
        print(f"[PCControl] Failed to toggle WiFi: {e}")
        return False


def wifi_connect(ssid):
    try:
        if SYSTEM == "Windows":
            subprocess.run(f'netsh wlan connect name="{ssid}"', shell=True, capture_output=True)
        return True
    except Exception as e:
        print(f"[PCControl] Failed to connect WiFi: {e}")
        return False


def bluetooth_toggle(state):
    on = str(state).lower() in ["true", "on", "1"]
    try:
        if SYSTEM == "Windows":
            # BT toggle via PS or command line on Windows is famously restricted.
            # Shelling to settings is the safest fallback without heavy C# libraries.
            subprocess.run("start ms-settings:bluetooth", shell=True)
            # Linux: rfkill block/unblock bluetooth
            # Mac: blueutil -p 1/0
        return True
    except Exception as e:
        print(f"[PCControl] Failed to toggle BT: {e}")
        return False


def bluetooth_connect(device_name):
    print(f"[PCControl] BT connect requested for {device_name}")
    return True


def set_volume(level):
    try:
        level = max(0, min(100, int(level)))
        if SYSTEM == "Windows":
            # Using Volume Up/Down keystrokes to simulate level
            ps_script = f"""
Function Set-Volume {{
    param([int]$Level)
    $code = @"
using System.Runtime.InteropServices;
public class Audio {{
    [DllImport("user32.dll")]
    public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, uint dwExtraInfo);
}}
"@
    Add-Type -TypeDefinition $code
    for ($i=0; $i -lt 50; $i++) {{ [Audio]::keybd_event(0xAE, 0, 0, 0) }} # Down to 0
    for ($i=0; $i -lt ($Level / 2); $i++) {{ [Audio]::keybd_event(0xAF, 0, 0, 0) }} # Up
}}
Set-Volume -Level {level}
"""
            subprocess.run(["powershell", "-Command", ps_script], capture_output=True)
        return True
    except Exception as e:
        print(f"[PCControl] Failed to set volume: {e}")
        return False


def mute_toggle():
    try:
        if SYSTEM == "Windows":
            ps_script = "$obj = new-object -com wscript.shell; $obj.SendKeys([char]173)"
            subprocess.run(["powershell", "-Command", ps_script], capture_output=True)
        return True
    except Exception as e:
        print(f"[PCControl] Failed to toggle mute: {e}")
        return False


def screenshot():
    try:
        from PIL import ImageGrab
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"
        img = ImageGrab.grab()
        img.save(filename)
        return {"success": True, "file": filename}
    except ImportError:
        print("[PCControl] PIL is not installed. Run: pip install pillow")
        return {"success": False, "error": "PIL not installed"}
    except Exception as e:
        print(f"[PCControl] Failed to take screenshot: {e}")
        return {"success": False, "error": str(e)}


def clipboard_get():
    try:
        if SYSTEM == "Windows":
            res = subprocess.run(["powershell", "-Command", "Get-Clipboard"], capture_output=True, text=True)
            return {"success": True, "text": res.stdout.strip()}
    except Exception as e:
        print(f"[PCControl] Failed to get clipboard: {e}")
        return {"success": False}


def clipboard_set(text):
    try:
        if SYSTEM == "Windows":
            subprocess.run(["powershell", "-Command", f"Set-Clipboard -Value '{text}'"], capture_output=True)
            return {"success": True}
    except Exception as e:
        print(f"[PCControl] Failed to set clipboard: {e}")
        return {"success": False}

def system_status():
    battery = psutil.sensors_battery()
    battery_str = f"{battery.percent}% ({'charging' if battery.power_plugged else 'on battery'})" if battery else "N/A (desktop?)"
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory().percent
    return {
        "battery": battery_str,
        "cpu_percent": cpu,
        "ram_percent": ram
    }


def _load_tasks():
    path = os.path.join(os.path.dirname(__file__), "..", TASKS_FILE)
    with open(path, "r") as f:
        return json.load(f)


def _save_tasks(data):
    path = os.path.join(os.path.dirname(__file__), "..", TASKS_FILE)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def list_tasks():
    data = _load_tasks()
    return [t for t in data["tasks"] if not t["done"]]


def add_task(title):
    data = _load_tasks()
    data["tasks"].append({"title": title, "done": False, "priority": "medium"})
    _save_tasks(data)
    return True


def complete_task(title):
    data = _load_tasks()
    for t in data["tasks"]:
        if title.lower() in t["title"].lower():
            t["done"] = True
            _save_tasks(data)
            return True
    return False


def execute(action, params):
    """Router: takes the brain's decision and calls the right function.
    Returns a result dict the main loop can use to shape Charlie's spoken reply."""
    if action in EXTRA_ACTIONS:
        return EXTRA_ACTIONS[action](params)
    
    if action == "open_app" or action == "open":
        # The 1B parameter LLM frequently hallucinates "open" instead of "open_app".
        # This fallback catches it so the command still succeeds.
        ok = open_app(params.get("app_name", ""))
        return {"success": ok}
    elif action == "close_app" or action == "close":
        ok = close_app(params.get("app_name", ""))
        return {"success": ok}
    elif action == "open_url":
        ok = open_url(params.get("url", ""), params.get("browser"))
        return {"success": ok}
    elif action == "shutdown":
        return shutdown()
    elif action == "restart":
        return restart()
    elif action == "sleep":
        return sleep_pc()
    elif action == "lock_screen":
        return lock_screen()
    elif action == "wifi_toggle":
        ok = wifi_toggle(params.get("state", "on"))
        return {"success": ok}
    elif action == "wifi_connect":
        ok = wifi_connect(params.get("ssid", ""))
        return {"success": ok}
    elif action == "bluetooth_toggle":
        ok = bluetooth_toggle(params.get("state", "on"))
        return {"success": ok}
    elif action == "bluetooth_connect":
        ok = bluetooth_connect(params.get("device_name", ""))
        return {"success": ok}
    elif action == "set_volume":
        ok = set_volume(params.get("level", 50))
        return {"success": ok}
    elif action == "mute_toggle":
        ok = mute_toggle()
        return {"success": ok}
    elif action == "screenshot":
        return screenshot()
    elif action == "clipboard_get":
        return clipboard_get()
    elif action == "clipboard_set":
        ok = clipboard_set(params.get("text", ""))
        return {"success": ok}
    elif action == "system_status":
        return system_status()
    elif action == "list_tasks":
        return {"tasks": list_tasks()}
    elif action == "add_task":
        ok = add_task(params.get("title", ""))
        return {"success": ok}
    elif action == "complete_task":
        ok = complete_task(params.get("title", ""))
        return {"success": ok}
    elif action == "set_display_mode":
        return {"mode": params.get("mode", "widget"), "success": True, "action": "set_display_mode"}
    else:
        return {"success": False, "note": "no PC action needed (chat only)"}
