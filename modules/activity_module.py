"""
Activity monitor: periodically checks the active window title to see what the user is doing.
"""

import time
import threading
import ctypes
import random
import sys

sys.path.append("..")
from config.settings import ACTIVITY_ENABLED, ACTIVITY_CHECK_INTERVAL_SECONDS, ACTIVITY_PROACTIVE_CHANCE

class ActivityMonitor:
    def __init__(self, on_activity_change=None):
        self.on_activity_change = on_activity_change
        self.running = False
        self._thread = None
        self.last_window_title = ""

    def start(self):
        if not ACTIVITY_ENABLED:
            return
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[Activity] Activity monitoring started.")

    def stop(self):
        self.running = False
        print("[Activity] Activity monitoring stopped.")

    def get_active_window_title(self):
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value if buf.value else ""

    def _loop(self):
        sustained_time = 0
        while self.running:
            time.sleep(ACTIVITY_CHECK_INTERVAL_SECONDS)
            title = self.get_active_window_title()
            
            if title:
                if title == self.last_window_title:
                    sustained_time += ACTIVITY_CHECK_INTERVAL_SECONDS
                    # Trigger proactive chat only after 60 seconds of sustained focus on one window
                    if sustained_time == 60:
                        if random.random() < ACTIVITY_PROACTIVE_CHANCE:
                            if self.on_activity_change:
                                self.on_activity_change(title)
                else:
                    self.last_window_title = title
                    sustained_time = 0

if __name__ == "__main__":
    def print_activity(title):
        print(f"[Test] User switched to: {title}")
    
    monitor = ActivityMonitor(on_activity_change=print_activity)
    monitor.start()
    print("Monitoring for 60 seconds... (Ctrl+C to stop early)")
    try:
        time.sleep(60)
    except KeyboardInterrupt:
        pass
    monitor.stop()
