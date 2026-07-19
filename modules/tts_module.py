"""
tts_module.py — streaming Piper TTS with multi-viseme lipsync.

Volume-only lipsync (old approach) drives a single 'aa' blend shape off RMS,
which just makes the mouth flap proportional to loudness — it can't tell
"ah" from "ee" from "oh", so it never looks like it's actually saying the
words. This version does a lightweight per-chunk FFT to get the spectral
centroid (where the audio's energy sits — low = round vowels like oh/oo,
high = bright vowels like ee/ih) and blends across multiple VRM visemes
based on that, which reads far more natural for very little extra cost.

It's a heuristic, not real phoneme alignment — but it's a big step up from
single-viseme volume mapping and stays real-time on CPU.

Install: pip install sounddevice numpy
"""

import os
import sys
import json
import queue
import threading
import numpy as np
import sounddevice as sd
from piper.voice import PiperVoice

sys.path.append("..")
from config.settings import TTS_RATE


def _estimate_viseme(pcm, sample_rate):
    """Very lightweight heuristic viseme estimate from one audio chunk.
    Returns a dict of VRM standard viseme weights (aa, ih, ou, ee, oh)."""
    if len(pcm) < 32:
        return {"aa": 0.0, "ih": 0.0, "ou": 0.0, "ee": 0.0, "oh": 0.0}

    samples = pcm.astype(np.float32)
    rms = np.sqrt(np.mean(samples ** 2))
    volume = min(1.0, rms / 8000.0)

    if volume < 0.03:
        return {"aa": 0.0, "ih": 0.0, "ou": 0.0, "ee": 0.0, "oh": 0.0}

    # Spectral centroid: energy-weighted average frequency of this chunk
    windowed = samples * np.hanning(len(samples))
    spectrum = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(len(windowed), d=1.0 / sample_rate)
    total_energy = np.sum(spectrum) + 1e-9
    centroid = np.sum(freqs * spectrum) / total_energy

    # Bucket the centroid into viseme space. These ranges are tuned by ear,
    # not derived from formant tables — nudge them if a particular voice
    # model over/under-rounds.
    weights = {"aa": 0.0, "ih": 0.0, "ou": 0.0, "ee": 0.0, "oh": 0.0}
    if centroid < 500:
        weights["ou"] = volume  # low/round — "oh", "oo"
    elif centroid < 900:
        weights["oh"] = volume * 0.8
        weights["aa"] = volume * 0.3
    elif centroid < 1500:
        weights["aa"] = volume  # open — "ah"
    elif centroid < 2400:
        weights["ih"] = volume * 0.7
        weights["aa"] = volume * 0.3
    else:
        weights["ee"] = volume  # bright/high — "ee", "ih"

    return weights


class StreamingPiperTTS:
    def __init__(self):
        self._lock = threading.Lock()
        model_path = os.path.join(os.path.dirname(__file__), "..", "en_US-hfc_female-medium.onnx")
        config_path = os.path.join(os.path.dirname(__file__), "..", "en_US-hfc_female-medium.onnx.json")
        print("[TTS] Loading Piper TTS voice model...")
        self.voice = PiperVoice.load(model_path, config_path=config_path)
        self.sample_rate = self.voice.config.sample_rate
        print("[TTS] Piper voice loaded (streaming mode).")

        self.speech_queue = queue.Queue()
        self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.worker_thread.start()

    def speak(self, text, on_volume=None, on_viseme=None):
        # Push to queue and return immediately so the LLM stream can keep producing
        self.speech_queue.put((text, on_volume, on_viseme))

    def wait(self):
        self.speech_queue.join()

    def _process_queue(self):
        while True:
            text, on_volume, on_viseme = self.speech_queue.get()
            try:
                self._synthesize_and_stream(text, on_volume, on_viseme)
            except Exception as e:
                print(f"[TTS Error] {e}")
            finally:
                self.speech_queue.task_done()

    def _synthesize_and_stream(self, text, on_volume, on_viseme):
        with self._lock:
            print(f"[Charlie] {text}")

            stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype='int16',
                blocksize=0,  # let PortAudio choose — lower latency than a fixed large block
            )
            stream.start()
            try:
                for chunk in self.voice.synthesize(text):
                    pcm = np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)
                    if len(pcm) == 0:
                        continue

                    # Slice into ~50ms chunks for highly accurate, fast-updating lip sync
                    slice_size = int(self.sample_rate * 0.05)
                    for i in range(0, len(pcm), slice_size):
                        sub_pcm = pcm[i:i+slice_size]
                        
                        stream.write(sub_pcm)

                        if on_volume:
                            rms = np.sqrt(np.mean(sub_pcm.astype(np.float32) ** 2))
                            vol = min(1.0, rms / 8000.0)
                            on_volume(vol)

                        if on_viseme:
                            weights = _estimate_viseme(sub_pcm, self.sample_rate)
                            on_viseme(json.dumps(weights))
            finally:
                stream.stop()
                stream.close()
                if on_volume:
                    on_volume(0.0)
                if on_viseme:
                    on_viseme(json.dumps({"aa": 0.0, "ih": 0.0, "ou": 0.0, "ee": 0.0, "oh": 0.0}))


class CoquiTTS:
    """Unchanged — higher quality, ~1-3s generation delay before speech starts."""
    def __init__(self):
        from TTS.api import TTS
        self.tts = TTS(model_name="tts_models/en/ljspeech/tacotron2-DDC", progress_bar=False)

    def speak(self, text):
        print(f"[Charlie] {text}")
        self.tts.tts_to_file(text=text, file_path="modules/_tmp_speech.wav")
        import sounddevice as sd
        import soundfile as sf
        data, samplerate = sf.read("modules/_tmp_speech.wav")
        sd.play(data, samplerate)
        sd.wait()

    def wait(self):
        pass


def get_tts_engine():
    from config.settings import TTS_ENGINE
    if TTS_ENGINE == "coqui":
        return CoquiTTS()
    return StreamingPiperTTS()


if __name__ == "__main__":
    tts = get_tts_engine()
    tts.speak("Hi Harshvardhan. This is a test of multi viseme streaming voice.",
               on_viseme=lambda v: print(v))
    tts.wait()
