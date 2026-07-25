"""
Speech-to-Text module.
Uses faster-whisper: a reimplementation of OpenAI's Whisper that runs
4-5x faster on CPU with the same accuracy. This is the single biggest
lever for "no delay" — vanilla whisper is too slow for real-time use
on a laptop CPU, faster-whisper is not.

Install: pip install faster-whisper sounddevice numpy
"""

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
import queue
import sys

sys.path.append("..")
from config.settings import STT_MODEL_SIZE, STT_DEVICE


class SpeechToText:
    def __init__(self):
        # compute_type="int8" is the key speed lever on CPU - trades a small
        # accuracy hit for a large speed gain. Use "float16" if STT_DEVICE="cuda".
        compute_type = "float16" if STT_DEVICE == "cuda" else "int8"
        print(f"[STT] Loading Whisper model '{STT_MODEL_SIZE}' on {STT_DEVICE}...")
        self.model = WhisperModel(STT_MODEL_SIZE, device=STT_DEVICE, compute_type=compute_type)
        self.sample_rate = 16000
        self.dynamic_silence_threshold = 0.015
        self._auto_calibrate()
        print("[STT] Ready.")

    def _auto_calibrate(self):
        print("[STT] Auto-calibrating microphone to your room's background noise... (Please stay silent for 2 seconds)")
        try:
            import time
            time.sleep(1.0) # Wait for any application startup noises to finish
            audio = sd.rec(int(2 * self.sample_rate), samplerate=self.sample_rate, channels=1, dtype='int16')
            sd.wait()
            audio_float = audio.astype(np.float32) / 32768.0
            noise_level = np.abs(audio_float).mean()
            # Increased threshold multiplier to 1.8x so background noise doesn't keep the mic open for 5+ seconds
            self.dynamic_silence_threshold = max(0.0005, noise_level * 1.8)
            print(f"[STT] Calibration complete! Noise level: {noise_level:.6f}, Threshold set to: {self.dynamic_silence_threshold:.6f}")
        except Exception as e:
            try:
                dev = sd.query_devices(sd.default.device[0], 'input')
                print(f"[STT] Calibration failed on device '{dev['name']}' (Default SR: {dev['default_samplerate']}). Error: {e}")
            except:
                print(f"[STT] Calibration failed: {e}. Using default threshold.")

    def record_audio(self, duration=5):
        """Records a fixed-length clip. For production use, replace with
        silence-detection (stop recording when you stop talking) - see
        record_until_silence() below for that upgrade."""
        print("[STT] Listening...")
        audio = sd.rec(int(duration * self.sample_rate), samplerate=self.sample_rate,
                        channels=1, dtype='int16')
        sd.wait()
        return audio.flatten().astype(np.float32) / 32768.0

    def record_until_silence(self, silence_duration=0.5, max_duration=15, wait_timeout=1.2):
        """Better UX than a fixed timer: stops listening as soon as you stop
        talking, instead of waiting out a fixed 5 seconds every time. This is
        what actually removes perceived delay for the user.
        """
        print("[STT] Listening (will stop automatically on silence)...")
        chunks = []
        silent_chunks_needed = int(silence_duration * self.sample_rate / 1024)
        silent_count = 0
        max_chunks = int(max_duration * self.sample_rate / 1024)
        
        has_started_speaking = False
        import time
        wait_start_time = time.time()

        q = queue.Queue()

        def callback(indata, frames, time_info, status):
            q.put(indata.copy())

        try:
            with sd.InputStream(samplerate=self.sample_rate, channels=1,
                                 dtype='int16', blocksize=1024, callback=callback):
                for _ in range(max_chunks):
                    try:
                        chunk = q.get(timeout=2.0)
                    except queue.Empty:
                        print("\n[STT] Microphone stream froze! Recovering...")
                        break
                        
                    chunks.append(chunk)
                    volume = np.abs(chunk.astype(np.float32) / 32768.0).mean()
                    
                    if volume > self.dynamic_silence_threshold * 1.5:
                        has_started_speaking = True
                        silent_count = 0
                    else:
                        silent_count += 1
                        
                    if has_started_speaking:
                        if silent_count >= silent_chunks_needed:
                            break
                    else:
                        if (time.time() - wait_start_time) > wait_timeout:
                            break
        except Exception as e:
            try:
                dev = sd.query_devices(sd.default.device[0], 'input')
                print(f"\n[STT] CRITICAL ERROR: Could not open microphone '{dev['name']}' at {self.sample_rate}Hz. Error: {e}")
            except:
                print(f"\n[STT] CRITICAL ERROR: Could not open microphone. Error: {e}")
            return np.array([])
            
        result_audio = np.concatenate(chunks).flatten().astype(np.float32) / 32768.0
        max_vol = np.max(np.abs(result_audio))
        print(f"[STT] Finished recording {len(result_audio)/self.sample_rate:.1f} seconds. Max volume recorded: {max_vol:.6f}")
        
        # Aggressively drop audio that never got significantly louder than background noise
        if max_vol < max(0.001, self.dynamic_silence_threshold * 1.5):
            print(f"[STT] Audio was too quiet to be real speech (Max Vol: {max_vol:.6f}). Discarding to prevent hallucinations.")
            return np.array([])
            
        return result_audio

    def transcribe(self, audio):
        if len(audio) == 0:
            return ""
            
        segments, info = self.model.transcribe(
            audio, 
            language="en",
            initial_prompt="Charlie, ChatGPT, Gemini, Claude, Notepad, Firefox, Chrome, Spotify, YouTube, Arijit Singh, play, open, stop.",
            beam_size=1, 
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500, threshold=0.7), # Strict VAD
            no_speech_threshold=0.4, # Drop if 40% confident it's silence
            log_prob_threshold=-1.0,
            compression_ratio_threshold=1.4
        )
        text = " ".join(seg.text for seg in segments).strip()
        print(f"[STT DEBUG] Raw whisper transcription: '{text}'")
        
        lower_text = text.lower().strip(" .!?\n")
        
        # Filter exact-match single-word hallucinations
        if lower_text in ["you", "yeah", "i", "bye", "ok", "okay", "thank you", "thanks", "hello", "the", "a", "it", "so", "and"]:
            print(f"[STT] Dropped likely short hallucination: '{text}'")
            return ""

        # Filter out known Whisper background-noise hallucination substrings
        hallucinations = [
            "bozzi", "amara.org", "thanks for watching", "thank you for watching",
            "subscribe to our channel", "press the bell icon", "get notified",
            "subtitles by", "translated by", "captioned by"
        ]
        
        for h in hallucinations:
            if h in lower_text:
                return ""
                
        # Fallback Python-level repetition filter
        # If the exact same phrase is repeated 3 or more times, it's a hallucination
        words = lower_text.split()
        if len(words) > 6:
            # Check for repeating 3-word chunks
            for i in range(len(words) - 6):
                chunk = " ".join(words[i:i+3])
                if lower_text.count(chunk) >= 3:
                    return ""
                
        return text


if __name__ == "__main__":
    # Standalone test - run this file directly to test STT in isolation
    stt = SpeechToText()
    audio = stt.record_until_silence()
    text = stt.transcribe(audio)
    print(f"You said: {text}")
