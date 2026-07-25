"""
project_module_auto.py

Fully automated project workflow: no browser, no manual copy/paste.

    You: "Let's work on project Charlie-Avatar"
    Charlie: "What do you need help with?"
    You: describe the task
    Charlie: calls the Anthropic API directly, gets back a ready-to-use
             Antigravity prompt, puts it on your clipboard, and (optionally)
             types it straight into Antigravity for you.

Why API instead of driving a browser: automating a ChatGPT/Gemini/Claude
*webpage* (clicking, typing into their UI, scraping the reply) is fragile —
it breaks whenever they change their page and often gets blocked by
anti-automation protections. Calling the API is the same AI, but a stable,
supported way to do it programmatically. Your project already has an
Anthropic client wired up in CloudBrain, so this reuses CLOUD_API_KEY.

Install: pip install anthropic pyautogui
"""

import sys
import time

sys.path.append("..")
from charlie.core.settings import CLOUD_API_KEY
from charlie.modules.pc_control_extensions import clipboard_set
from charlie.modules.pc_control_module import open_app

PROMPT_TEMPLATE = """You are helping turn a task description into a precise, actionable prompt
for Antigravity, an AI coding assistant, for the project "{project_name}".

Task: {task_description}

Write ONLY the prompt to give Antigravity — clear, specific instructions, naming exact
files or functions to touch where relevant. No preamble, no markdown fences, no
commentary — just the prompt text itself, ready to paste in as-is."""


class AutoProjectSession:
    def __init__(self):
        import anthropic
        self.client = anthropic.Anthropic(api_key=CLOUD_API_KEY)
        self.active = False
        self.project_name = None

    def start(self, project_name):
        self.active = True
        self.project_name = project_name
        return f"Got it, Boss. What do you need help with on {project_name}?"

    def run_task(self, task_description, auto_type_into_antigravity=False):
        if not self.active:
            return None, "We're not mid-setup on a project — say 'let's work on project X' first."

        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{
                "role": "user",
                "content": PROMPT_TEMPLATE.format(
                    project_name=self.project_name,
                    task_description=task_description,
                ),
            }],
        )
        prompt_text = response.content[0].text.strip()
        clipboard_set({"text": prompt_text})
        self.active = False

        if auto_type_into_antigravity:
            self._deliver_to_antigravity(prompt_text)
            return prompt_text, "Done — I've generated the prompt and typed it into Antigravity for you."

        return prompt_text, "Here's the prompt — it's on your clipboard, ready to paste into Antigravity."

    def _deliver_to_antigravity(self, prompt_text):
        # CAUTION: this types into whatever window has focus after the delay
        # below. If Antigravity doesn't grab focus in time, this will type
        # into the wrong app. Test with auto_type_into_antigravity=False
        # first, and only flip it on once you've confirmed the timing works
        # reliably on your machine.
        import pyautogui
        open_app({"app_name": "antigravity"})
        time.sleep(3)  # tune this — needs to comfortably exceed Antigravity's launch time
        pyautogui.write(prompt_text, interval=0.005)
