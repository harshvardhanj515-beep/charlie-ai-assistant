"""
Camera-based state detection.

READ THIS BEFORE ENABLING:
This module turns your laptop camera on and analyzes your face periodically.
Three things worth deciding on purpose, not by accident:

1. VISIBILITY: your laptop's camera LED will light up whenever this runs -
   don't disable that indicator in software. It's your only signal to
   anyone in the room (including future-you) that the camera is live.
2. SCOPE: this samples a frame every EMOTION_CHECK_INTERVAL_SECONDS, not
   every frame continuously. Continuous frame-by-frame analysis burns
   CPU/battery for no real benefit and increases the amount of your life
   getting processed, even locally, for no gain in usefulness.
3. LOCAL-ONLY: this uses DeepFace running entirely on your machine. No
   frame or emotion data leaves your laptop. Keep it that way - do not
   route this through a cloud API unless you've separately decided you're
   okay with a third party receiving a webcam feed of your face.

Also: "detects emotion and asks a question automatically" is a real UX
choice - an assistant that interrupts you because it thinks you look upset
or unfocused can get annoying or wrong fast (it WILL misread neutral/
concentrating faces as "sad" or "angry" - that's a known limitation of
these models, not a bug you'll patch out). This module raises a candidate
event; whether Charlie actually interrupts you is a separate decision in
main.py, so you can tune how naggy it is.

Install: pip install deepface opencv-python
First run downloads model weights (~ couple hundred MB, one-time).
"""

import cv2
import time
import threading
import sys

sys.path.append("..")
from config.settings import CAMERA_INDEX, EMOTION_CHECK_INTERVAL_SECONDS, EMOTION_CONFIDENCE_THRESHOLD


class EmotionMonitor:
    def __init__(self, on_emotion_change=None):
        """on_emotion_change: callback fired as on_emotion_change(emotion, confidence)
        when a new dominant emotion is detected above threshold. main.py decides
        what to actually do with that (e.g. whether to say anything)."""
        self.on_emotion_change = on_emotion_change
        self.running = False
        self.last_emotion = None
        self._thread = None

    def start(self):
        """Runs in a background thread so it never blocks voice interaction."""
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[Camera] Emotion monitoring started. Camera LED should be ON now.")

    def stop(self):
        self.running = False
        print("[Camera] Emotion monitoring stopped.")

    def _loop(self):
        from deepface import DeepFace  # imported here so app startup is fast if camera disabled

        cap = cv2.VideoCapture(CAMERA_INDEX)
        if not cap.isOpened():
            print("[Camera] ERROR: could not open camera.")
            return

        while self.running:
            ret, frame = cap.read()
            if ret:
                try:
                    result = DeepFace.analyze(frame, actions=['emotion'], enforce_detection=False, silent=True)
                    if isinstance(result, list):
                        result = result[0]
                    emotion = result['dominant_emotion']
                    confidence = result['emotion'][emotion] / 100.0

                    if confidence >= EMOTION_CONFIDENCE_THRESHOLD and emotion != self.last_emotion:
                        self.last_emotion = emotion
                        if self.on_emotion_change:
                            self.on_emotion_change(emotion, confidence)
                except Exception as e:
                    pass  # face not found / lighting issue - skip silently, don't spam errors

            time.sleep(EMOTION_CHECK_INTERVAL_SECONDS)

        cap.release()


if __name__ == "__main__":
    def print_emotion(emotion, confidence):
        print(f"[Test] Detected: {emotion} ({confidence:.0%} confidence)")

    monitor = EmotionMonitor(on_emotion_change=print_emotion)
    monitor.start()
    print("Monitoring for 60 seconds... (Ctrl+C to stop early)")
    try:
        time.sleep(60)
    except KeyboardInterrupt:
        pass
    monitor.stop()
