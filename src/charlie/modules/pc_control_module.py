"""
Executes the actual PC actions the brain decides on.
This is deliberately a small, explicit allowlist of actions rather than
letting the LLM run arbitrary shell commands - an LLM with unrestricted
shell access on your personal laptop is a real security risk (a bad
transcription or a weird model output could delete files or run something
unintended). Add new actions here deliberately, one at a time, as you trust them.

Install: pip install psutil pillow pygetwindow pyautogui
"""

import subprocess
import platform
import psutil
import json
import sys
import os
import datetime

sys.path.append("..")
from charlie.core.settings import TASKS_FILE, APP_PATHS
from charlie.modules.pc_control_extensions import EXTRA_ACTIONS

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
    # Handle multiple apps separated by "and" or commas
    import re
    apps = [a.strip() for a in re.split(r'\band\b|,', app_name) if a.strip()]
    if len(apps) > 1:
        success = True
        for a in apps:
            if not open_app(a):
                success = False
        return success

    # Normalize input by removing all spaces, underscores, and hyphens
    clean_app = apps[0].lower().replace(" ", "").replace("_", "").replace("-", "")
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
                
        # Check common web apps
        if not mapped:
            web_apps = {
                "chatgpt": "https://chatgpt.com",
                "youtube": "https://youtube.com",
                "gemini": "https://gemini.google.com",
                "claude": "https://claude.ai",
            }
            if clean_app in web_apps:
                return open_url(web_apps[clean_app])
        
        # Fallback to whatever the LLM generated if no map is found
        if not mapped:
            mapped = app_name
        
    try:
        if SYSTEM == "Windows":
            if os.path.isabs(mapped) and mapped.lower().endswith(".exe"):
                subprocess.Popen([mapped], cwd=os.path.dirname(mapped))
            else:
                os.startfile(mapped)
        elif SYSTEM == "Darwin":
            subprocess.Popen(["open", "-a", mapped])
        else:
            subprocess.Popen([mapped])
        return True
    except Exception as e:
        print(f"[PCControl] Failed to open {app_name} (mapped to {mapped}): {e}")
        return False


def close_app(app_name):
    app_name = app_name.lower().strip()
    
    # Clean up conversational suffixes
    for suffix in [" immediately", " right now", " now", " please", " for me"]:
        if app_name.endswith(suffix):
            app_name = app_name[:-len(suffix)].strip()
            
    if app_name in ("current window", "current windows", "this window", "this windows", "current", "this", "it", "this one", "that"):
        try:
            import pygetwindow as gw
            active = gw.getActiveWindow()
            if active:
                active.close()
            return True
        except Exception as e:
            print(f"[PCControl] Failed to close active window: {e}")
            return False
            
    if app_name in ("all windows", "everything", "*all*"):
        try:
            import pyautogui
            pyautogui.hotkey('win', 'd')
            return True
        except Exception:
            return False
            
    # Try to close by window title first (this handles "youtube", "chatgpt", etc. running in browser tabs)
    try:
        import pygetwindow as gw
        titles = gw.getAllTitles()
        # Find exact substring match in titles
        for t in titles:
            if app_name in t.lower():
                windows = gw.getWindowsWithTitle(t)
                for w in windows:
                    w.close()
                return True
    except Exception:
        pass
            
    # Fix for common app names that might not match process names perfectly
    if "firefox" in app_name: app_name = "firefox"
    elif "chrome" in app_name: app_name = "chrome"
    elif "spotify" in app_name: app_name = "spotify"
    
    closed = False
    for proc in psutil.process_iter(['name']):
        if app_name in (proc.info['name'] or "").lower():
            try:
                proc.kill()
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
                os.startfile(url)
            elif SYSTEM == "Darwin":
                subprocess.Popen(["open", url])
            else:
                subprocess.Popen(["xdg-open", url])
        return True
    except Exception as e:
        print(f"[PCControl] Failed to open URL {url}: {e}")
        return False


def _focus_and_maximize_browser_window():
    """Brings the actual browser window to the foreground and maximizes it
    before the autoplay click below fires. Without this, the click can land
    wherever the OS considers topmost at that screen position — if Charlie's
    avatar overlay is still covering the screen (fullscreen 'cinematic' mode
    isn't click-through), the click silently hits the overlay instead of the
    browser, which is why the cursor visibly moves but nothing plays."""
    try:
        import pygetwindow as gw
    except ImportError:
        print("[PCControl] pygetwindow not installed — can't guarantee browser focus before clicking. pip install pygetwindow")
        return

    candidates = [
        t for t in gw.getAllTitles()
        if t.strip() and any(name in t.lower() for name in ("spotify", "chrome", "firefox", "edge"))
    ]
    if not candidates:
        return

    try:
        win = gw.getWindowsWithTitle(candidates[0])[0]
        if win.isMinimized:
            win.restore()
        win.activate()
        try:
            win.maximize()
        except Exception:
            pass  # maximize isn't supported on every platform/window manager, non-fatal
    except Exception as e:
        print(f"[PCControl] Couldn't focus browser window before click: {e}")


def play_music(query):
    import urllib.request
    import urllib.parse
    import re
    import sys
    import subprocess
    
    # 1. Check Internet Connection
    try:
        urllib.request.urlopen('http://www.google.com', timeout=3)
    except:
        return {"success": False, "error": "not_connected"}
        
    print(f"[PCControl] Instantly playing '{query}' on YouTube...")
    
    def play_thread():
        try:
            # We completely bypass pywhatkit because it is too slow.
            # Instead, we directly fetch the YouTube search HTML and grab the first video ID instantly.
            clean_query = urllib.parse.quote(query)
            html = urllib.request.urlopen("https://www.youtube.com/results?search_query=" + clean_query)
            video_ids = re.findall(r"watch\?v=(\S{11})", html.read().decode())
            
            if video_ids:
                url = "https://www.youtube.com/watch?v=" + video_ids[0] + "&autoplay=1"
                
                if SYSTEM == "Windows":
                    os.startfile(url)
                elif SYSTEM == "Darwin":
                    subprocess.Popen(["open", url])
                else:
                    subprocess.Popen(["xdg-open", url])
                
                # Try to forcefully maximize the browser
                import time
                time.sleep(1)
                _focus_and_maximize_browser_window()
        except Exception as e:
            print(f"[PCControl] Failed to play music instantly: {e}")
            
    import threading
    threading.Thread(target=play_thread, daemon=True).start()
    return {"success": True, "action": "play_music"}


def shutdown():
    try:
        if SYSTEM == "Windows":
            subprocess.Popen("shutdown /s /t 5", shell=True)
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
            subprocess.run("start ms-settings:bluetooth", shell=True)
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
    for ($i=0; $i -lt 50; $i++) {{ [Audio]::keybd_event(0xAE, 0, 0, 0) }}
    for ($i=0; $i -lt ($Level / 2); $i++) {{ [Audio]::keybd_event(0xAF, 0, 0, 0) }}
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


def take_note(note_content):
    import os
    import datetime
    try:
        os.makedirs("config", exist_ok=True)
        with open("config/notes.txt", "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {note_content}\n")
        return {"success": True, "note": "Note saved successfully!"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def execute(action, params):
    """Router: takes the brain's decision and calls the right function.
    Returns a result dict the main loop can use to shape Charlie's spoken reply."""
    if action in EXTRA_ACTIONS:
        return EXTRA_ACTIONS[action](params)
    
    if action == "open_app" or action == "open":
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
    elif action == "play_music":
        return play_music(params.get("query", ""))
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
    elif action == "take_note":
        return take_note(params.get("note_content", ""))
    elif action == "set_display_mode":
        return {"mode": params.get("mode", "widget"), "success": True, "action": "set_display_mode"}
    else:
        return {"success": False, "note": "no PC action needed (chat only)"}
