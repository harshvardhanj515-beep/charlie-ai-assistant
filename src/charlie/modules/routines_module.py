"""
routines_module.py — named multi-step voice macros.

"Hey Charlie, run my good morning routine" fires a predefined sequence of
pc_control actions in order. Define routines in config/settings.py under
ROUTINES so you can edit them without touching code.

Example settings.py entry:

    ROUTINES = {
        "good morning": [
            ("open_url", {"url": "https://mail.google.com", "browser": "chrome"}),
            ("system_status", {}),
        ],
        "focus mode": [
            ("close_app", {"app_name": "chrome"}),
            ("mute_toggle", {}),
            ("set_display_mode", {"mode": "widget"}),
        ],
    }
"""

import sys
sys.path.append("..")
from charlie.core.settings import ROUTINES


def run_routine(routine_name, execute_fn):
    key = routine_name.strip().lower()
    steps = ROUTINES.get(key)

    if not steps:
        available = ", ".join(ROUTINES.keys()) or "none configured yet"
        return f"I don't have a routine called '{routine_name}'. I know: {available}."

    # Routines bypass main.py's shutdown/restart confirmation window since
    # they run every step back-to-back with no chance to say "cancel" in
    # between. Rather than let that safety net get silently skipped just
    # because an action came from a routine instead of a direct command,
    # block it outright here.
    BLOCKED_IN_ROUTINES = {"shutdown", "restart"}

    failures = []
    for action, params in steps:
        if action in BLOCKED_IN_ROUTINES:
            print(f"[Routines] Skipped '{action}' — not allowed inside a routine, say it directly instead.")
            failures.append(action)
            continue
        try:
            result = execute_fn(action, params)
            if not result.get("success", True):
                failures.append(action)
        except Exception as e:
            print(f"[Routines] Step '{action}' failed: {e}")
            failures.append(action)

    if failures:
        return f"Ran the {routine_name} routine, but {', '.join(failures)} didn't work — check the console."
    return f"Done — {routine_name} routine complete."
