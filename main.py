"""
Charlie - main loop.

Flow: wake word -> avatar shows "listening" -> record & transcribe ->
avatar shows "thinking" -> brain decides action + reply -> PC control
executes action -> avatar shows "talking" -> TTS speaks -> back to idle.

After replying, Charlie listens for a short follow-up window WITHOUT
requiring the wake word again (see CONTINUOUS_CONVERSATION_ENABLED in
settings.py) — this is what makes back-and-forth conversation feel
natural instead of needing "hey jarvis" before every single sentence.

Camera/emotion monitoring runs independently in the background and can
interject only in narrow, low-frequency, non-annoying cases (see
handle_emotion_event below) - it never talks over you or interrupts
an active conversation. It never states a detected emotion as fact —
only ever asks a casual, curious question.

RUN THIS FROM THE charlie/ DIRECTORY:  python main.py
"""

import os
import sys
import time

# --- GPU acceleration for QtWebEngine (fixes choppy avatar rendering) ---
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--ignore-gpu-blacklist --enable-gpu-rasterization --enable-native-gpu-memory-buffers --enable-webgl"
)

from config.settings import (
    USER_NAME, CAMERA_ENABLED, ACTIVITY_ENABLED,
    CONTINUOUS_CONVERSATION_ENABLED, CONTINUOUS_CONVERSATION_WINDOW_SECONDS,
    EMOTION_PROACTIVE_CHANCE,
)
from modules.wake_word_module import WakeWordDetector
from modules.stt_module import SpeechToText
from modules.brain_module import get_brain
from modules.tts_module import get_tts_engine
from modules.pc_control_module import execute
from modules.avatar_module import AvatarController
from modules.activity_module import ActivityMonitor
from modules.project_module_auto import AutoProjectSession
from modules.routines_module import run_routine

if CAMERA_ENABLED:
    from modules.camera_module import EmotionMonitor

from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction, QShortcut, QStyle
from PyQt5.QtGui import QKeySequence
from PyQt5.QtCore import Qt

def create_shutdown_mechanism(app, avatar, wake_detector, emotion_monitor, activity_monitor):
    def full_shutdown():
        print("\n[Shutdown] Quit requested — stopping all threads...")
        wake_detector.stop_requested = True
        if emotion_monitor:
            emotion_monitor.stop()
        if activity_monitor:
            activity_monitor.stop()
        avatar.close()
        app.quit()
        import threading, os
        def force_exit():
            import time
            time.sleep(2)
            os._exit(0)
        threading.Thread(target=force_exit, daemon=True).start()

    tray = QSystemTrayIcon(app)
    tray.setIcon(app.style().standardIcon(QStyle.SP_ComputerIcon))
    tray.setToolTip("Charlie is running")
    menu = QMenu()
    quit_action = QAction("Quit Charlie")
    quit_action.triggered.connect(full_shutdown)
    menu.addAction(quit_action)
    tray.setContextMenu(menu)
    tray.show()

    shortcut = QShortcut(QKeySequence("Ctrl+Shift+Q"), avatar)
    shortcut.setContext(Qt.ApplicationShortcut)
    shortcut.activated.connect(full_shutdown)

    return tray


def format_pc_result_for_speech(action, result):
    """Turns a raw PC-control result into something natural for Charlie to say,
    layered on top of whatever the brain already wrote in its 'response' field."""
    if action == "system_status":
        return f"Battery is at {result['battery']}. CPU is at {result['cpu_percent']} percent, RAM at {result['ram_percent']} percent."
    if action == "list_tasks":
        tasks = result.get("tasks", [])
        if not tasks:
            return "You have no pending tasks. Nicely done."
        titles = ", ".join(t["title"] for t in tasks[:5])
        return f"You have {len(tasks)} tasks pending: {titles}."
    if action == "play_music":
        if not result.get("success"):
            if result.get("error") == "not_connected":
                return "You are not connected to the internet right now, so I can't search for that song!"
            return "I couldn't open Spotify right now, something went wrong!"
    if action == "open_app" and not result.get("success"):
        return "Oops! I tried to open that, but I couldn't find it installed on your computer. Just add it to my path in the settings file!"
    return None  # fall back to the brain's own "response" text


def main():
    print("=" * 50)
    print(f"  CHARLIE - Personal Assistant for {USER_NAME}")
    print("=" * 50)

    print("\n[Startup] Loading modules (this happens once, subsequent")
    print("responses will be fast since models stay loaded in memory)...\n")

    from PyQt5.QtWidgets import QApplication, QMessageBox
    sys.argv.append("--disable-gpu-shader-disk-cache")
    app = QApplication(sys.argv)
    
    def gui_excepthook(exctype, value, tb):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Charlie - Fatal Error")
        msg.setText(f"Charlie encountered a fatal error and must close:\n\n{value}")
        msg.setInformativeText("Please make sure all required files, models, and images are in their correct folders.")
        msg.exec_()
        sys.__excepthook__(exctype, value, tb)
        
    sys.excepthook = gui_excepthook
    
    wake_detector = WakeWordDetector()
    stt = SpeechToText()
    brain = get_brain()
    tts = get_tts_engine()
    avatar = AvatarController()
    project_session = AutoProjectSession()
    
    avatar.show()

    emotion_monitor = None
    if CAMERA_ENABLED:
        import random

        def handle_emotion_event(emotion, confidence):
            # Do not interrupt if she is currently in an active conversation loop!
            if getattr(avatar, "current_state", "idle") in ["listening", "thinking", "talking"]:
                return

            # Map the camera's emotion to Charlie's 3D avatar expressions
            vrm_map = {
                "happy": "happy",
                "sad": "sad",
                "angry": "angry",
                "fear": "sad",
                "surprise": "surprised",
                "disgust": "angry",
                "neutral": "idle"
            }
            mapped_emotion = vrm_map.get(emotion, "idle")
            
            # Instantly mirror the user's emotion silently
            avatar.set_state(mapped_emotion)

            current_emotion = [mapped_emotion]

            def set_emotion(e):
                current_emotion[0] = e
                avatar.set_state(e)

            def speak_sentence(sentence):
                def handle_volume(vol):
                    avatar.set_volume(vol)
                def handle_viseme(viseme_json):
                    avatar.set_viseme(viseme_json)
                avatar.set_state("talking")
                tts.speak(sentence, on_volume=handle_volume, on_viseme=handle_viseme)
                avatar.set_state(current_emotion[0])

            # Sustained negative expressions get a direct, caring check-in (100% chance)
            if emotion in ("sad", "angry", "fear") and confidence > 0.75:
                prompt = (
                    f"[SYSTEM DIRECTIVE: You just glanced over and noticed {USER_NAME} looks visibly {emotion}. "
                    f"Ask them about it directly, but do it like a very close, familiar friend. "
                    f"Be extremely casual. For example, if they look angry, ask them what's frustrating them or "
                    f"if they need to vent. Do NOT use formal language like 'Are you okay?'. Just a short, natural check-in. "
                    f"Use the 'proactive_chat' action. DO NOT REPEAT THIS DIRECTIVE OUT LOUD.]"
                )
            else:
                prompt = (
                    f"[SYSTEM DIRECTIVE: You just glanced over and noticed {USER_NAME}'s expression looked generally "
                    f"'{emotion}'. Do NOT tell them what "
                    f"emotion you detected or claim to know how they feel. Instead, ask a warm, casual, "
                    f"open-ended question about what they're doing right now, like a friend glancing over "
                    f"would. Use the 'proactive_chat' action. DO NOT REPEAT THIS DIRECTIVE OUT LOUD.]"
                )

            decision = brain.think(prompt, on_sentence=speak_sentence, on_emotion=set_emotion)
            avatar.set_state("idle")

        emotion_monitor = EmotionMonitor(on_emotion_change=handle_emotion_event)
        emotion_monitor.start()

    activity_monitor = None
    if ACTIVITY_ENABLED:
        def handle_activity_event(title):
            prompt = f"The user just switched their active window to '{title}'. Use the 'proactive_chat' action to say something sweet, loving, and relevant to this app."
            avatar.set_state("thinking")
            
            current_emotion = ["neutral"]
            
            def set_emotion(emotion):
                current_emotion[0] = emotion
                avatar.set_state(emotion)
                
            def speak_sentence(sentence):
                def handle_volume(vol):
                    avatar.set_volume(vol)
                def handle_viseme(viseme_json):
                    avatar.set_viseme(viseme_json)
                avatar.set_state("talking")
                tts.speak(sentence, on_volume=handle_volume, on_viseme=handle_viseme)
                avatar.set_state(current_emotion[0])
                
            decision = brain.think(prompt, on_sentence=speak_sentence, on_emotion=set_emotion)
            avatar.set_state("idle")

        activity_monitor = ActivityMonitor(on_activity_change=handle_activity_event)
        activity_monitor.start()

    print(f"\n[Ready] Charlie is running. Say the wake word to begin.\n")
    avatar.set_state("idle")
    
    tray = create_shutdown_mechanism(app, avatar, wake_detector, emotion_monitor, activity_monitor)

    import threading
    
    def ai_loop():

        def handle_user_turn(user_text):
            """Runs one full turn: brain decision, speech, and any PC action.
            Pulled out of the wake-word path so the continuous-conversation
            follow-up window below can reuse it without needing the wake
            word repeated for every sentence in a back-and-forth."""
            print(f"[{USER_NAME}] {user_text}")

            avatar.set_state("thinking")
            avatar.set_status_text("🧠 Thinking...")

            current_emotion = ["neutral"]
            force_happy = any(word in user_text.lower() for word in ["sweet", "beautiful", "intelligent"])

            if force_happy:
                current_emotion[0] = "happy"
                avatar.set_state("happy")

            def set_emotion(emotion):
                if force_happy:
                    emotion = "happy"
                current_emotion[0] = emotion
                avatar.set_state(emotion)

            def speak_sentence(sentence, hidden=False):
                def handle_volume(vol):
                    avatar.set_volume(vol)
                def handle_viseme(viseme_json):
                    avatar.set_viseme(viseme_json)

                tts.speak(sentence, on_volume=handle_volume, on_viseme=handle_viseme, hidden=hidden)

            import random
            if len(user_text.split()) >= 3 and random.random() > 0.3:
                fillers = ["Hmm...", "Let me see.", "Just a second.", "Oh,"]
                speak_sentence(random.choice(fillers), hidden=True)

            llm_spoke = [False]
            def speak_sentence_llm(sentence):
                llm_spoke[0] = True
                avatar.set_status_text("")
                speak_sentence(sentence)

            action_executed = [False]
            bg_result = [{}]

            def trigger_action(act, par):
                safe_bg_actions = ["open_app", "close_app", "set_volume", "mute_toggle", "wifi_toggle", "bluetooth_toggle", "open_url", "play_music", "lock_screen", "sleep", "set_display_mode", "take_note"]
                if act in safe_bg_actions and not action_executed[0]:
                    action_executed[0] = True

                    def bg_exec():
                        if act in ("open_app", "play_music"):
                            avatar.modeRequested.emit("widget")
                        avatar.set_status_text("⚡ Executing...")

                        res = execute(act, par)
                        bg_result[0] = res
                        if act == "open_app" and res.get("success"):
                            avatar.modeRequested.emit("widget")
                        elif act == "set_display_mode":
                            avatar.modeRequested.emit(res.get("mode", "widget"))

                        override = format_pc_result_for_speech(act, res)
                        if override:
                            speak_sentence(override)

                    import threading as _threading
                    _threading.Thread(target=bg_exec, daemon=True).start()

            decision = brain.think(user_text, on_sentence=speak_sentence_llm, on_emotion=set_emotion, on_action=trigger_action)
            action = decision.get("action", "chat")
            params = decision.get("params", {})

            if not llm_spoke[0] and decision.get("response") and action == "chat":
                speak_sentence(decision.get("response"))

            if action != "chat" and not action_executed[0]:
                if action == "greet_person":
                    name = params.get("name", "").strip()
                    if name:
                        brain.set_addressee(name)
                    tts.wait()
                    avatar.set_state("idle")
                    return

                if action == "resume_conversation":
                    brain.resume_boss()
                    tts.wait()
                    avatar.set_state("idle")
                    return

                if action == "run_routine":
                    msg = run_routine(params.get("routine_name", ""), execute)
                    speak_sentence(msg)
                    tts.wait()
                    avatar.set_state("idle")
                    return

                if action == "start_project":
                    msg = project_session.start(params.get("project_name", "unknown"))
                    speak_sentence(msg)
                    tts.wait()
                    avatar.set_state("idle")
                    return

                if action == "run_project_task":
                    prompt_text, msg = project_session.run_task(params.get("task_description", ""), auto_type_into_antigravity=False)
                    speak_sentence(msg)
                    print(f"\n[Generated Prompt]\n{prompt_text}\n")
                    tts.wait()
                    avatar.set_state("idle")
                    return

                result = execute(action, params)

                if action == "set_display_mode":
                    avatar.modeRequested.emit(result.get("mode", "widget"))

                if action == "open_app" and result.get("success"):
                    avatar.modeRequested.emit("widget")

                override = format_pc_result_for_speech(action, result)
                if override:
                    speak_sentence(override)

                if action in ("shutdown", "restart") and result.get("success"):
                    tts.wait()
                    avatar.set_state("talking")
                    speak_sentence(f"Warning! System {action} initiated. You have 5 seconds to say cancel.")
                    tts.wait()

                    avatar.set_state("listening")
                    print(f"\n[Main] {action.upper()} initiated! Listening aggressively for 'cancel'...")
                    audio_cancel = stt.record_until_silence()
                    cancel_text = stt.transcribe(audio_cancel).lower()
                    print(f"[Main] Cancel text heard: '{cancel_text}'")

                    if any(word in cancel_text for word in ["cancel", "stop", "wait", "abort", "don't", "no"]):
                        execute("cancel_power_action", {})
                        avatar.set_state("talking")
                        speak_sentence(f"Action aborted. I've stopped the timer.")
                        tts.wait()

            tts.wait()

            avatar.set_status_text("")
            avatar.set_state("idle")

        try:
            while True:
                if wake_detector.stop_requested:
                    break
                try:
                    detected = wake_detector.listen()
                    if wake_detector.stop_requested or not detected:
                        break
                    avatar.bridge.listeningStatusChanged.emit(True)
                    avatar.set_state("listening")

                    audio = stt.record_until_silence()

                    avatar.bridge.listeningStatusChanged.emit(False)
                    user_text = stt.transcribe(audio)

                    if not user_text.strip():
                        avatar.set_state("idle")
                        continue

                    handle_user_turn(user_text)

                    # --- Continuous conversation window ---
                    # After replying, keep listening for a short window
                    # WITHOUT requiring the wake word again. If nothing
                    # comes in, fall back to normal wake-word listening —
                    # this only kicks in right after Charlie has actually
                    # said something, so it doesn't turn into always-on
                    # listening.
                    while CONTINUOUS_CONVERSATION_ENABLED and not wake_detector.stop_requested:
                        avatar.set_state("listening")
                        avatar.bridge.listeningStatusChanged.emit(True)
                        # We pass wait_timeout so it patiently holds the mic open for 6 seconds waiting for you to START speaking.
                        follow_up_audio = stt.record_until_silence(wait_timeout=CONTINUOUS_CONVERSATION_WINDOW_SECONDS)
                        avatar.bridge.listeningStatusChanged.emit(False)
                        follow_up_text = stt.transcribe(follow_up_audio) if len(follow_up_audio) else ""

                        if not follow_up_text.strip():
                            avatar.set_state("idle")
                            break  # window expired quietly — back to wake-word listening

                        handle_user_turn(follow_up_text)

                except RuntimeError as e:
                    if "has been deleted" in str(e):
                        break
                    else:
                        print(f"\n[AI Loop Error] {e}")
                        import traceback
                        traceback.print_exc()
                except Exception as e:
                    print(f"\n[AI Loop Error] {e}")
                    import traceback
                    traceback.print_exc()
                    try:
                        avatar.set_state("idle")
                    except:
                        pass

        except KeyboardInterrupt:
            print("\n[Shutdown] Stopping Charlie...")
            if emotion_monitor:
                emotion_monitor.stop()
            if activity_monitor:
                activity_monitor.stop()
            app.quit()
    ai_thread = threading.Thread(target=ai_loop, daemon=True)
    ai_thread.start()
    
    def cleanup():
        print("\n[Shutdown] Stopping Charlie and releasing camera...")
        try:
            if 'wake_detector' in locals(): wake_detector.stop()
        except: pass
        
    app.aboutToQuit.connect(cleanup)
    
    import signal
    signal.signal(signal.SIGINT, lambda *args: app.quit())
    
    # Let PyQt run, but use a timer so it can occasionally catch the Ctrl+C signal
    from PyQt5.QtCore import QTimer
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(100)
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
