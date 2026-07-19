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
from config.settings import BRAIN_MODE, OLLAMA_MODEL, USER_NAME, CLOUD_API_KEY
from modules.memory_module import MemoryManager
from modules.contacts_module import ContactsManager

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

    def think(self, user_text, on_sentence=None, on_emotion=None):
        with self.lock:
            # Re-render the system prompt in case addressee changed since last turn
            self.history[0] = {"role": "system", "content": self._current_system_prompt()}

            # --- Fast-Path Intent Router for 1B Model Hallucinations ---
            # Intercept obvious commands directly to bypass the LLM's tendency to guess wrong actions.
            user_text_lower = user_text.lower().strip()
            
            # 2. App opening fast-path
            # Catch "open X", "please open X", "can you open X", "could you please open X"
            if "open " in user_text_lower:
                app_name = user_text_lower.split("open ")[-1].strip()
                # Strip trailing punctuation
                import string
                app_name = app_name.rstrip(string.punctuation)
                
                # Fix Whisper's common transcription errors for ChatGPT
                if "chat" in app_name and ("gpt" in app_name or "gpd" in app_name):
                    app_name = "chatgpt"
                    
                reply = f"Opening {app_name} for you!"
                if on_sentence:
                    on_sentence(reply)
                
                self.history.append({"role": "user", "content": user_text})
                self.history.append({"role": "assistant", "content": f'{{"emotion": "happy", "action": "open_app", "params": {{"app_name": "{app_name}"}}, "response": "{reply}"}}'})
                if len(self.history) > 5:
                    self.history = [self.history[0]] + self.history[-4:]
                    
                return {"action": "open_app", "params": {"app_name": app_name}}

            past_memories = self.memory.retrieve_relevant_memories(user_text)
            rag_context = ""
            if past_memories:
                rag_context = "\n[SYSTEM NOTE: Relevant past memories you should recall: " + " | ".join(past_memories) + "]"
            
            augmented_user_text = user_text + rag_context
            self.history.append({"role": "user", "content": augmented_user_text})
            
            self.memory.add_message("user", user_text)
            
            try:
                response_stream = self.ollama.chat(
                    model=self.model,
                    messages=self.history,
                    options={
                        "temperature": 0.4,
                        "num_predict": 220,
                        "num_ctx": 2048,
                    },
                    format="json",
                    stream=True,
                    keep_alive="30m",
                )
            except Exception as e:
                if "connection" in str(e).lower() or "[WinError 10061]" in str(e):
                    err_msg = "My brain is currently disconnected! Please make sure the Ollama application is running on your computer."
                    if on_sentence:
                        on_sentence(err_msg)
                    return {"action": "chat", "params": {}, "response": err_msg}
                raise e
            
            full_content = ""
            spoken_raw_len = 0
            emotion_parsed = False
            
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
