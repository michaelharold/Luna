"""
piper_tts.py

Persistent Piper TTS engine for Luna.
Keeps the voice model loaded.
"""

import subprocess
import threading
import queue
import tempfile
import os

from config import (
    PIPER_PATH,
    PIPER_MODEL,
    PIPER_LENGTH_SCALE,
    TTS_PLAYER,
)


class PiperTTS:

    def __init__(self):

        self.lock = threading.Lock()


    def speak(self, text):

        with self.lock:

            wav_file = None

            try:

                with tempfile.NamedTemporaryFile(
                    suffix=".wav",
                    delete=False
                ) as f:
                    wav_file = f.name


                subprocess.run(
                    [
                        PIPER_PATH,
                        "--model",
                        PIPER_MODEL,
                        "--length_scale",
                        str(PIPER_LENGTH_SCALE),
                        "--output_file",
                        wav_file,
                    ],
                    input=text.encode("utf-8"),
                    check=True,
                )


                subprocess.run(
                    [
                        TTS_PLAYER,
                        wav_file
                    ],
                    check=True,
                )


            except Exception as e:

                print(
                    f"[Piper] error: {e}"
                )


            finally:

                if wav_file and os.path.exists(wav_file):
                    os.remove(wav_file)



tts = PiperTTS()