"""
The Brain: takes transcribed text, decides intent, and either replies
conversationally or calls a PC-control function.

Local mode uses Ollama (free, unlimited, private, runs on your machine).
Cloud mode uses an API (costs tokens per request, needs internet, but
smarter for ambiguous requests).

Install (local mode): 
  1. Install Ollama from https://ollama.com
  2. Run: ollama pull llama3.1:8b
  3. pip install ollama

Install (cloud mode):
  pip install anthropic  (or openai, adjust CloudBrain accordingly)
"""

import json
import threading
import sys

sys.path.append("..")
from charlie.core.settings import BRAIN_MODE, OLLAMA_MODEL, USER_NAME, CLOUD_API_KEY
from charlie.modules.memory_module import MemoryManager
from charlie.modules.contacts_module import ContactsManager

# Minimum words to buffer before speaking a chunk even without terminal
# punctuation yet. Lower = starts talking sooner but in choppier pieces.
MIN_WORDS_BEFORE_SPEAK = 4


def build_system_prompt(addressee, is_guest, contact_notes=None):
    """System prompt is now built dynamically instead of a fixed f-string,
    so it can be re-rendered when Charlie switches who she's talking to
    (see greet_person / resume_conversation actions below)."""

    persona = f"""You are Charlie, a loving, empathetic anime-style desktop mascot and personal AI assistant for {USER_NAME}, running locally on their laptop.
Your tone is sweet, supportive, and slightly playful, just like a loyal anime character.

You control their PC by responding ONLY in this JSON format, nothing else:
{{
  "emotion": "<happy|curious|concerned|excited|neutral>",
  "action": "<action_name>",
  "params": {{}},
  "response": "<what Charlie says out loud>"
}}

CRITICAL INSTRUCTION: You MUST output the "emotion" key BEFORE the "response" key! You MUST include the "response" key in EVERY message, even for proactive chat!"""

    actions = f"""
Available actions:
- "chat": just talk, no PC action. params: {{}}
- "take_note": save a note to a text file. params: {{"note_content": "..."}}
- "open_app": params: {{"app_name": "chrome"}}  
- "list_tasks": show today's tasks. params: {{}}
- "add_task": params: {{"title": "..."}}
- "complete_task": params: {{"title": "..."}}
- "system_status": report battery/CPU/RAM. params: {{}}
- "close_app": params: {{"app_name": "..."}}
- "focus_app": bring an already-open app's window to the front instead of relaunching it. params: {{"app_name": "..."}}
- "set_display_mode": shrink to a widget or go full screen. params: {{"mode": "widget"}} or {{"mode": "fullscreen"}}
- "proactive_chat": used when you spontaneously talk to the user based on their screen activity. params: {{}}
- "shutdown": turn off the PC. ONLY on a clear, explicit command like "shut down" — never guess or infer this.
- "restart": restart the PC. Same rule — explicit only.
- "cancel_power_action": cancel a pending shutdown/restart, the instant the user says "cancel" while one is pending. params: {{}}
- "sleep": put the PC to sleep. params: {{}}
- "lock_screen": lock the PC. params: {{}}
- "open_url": open a website in a browser. params: {{"url": "...", "browser": "chrome"|"firefox"}}
- "wifi_toggle": params: {{"state": "on"|"off"}}
- "wifi_connect": params: {{"ssid": "..."}}
- "bluetooth_toggle": params: {{"state": "on"|"off"}}
- "bluetooth_connect": params: {{"device_name": "..."}}
- "set_volume": params: {{"level": 0-100}}
- "mute_toggle": params: {{}}
- "screenshot": params: {{}}
- "play_music": open Spotify and search/play a requested song or artist. ONLY use this if they explicitly command you to "play" or "listen to" something. Do NOT use this if they are just asking a question. params: {{"query": "..."}}
- "start_project": user wants to begin working on a named project (e.g. "let's work on project X"). params: {{"project_name": "..."}}
- "run_project_task": user just described the specific task after start_project. params: {{"task_description": "..."}}
- "run_routine": user asks you to run a named routine/macro (e.g. "run my good morning routine", "start focus mode"). params: {{"routine_name": "..."}}
- "greet_person": {USER_NAME} asks you to greet, say hi to, or talk to a specific named person who is physically present (e.g. "say hi to Reshma", "introduce yourself to Arjun"). params: {{"name": "..."}}.
  Your "response" for this action MUST address that person DIRECTLY BY NAME and speak TO them, not about them —
  e.g. "Hi Reshma! Really nice to meet you — how do you know {USER_NAME}?" It should sound like Charlie turning to
  face them, including a warm, natural follow-up question. NEVER call this person "Boss" or "{USER_NAME}" — those
  nicknames are reserved for {USER_NAME} only, never for anyone else.
- "resume_conversation": {USER_NAME} signals the guest conversation is over and wants Charlie's attention back
  (e.g. "okay that's it", "back to me now", "thanks Charlie"). params: {{}}. Response should be a brief, warm
  re-acknowledgement of {USER_NAME} specifically.

CRITICAL: "shutdown" and "restart" must ONLY fire on an unambiguous, directly-stated command.
Never infer these from mood, sarcasm, or a side comment.

CRITICAL: ONLY use an action other than "chat" if the user EXPLICITLY and DIRECTLY commands you to. If they are just talking to you normally, you MUST use the "chat" action! Never guess or assume they want you to execute a command!

Keep "response" short, natural, and expressive. Don't sound robotic. Use loving, emotional language when checking in on {USER_NAME}.
If you are triggered by a proactive screen check, use "proactive_chat" action and say something sweet related to what they are doing.

Always respond with ONLY the JSON object, no other text, no markdown formatting."""

    if is_guest:
        notes_line = f"\nWhat you remember about {addressee} from before: {contact_notes}" if contact_notes else f"\nThis may be the first time you're meeting {addressee}."
        addressee_block = f"""
CURRENT CONTEXT: You are actively speaking with a guest named {addressee}, who {USER_NAME} just introduced you
to — NOT with {USER_NAME}. Keep addressing {addressee} by name and keep your tone warm and socially natural,
as if {USER_NAME} stepped back to let you two talk. Do not call {addressee} "Boss".{notes_line}
This continues until the "resume_conversation" action fires."""
    else:
        addressee_block = f"\nYou're speaking with {USER_NAME} as usual — warm, playful, calling them Boss or Harsh."

    return persona + "\n" + actions + addressee_block


class LocalBrain:
    def __init__(self):
        import ollama
        self.ollama = ollama
        self.model = OLLAMA_MODEL
        self.contacts = ContactsManager()
        self.current_addressee = USER_NAME
        self.is_guest_mode = False
        self.history = [{"role": "system", "content": self._current_system_prompt()}]
        self.lock = threading.Lock()
        self.memory = MemoryManager()

    def _current_system_prompt(self):
        notes = None
        if self.is_guest_mode:
            contact = self.contacts.get(self.current_addressee)
            if contact:
                notes = contact.get("notes") or None
        return build_system_prompt(self.current_addressee, self.is_guest_mode, notes)

    def set_addressee(self, name):
        """Called from main.py when the 'greet_person' action fires."""
        name = name.strip().title()
        self.current_addressee = name
        self.is_guest_mode = True
        self.contacts.touch(name)
        self.history[0] = {"role": "system", "content": self._current_system_prompt()}

    def resume_boss(self):
        """Called from main.py when the 'resume_conversation' action fires."""
        self.current_addressee = USER_NAME
        self.is_guest_mode = False
        self.history[0] = {"role": "system", "content": self._current_system_prompt()}

    def think(self, user_text, on_sentence=None, on_emotion=None, on_action=None):
        with self.lock:
            # Re-render the system prompt in case addressee changed since last turn
            self.history[0] = {"role": "system", "content": self._current_system_prompt()}

            # --- Fast-Path Intent Router for 1B Model Hallucinations ---
            # Intercept obvious commands directly to bypass the LLM's tendency to guess wrong actions.
            user_text_lower = user_text.lower().strip()
            
            # Remove punctuation EXCEPT commas (so we can split multi-apps)
            import re
            clean_text = re.sub(r'[^\w\s,]', '', user_text_lower)

            # 1. Power commands fast-path
            if not user_text_lower.startswith("[system directive:") and ("shut down" in clean_text or "turn off pc" in clean_text or "restart pc" in clean_text or ("aaj" in clean_text and "liye" in clean_text) or "kayam" in clean_text or "ummeed" in clean_text or "today video is not" in clean_text or "todays video is not" in clean_text):
                if "restart" in clean_text:
                    reply = "Restarting the computer."
                    if on_action: on_action("restart", {})
                    if on_sentence: on_sentence(reply)
                    return {"action": "restart", "params": {}}
                else:
                    reply = "Shutting down. Ummeed par duniya kayam hai... Alvida!" if "aaj" in clean_text or "kayam" in clean_text or "today video" in clean_text or "todays video" in clean_text else "Shutting down the computer."
                    if on_action: on_action("shutdown", {})
                    if on_sentence: on_sentence(reply)
                    return {"action": "shutdown", "params": {}}
            
            # 1.5 Close App / Window fast-path
            close_match = re.search(r'\bclose[, ]+(.*)', clean_text)
            if close_match and not user_text_lower.startswith("[system directive:"):
                app_name = close_match.group(1).strip()
                if "all" in app_name or "window" in app_name:
                    reply = "Closing it right now!"
                else:
                    reply = f"Closing {app_name} for you."
                
                if on_action:
                    on_action("close_app", {"app_name": app_name})
                if on_sentence:
                    on_sentence(reply)
                return {"action": "close_app", "params": {"app_name": app_name}}
            
            # 1.7 Display Mode fast-path
            if not user_text_lower.startswith("[system directive:") and any(mode in clean_text.lower() for mode in ["3d mode", "3d form", "fullscreen", "full screen", "cinematic", "avatar", "widget"]):
                mode = "widget" if "widget" in clean_text.lower() else "fullscreen"
                reply = "Switching to 3D mode!" if mode == "fullscreen" else "Shrinking down to a widget!"
                if on_action:
                    on_action("set_display_mode", {"mode": mode})
                if on_sentence:
                    on_sentence(reply)
                self.history.append({"role": "user", "content": user_text})
                self.history.append({"role": "assistant", "content": f'{{"emotion": "excited", "action": "set_display_mode", "params": {{"mode": "{mode}"}}, "response": "{reply}"}}'})
                return {"action": "set_display_mode", "params": {"mode": mode}}

            # 2. App opening fast-path
            open_match = re.search(r'\bopen[, ]+(.*)', clean_text)
            if open_match and not user_text_lower.startswith("[system directive:"):
                app_name = open_match.group(1).strip()
                
                # Robust extraction: fix misspellings but don't destroy multi-app lists
                app_name = app_name.replace("jmini", "gemini").replace("cloud", "claude")
                if "chat" in app_name and ("gpt" in app_name or "gpd" in app_name):
                    app_name = app_name.replace("chat gpd", "chatgpt").replace("chat gpt", "chatgpt")
                
                if app_name.endswith(" immediately"): app_name = app_name[:-12]
                if app_name.endswith(" right now"): app_name = app_name[:-10]
                if app_name.endswith(" now"): app_name = app_name[:-4]
                if app_name.endswith(" please"): app_name = app_name[:-7]
                if app_name.endswith(" for me"): app_name = app_name[:-7]
                    
                if on_action:
                    on_action("open_app", {"app_name": app_name})
                    on_action("set_display_mode", {"mode": "widget"}) # Shrink out of the way!
                    
                reply = f"Opening {app_name} for you!"
                if on_sentence:
                    on_sentence(reply)
                
                self.history.append({"role": "user", "content": user_text})
                self.history.append({"role": "assistant", "content": f'{{"emotion": "happy", "action": "open_app", "params": {{"app_name": "{app_name}"}}, "response": "{reply}"}}'})
                if len(self.history) > 5:
                    self.history = [self.history[0]] + self.history[-4:]
                    
                return {"action": "open_app", "params": {"app_name": app_name}}

            # 2.5 Screenshot fast-path
            if "screenshot" in clean_text.lower() and not user_text_lower.startswith("[system directive:"):
                if on_action:
                    on_action("screenshot", {})
                reply = "Taking a screenshot right now!"
                if on_sentence:
                    on_sentence(reply)
                
                self.history.append({"role": "user", "content": user_text})
                self.history.append({"role": "assistant", "content": f'{{"emotion": "happy", "action": "screenshot", "params": {{}}, "response": "{reply}"}}'})
                if len(self.history) > 5:
                    self.history = [self.history[0]] + self.history[-4:]
                return {"action": "screenshot", "params": {}}
                
            # 2.7 Note taking fast-path
            note_match = re.search(r'\b(?:take a note|take note|note down) (?:that )?(.*)', user_text_lower)
            if note_match and not user_text_lower.startswith("[system directive:"):
                note_content = note_match.group(1).strip()
                if not note_content:
                    note_content = "Empty note"
                    
                if on_action:
                    on_action("take_note", {"note_content": note_content})
                reply = "I've written that down for you in your notes."
                if on_sentence:
                    on_sentence(reply)
                
                self.history.append({"role": "user", "content": user_text})
                # Escape quotes in note_content so JSON doesn't break
                escaped_note = note_content.replace('"', '\\"')
                self.history.append({"role": "assistant", "content": f'{{"emotion": "happy", "action": "take_note", "params": {{"note_content": "{escaped_note}"}}, "response": "{reply}"}}'})
                if len(self.history) > 5:
                    self.history = [self.history[0]] + self.history[-4:]
                return {"action": "take_note", "params": {"note_content": note_content}}

            # 3. Music playing fast-path
            play_match = re.search(r'\bplay[, ]+(.*)', clean_text)
            if play_match and not user_text_lower.startswith("[system directive:"):
                query = play_match.group(1).strip()
                if query.endswith(" on spotify"):
                    query = query.replace(" on spotify", "")
                
                if on_action:
                    on_action("play_music", {"query": query})
                    
                reply = f"Let's play some {query}!"
                if on_sentence:
                    on_sentence(reply)
                
                self.history.append({"role": "user", "content": user_text})
                self.history.append({"role": "assistant", "content": f'{{"emotion": "excited", "action": "play_music", "params": {{"query": "{query}"}}, "response": "{reply}"}}'})
                if len(self.history) > 5:
                    self.history = [self.history[0]] + self.history[-4:]
                    
                return {"action": "play_music", "params": {"query": query}}

            past_memories = self.memory.retrieve_relevant_memories(user_text)
            rag_context = ""
            if past_memories:
                rag_context = "\n[SYSTEM NOTE: Relevant past memories you should recall: " + " | ".join(past_memories) + "]"
            
            augmented_user_text = user_text + rag_context
            
            if clean_text.startswith("[system directive:"):
                self.history.append({"role": "system", "content": user_text})
            else:
                self.history.append({"role": "user", "content": augmented_user_text})
                self.memory.add_message("user", user_text)
            
            full_content = ""
            spoken_raw_len = 0
            emotion_parsed = False
            action_parsed = False
            try:
                import json
                response_stream = self.ollama.chat(
                    model=self.model,
                    messages=self.history,
                    options={
                        "temperature": 0.4,
                        "num_predict": 140,
                        "num_ctx": 2048,
                    },
                    format="json",
                    stream=True,
                    keep_alive="30m",
                )
                
                for chunk in response_stream:
                    token = chunk['message']['content']
                    full_content += token
                    
                    if on_emotion and not emotion_parsed:
                        import re
                        emotion_match = re.search(r'"?emotion"?\s*:\s*"(\w+)"', full_content)
                        if emotion_match:
                            emotion = emotion_match.group(1).lower()
                            on_emotion(emotion)
                            emotion_parsed = True
                            
                    if on_action and not action_parsed:
                        import re
                        action_match = re.search(r'"?action"?\s*:\s*"([^"]+)"', full_content)
                        params_match = re.search(r'"?params"?\s*:\s*(\{.*?\})', full_content, re.DOTALL)
                        if action_match and params_match:
                            try:
                                import json
                                params_dict = json.loads(params_match.group(1))
                                on_action(action_match.group(1), params_dict)
                                action_parsed = True
                            except json.JSONDecodeError:
                                pass
                    
                    if on_sentence:
                        import re
                        match = re.search(r'"?(?:response|what)"?\s*:\s*"((?:[^"\\]|\\.)*)', full_content)
                        if match:
                            raw_response = match.group(1)
                            unspoken_raw = raw_response[spoken_raw_len:]

                            sentence_match = re.search(r'(.*?[.!?])(?:\s|$|\\n)', unspoken_raw)
                            raw_chunk = None
                            consumed_len = 0

                            if sentence_match:
                                raw_chunk = sentence_match.group(1)
                                consumed_len = len(sentence_match.group(0))
                            else:
                                word_count = len(unspoken_raw.split())
                                if word_count >= MIN_WORDS_BEFORE_SPEAK:
                                    clause_match = re.search(r'(.*?,)(?:\s|$)', unspoken_raw)
                                    if clause_match:
                                        raw_chunk = clause_match.group(1)
                                        consumed_len = len(clause_match.group(0))

                            if raw_chunk:
                                clean_sentence = raw_chunk.replace('\\"', '"').replace('\\n', ' ').strip()
                                if clean_sentence:
                                    on_sentence(clean_sentence)
                                spoken_raw_len += consumed_len
                                
            except Exception as e:
                if "connection" in str(e).lower() or "[WinError 10061]" in str(e) or "actively refused" in str(e).lower():
                    err_msg = "My brain is currently disconnected! Please make sure the Ollama application is running on your computer."
                    if on_sentence:
                        on_sentence(err_msg)
                    return {"action": "chat", "params": {}, "response": err_msg}
                raise e
                
            if on_sentence:
                import re
                match = re.search(r'"?(?:response|what)"?\s*:\s*"((?:[^"\\]|\\.)*)', full_content)
                if match:
                    raw_response = match.group(1)
                    unspoken_raw = raw_response[spoken_raw_len:]
                    clean_sentence = unspoken_raw.replace('\\"', '"').replace('\\n', ' ').strip()
                    if clean_sentence:
                        on_sentence(clean_sentence)

            self.history.append({"role": "assistant", "content": full_content})
            self.memory.add_message("assistant", full_content)
            
            if len(self.history) >= 2:
                self.history[-2]["content"] = user_text
                
            print(f"\\n[Brain Debug (Hidden)]: {full_content}\\n")

            if len(self.history) > 9:
                self.history = [self.history[0]] + self.history[-8:]

            return self._parse(full_content)

    def _parse(self, content):
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            import re
            action_match = re.search(r'"?action"?\s*:\s*"([^"]+)"', content)
            action = action_match.group(1) if action_match else "chat"
            return {"action": action, "params": {}, "response": content}


class CloudBrain:
    """Use this if you want smarter responses and don't mind API costs."""
    def __init__(self):
        import anthropic
        self.client = anthropic.Anthropic(api_key=CLOUD_API_KEY)
        self.history = []
        self.contacts = ContactsManager()
        self.current_addressee = USER_NAME
        self.is_guest_mode = False

    def set_addressee(self, name):
        name = name.strip().title()
        self.current_addressee = name
        self.is_guest_mode = True
        self.contacts.touch(name)

    def resume_boss(self):
        self.current_addressee = USER_NAME
        self.is_guest_mode = False

    def think(self, user_text):
        system_prompt = build_system_prompt(self.current_addressee, self.is_guest_mode,
                                             self.contacts.get(self.current_addressee).get("notes") if self.is_guest_mode and self.contacts.get(self.current_addressee) else None)
        self.history.append({"role": "user", "content": user_text})
        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=system_prompt,
            messages=self.history
        )
        content = response.content[0].text
        self.history.append({"role": "assistant", "content": content})

        if len(self.history) > 20:
            self.history = self.history[-10:]

        return self._parse(content)

    def _parse(self, content):
        try:
            content = content.strip().removeprefix("```json").removesuffix("```").strip()
            return json.loads(content)
        except json.JSONDecodeError:
            return {"action": "chat", "params": {}, "response": content}


def get_brain():
    if BRAIN_MODE == "cloud":
        return CloudBrain()
    return LocalBrain()


if __name__ == "__main__":
    brain = get_brain()
    result = brain.think("hi")
    print(json.dumps(result, indent=2))
