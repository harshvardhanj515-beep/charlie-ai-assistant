"""
contacts_module.py — lightweight local people directory.

Lets Charlie remember who's been introduced before ("say hi to Reshma")
so greetings get warmer over repeated visits instead of staying generic.
Pure JSON on disk, no external dependencies.
"""

import json
import os
import time


CONTACTS_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "contacts.json")


class ContactsManager:
    def __init__(self, path=CONTACTS_FILE):
        self.path = path
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r") as f:
                    self.data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self.data = {}
        else:
            self.data = {}

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent=2)

    def get(self, name):
        return self.data.get(name.strip().lower())

    def touch(self, name):
        """Record that this person was just interacted with — call every
        time greet_person fires, whether or not they're already known."""
        key = name.strip().lower()
        entry = self.data.get(key, {
            "name": name.strip().title(),
            "first_met": time.time(),
            "visits": 0,
            "notes": "",
        })
        entry["visits"] += 1
        entry["last_seen"] = time.time()
        self.data[key] = entry
        self._save()
        return entry

    def set_notes(self, name, notes):
        entry = self.touch(name)
        entry["notes"] = notes
        self.data[name.strip().lower()] = entry
        self._save()

    def all_names(self):
        return [v["name"] for v in self.data.values()]
