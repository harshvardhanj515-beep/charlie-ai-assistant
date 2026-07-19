# Charlie - Personal AI Desktop Assistant

## What this actually is right now
A working local voice-assistant skeleton: wake word -> speech-to-text ->
local LLM decides what you want -> does it (open apps, check tasks, report
system status) -> speaks back -> animated desktop avatar reflects its state.
Optional camera-based check-in, off by default.

This is a real first version, not a mockup - every module has a
`if __name__ == "__main__":` block so you can test each piece standalone
before running the whole thing together. **Test in this order.**

## Setup (Windows - adjust for Mac/Linux where noted)

### 1. Install Python 3.10 or 3.11
(3.12 can have dependency issues with some of these packages as of now -
3.10/3.11 is the safer bet). Get it from python.org, check "Add to PATH"
during install.

### 2. Create a virtual environment (keeps this project's packages separate)
```
cd charlie
python -m venv venv
venv\Scripts\activate        (Windows)
source venv/bin/activate     (Mac/Linux)
```

### 3. Install dependencies
```
pip install -r requirements.txt
```
This will take a while - faster-whisper, deepface, and PyQt5 are sizeable.
If deepface/opencv fail to install and you don't want the camera feature
yet, set CAMERA_ENABLED = False in config/settings.py and remove
opencv-python/deepface/tf-keras from requirements.txt before installing.

### 4. Install Ollama (for the local brain)
Download from https://ollama.com, install it, then run:
```
ollama pull llama3.1:8b
```
This downloads a ~4.7GB model. Needs roughly 8GB RAM free to run smoothly.
If your laptop has less RAM, use a smaller model instead:
```
ollama pull llama3.2:3b
```
and change OLLAMA_MODEL in config/settings.py to match.

### 5. Get avatar sprites
Make an avatar in VRoid Studio (free) and export 4 static poses as PNGs,
OR download a free desktop-mascot sprite pack from itch.io. Name the files
exactly: idle.png, listening.png, talking.png, talking2.png, thinking.png
Place them in: charlie/assets/avatar/

## Testing order (IMPORTANT - do this before running main.py)

Test each piece alone first. This tells you exactly which component to
debug if something's wrong, instead of guessing across five systems at once.

```
python modules/tts_module.py          # Should hear Charlie say a test line
python modules/stt_module.py          # Should transcribe what you say
python modules/brain_module.py        # Should print a JSON decision for "hi"
python modules/avatar_module.py       # Should show the avatar cycling states
python modules/wake_word_module.py    # Should detect "hey jarvis" (stand-in wake word)
```

Only once all five pass individually:
```
python main.py
```

## Known limitations, on purpose (read before you get frustrated)

- **Wake word is "hey jarvis" as a placeholder**, not "Charlie" - training
  a custom wake word model is a separate step (openWakeWord has a Colab
  notebook for this, search "openWakeWord custom model training"). Swap
  the model path in wake_word_module.py once trained.
- **The avatar is 2D sprite-swapping, not Live2D rigging.** Looks fine,
  isn't as fluid as VTuber-style animation. Upgrading to Live2D is a
  separate, larger task (needs the Cubism SDK and a rigged model file).
- **Emotion detection WILL misread you sometimes.** Concentrating often
  reads as "angry" or "sad" to these models. It's tuned to only speak up
  rarely and only on high-confidence, narrow cases - adjust
  EMOTION_CONFIDENCE_THRESHOLD and the emotion list in main.py if it's
  ever annoying, don't just live with it.
- **Local brain (llama3.1:8b) is noticeably less sharp than Claude/GPT-4**
  for ambiguous or complex requests. That's the trade for $0 cost and full
  privacy. Switch BRAIN_MODE to "cloud" in settings.py if you want a
  smarter Charlie and don't mind small per-use API costs.
- **First response after starting Charlie will be slower** (models loading
  into memory). Every response after that is fast, since nothing reloads.

## Adding new PC actions
Open modules/pc_control_module.py, add a new function, then add it to the
`execute()` router at the bottom AND add it to the action list in
modules/brain_module.py's SYSTEM_PROMPT so the brain knows it exists.
Keep this list deliberate - don't wire in anything you wouldn't want
triggered by a misheard voice command.
