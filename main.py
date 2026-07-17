import sys
import time
import signal
import threading

from config import TORCH_THREADS, PI_MODEL
import torch
torch.set_num_threads(TORCH_THREADS)

if PI_MODEL:
    print(f"[Luna] Running on Raspberry Pi {PI_MODEL}")
    print(f"[Luna] PyTorch threads: {TORCH_THREADS}")

from camera_thread import start_camera
start_camera()
time.sleep(0.5)

from vision_module import start_vision
start_vision()
time.sleep(1.0)

from gesture_module import start_gesture
start_gesture()
time.sleep(0.5)

from behavior_engine import start_behavior
start_behavior()
time.sleep(0.2)

import random
import difflib

from speech_to_text import listen, WAKE_ACK
from text_to_speech import speak
from brain import process
from shared_state import state
from servo_module import servo
from config import (WAKE_REPLIES, ECHO_GUARD_WINDOW,
                    ECHO_RUN_THRESH, ECHO_OVERLAP_THRESH)


def _is_self_echo(text):
    """Defense-in-depth against Luna hearing her own voice through the
    speaker (see text_to_speech.py docstring for the timing side of this —
    that's the primary fix; this is cleanup for trailing echo/reverb that
    slips past the mic-blocking window).

    Requires BOTH a decent contiguous word-run match AND decent overall
    word overlap with Luna's last reply — either check alone is too easy
    to trigger on ordinary short sentences full of common words ("can",
    "you", "i"...), which would wrongly swallow real user speech."""
    with state.lock:
        last      = state.last_spoken_text
        last_time = state.last_spoken_time

    if not last or (time.time() - last_time) > ECHO_GUARD_WINDOW:
        return False

    heard_words = text.lower().split()
    last_words  = last.split()
    if not heard_words:
        return False

    overlap = sum(1 for w in heard_words if w in set(last_words)) / len(heard_words)
    sm      = difflib.SequenceMatcher(None, heard_words, last_words, autojunk=False)
    run     = sm.find_longest_match(0, len(heard_words), 0, len(last_words)).size
    run_ratio = run / len(heard_words)

    return run_ratio >= ECHO_RUN_THRESH and overlap >= ECHO_OVERLAP_THRESH


def voice_loop():
    while True:
        text = listen()
        try:
            if text == WAKE_ACK:
                # wake word alone ("Luna!") — short acknowledgement
                speak(random.choice(WAKE_REPLIES))
            elif text:
                if _is_self_echo(text):
                    print(f"[Luna] Ignoring self-echo: \"{text}\"")
                else:
                    # speak() serializes internally — an answer is never
                    # dropped, even if a gesture reaction is mid-sentence
                    process(text)
        finally:
            # never leave the mode stuck on "processing" (e.g. empty input)
            with state.lock:
                if not state.speaking and state.luna_mode == "processing":
                    state.luna_mode = "idle"
        time.sleep(0.05)


threading.Thread(target=voice_loop, daemon=True).start()


def _shutdown(*_):
    print("\n[Luna] Shutting down — centering servos, releasing GPIO")
    try:
        servo.cleanup()
    except Exception:
        pass
    try:
        import pygame
        pygame.quit()
    except Exception:
        pass
    sys.exit(0)


signal.signal(signal.SIGINT,  _shutdown)
signal.signal(signal.SIGTERM, _shutdown)

from face_renderer import renderer_loop

try:
    renderer_loop()
finally:
    _shutdown()
