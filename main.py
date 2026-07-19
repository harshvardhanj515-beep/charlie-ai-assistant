"""
Charlie - main loop.

Flow: wake word -> avatar shows "listening" -> record & transcribe ->
avatar shows "thinking" -> brain decides action + reply -> PC control
executes action -> avatar shows "talking" -> TTS speaks -> back to idle.

Camera/emotion monitoring runs independently in the background and can
interject only in narrow, low-frequency, non-annoying cases (see
handle_emotion_event below) - it never talks over you or interrupts
an active conversation.

RUN THIS FROM THE charlie/ DIRECTORY:  python main.py
"""

import os
import sys
import time

# --- GPU acceleration for QtWebEngine (fixes choppy avatar rendering) ---
# Must be set before QApplication is constructed. Without this, QtWebEngine
# can silently fall back to software rendering for the Three.js scene, which
# is a common cause of stuttering animation that has nothing to do with the
# JS code itself.
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--ignore-gpu-blacklist --enable-gpu-rasterization --enable-native-gpu-memory-buffers --enable-webgl"
)

from config.settings import USER_NAME, CAMERA_ENABLED, ACTIVITY_ENABLED
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
        def handle_emotion_event(emotion, confidence):
            # Deliberately conservative: only react to a narrow set of
            # emotions, and only speak up occasionally - not every single
            # detection. Tune this list based on what's actually useful
            # to you rather than noisy.
            if emotion in ("sad", "angry", "fear") and confidence > 0.75:
                avatar.set_state("talking")
                tts.speak(f"Hey {USER_NAME}, you okay? Let me know if you want to talk or need a break.")
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
    
    # Keep reference so it isn't garbage collected
    tray = create_shutdown_mechanism(app, avatar, wake_detector, emotion_monitor, activity_monitor)

    import threading
    
    def ai_loop():
        try:
            while True:
                if wake_detector.stop_requested:
                    break
                try:
                    # 1. Wait for wake word
                    detected = wake_detector.listen()
                    if wake_detector.stop_requested or not detected:
                        break
                    # Wake word detected, trigger visual feedback
                    avatar.bridge.listeningStatusChanged.emit(True)
                    avatar.set_state("listening")

                    # 2. Record and transcribe
                    audio = stt.record_until_silence()
                    
                    # Stop visual feedback
                    avatar.bridge.listeningStatusChanged.emit(False)
                    user_text = stt.transcribe(audio)

                    if not user_text.strip():
                        avatar.set_state("idle")
                        continue

                    print(f"[{USER_NAME}] {user_text}")

                    # 3. Brain decides intent + action
                    avatar.set_state("thinking")
                    
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
                        
                    def speak_sentence(sentence):
                        def handle_volume(vol):
                            avatar.set_volume(vol)
                        def handle_viseme(viseme_json):
                            avatar.set_viseme(viseme_json)

                        tts.speak(sentence, on_volume=handle_volume, on_viseme=handle_viseme)
                        # Remove blocking avatar.set_volume(0.0) from here since TTS is now async!
                        
                    decision = brain.think(user_text, on_sentence=speak_sentence, on_emotion=set_emotion)
                    action = decision.get("action", "chat")
                    params = decision.get("params", {})

                    # 4. Execute any PC action
                    if action != "chat":
                        # --- Social / people-aware actions ---
                        if action == "greet_person":
                            name = params.get("name", "").strip()
                            if name:
                                brain.set_addressee(name)
                            tts.wait()
                            avatar.set_state("idle")
                            continue

                        if action == "resume_conversation":
                            brain.resume_boss()
                            tts.wait()
                            avatar.set_state("idle")
                            continue

                        # --- Routines ---
                        if action == "run_routine":
                            msg = run_routine(params.get("routine_name", ""), execute)
                            speak_sentence(msg)
                            tts.wait()
                            avatar.set_state("idle")
                            continue

                        # AutoProjectSession actions
                        if action == "start_project":
                            msg = project_session.start(params.get("project_name", "unknown"))
                            speak_sentence(msg)
                            tts.wait()
                            avatar.set_state("idle")
                            continue
                            
                        if action == "run_project_task":
                            prompt_text, msg = project_session.run_task(params.get("task_description", ""), auto_type_into_antigravity=False)
                            speak_sentence(msg)
                            print(f"\n[Generated Prompt]\n{prompt_text}\n")
                            tts.wait()
                            avatar.set_state("idle")
                            continue
                            
                        result = execute(action, params)
                        
                        # Handle display mode switching
                        if action == "set_display_mode":
                            avatar.modeRequested.emit(result.get("mode", "widget"))
                            
                        # Automatically get out of the way when the user opens an app
                        if action == "open_app" and result.get("success"):
                            avatar.modeRequested.emit("widget")

                        override = format_pc_result_for_speech(action, result)
                        if override:
                            speak_sentence(override)
                            
                        # Shutdown/Restart Cancellation Loop
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
                    
                    # Wait for all speech to finish playing before going back to idle
                    tts.wait()
                    
                    avatar.set_state("idle")
                    
                except RuntimeError as e:
                    if "has been deleted" in str(e):
                        # The app is shutting down, safely break the loop
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
    
    # Allow Ctrl+C to work by setting up a signal handler
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
