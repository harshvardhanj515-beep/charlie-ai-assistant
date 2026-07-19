"""
Wake word detection using openWakeWord (fully open-source, free, offline).
This runs continuously with negligible CPU (~1-2%) and only fires the
rest of the pipeline (STT -> brain -> TTS) when the wake word is heard -
this is WHY the system doesn't feel laggy: it's not running the heavy
Whisper model constantly, only on-demand.

Install: pip install openwakeword sounddevice numpy
First run will download pretrained models automatically.

NOTE ON CUSTOM WAKE WORDS: openWakeWord ships with pretrained words
(alexa, hey_jarvis, hey_mycroft, etc). Training a custom "Charlie" model
requires a separate training step (they provide a Colab notebook for this -
search "openWakeWord custom model training"). Until you train one, this
code uses "hey_jarvis" as a stand-in so you have something working today;
swap the model path once you've trained your own "Charlie" model.
"""

import numpy as np
import sounddevice as sd
from openwakeword.model import Model
import sys

sys.path.append("..")
from config.settings import WAKE_WORD_SENSITIVITY


class WakeWordDetector:
    def __init__(self, model_path="hey_jarvis"):
        """model_path: either a pretrained name ('hey_jarvis', 'alexa') or
        a path to your own trained .onnx/.tflite model once you make one."""
        print("[WakeWord] Loading model...")
        self.model = Model(wakeword_models=[model_path], inference_framework="onnx")
        self.sample_rate = 16000
        self.chunk_size = 1280  # openWakeWord expects 80ms chunks at 16kHz
        self.stop_requested = False
        print(f"[WakeWord] Listening for wake word ('{model_path}')...")

    def listen(self):
        """Blocks until wake word detected, then returns."""
        print(f"\n[WakeWord] Listening for wake word...")
        try:
            with sd.InputStream(samplerate=self.sample_rate, channels=1,
                                 dtype='int16', blocksize=self.chunk_size) as stream:
                while not self.stop_requested:
                    try:
                        audio_chunk, _ = stream.read(self.chunk_size)
                    except Exception as e:
                        # Ignore PortAudio buffer overflow exceptions to prevent thread crashes
                        continue
                    audio_chunk = audio_chunk.flatten()
                    prediction = self.model.predict(audio_chunk)
    
                    for mdl_name, score in prediction.items():
                        if score > WAKE_WORD_SENSITIVITY:
                            print(f"[WakeWord] Detected! (confidence: {score:.2f})")
                            return True
                return False
        except Exception as e:
            try:
                dev = sd.query_devices(sd.default.device[0], 'input')
                print(f"\n[WakeWord] CRITICAL ERROR: Failed to open microphone '{dev['name']}' at {self.sample_rate}Hz. Error: {e}")
            except:
                print(f"\n[WakeWord] CRITICAL ERROR: Failed to open microphone. Error: {e}")
            
            # Prevent rapid infinite loop crashing if mic is permanently denied
            import time
            time.sleep(2)
            return False


if __name__ == "__main__":
    detector = WakeWordDetector()
    detector.listen()
    print("Wake word triggered - this is where the main loop would take over.")
