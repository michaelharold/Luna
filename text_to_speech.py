
"""
text_to_speech.py — Luna TTS system

CHANGES:
========
1. Disabled pyttsx3 on Linux.
   Reason:
   - pyttsx3 returns from runAndWait() immediately on Debian 13 + PipeWire.
   - Audio does not reliably reach Bluetooth A2DP devices.
   - This caused:
       "[TTS] engine returned early (0.0s...)"

2. Replaced Linux speech output with espeak-ng.
   Reason:
   - espeak-ng blocks until speech finishes.
   - Works correctly with PipeWire.
   - Automatically follows the system default output
     (Bluetooth earbuds, HDMI, etc.).

3. Kept Luna's existing:
   - speaking state lock
   - microphone blocking
   - echo protection
   - talking animation
   - servo movement
"""

import sys
import threading
import time
import random
import math
import subprocess
from piper_tts import tts

from shared_state import state
from servo_module import servo
from config import (
    TTS_RATE,
    MIC_BLOCK_AFTER_SPEAK,
)


# ============================================================================
# TTS ENGINE
# ============================================================================
#
# pyttsx3 was intentionally removed.
#
# Previously:
#
#   pyttsx3.say()
#        |
#        v
#   runAndWait()
#        |
#        v
#   returns immediately ❌
#
# Result:
# Luna thought she finished speaking,
# microphone opened,
# echo protection failed.
#
# Now:
#
#   espeak-ng subprocess
#        |
#        v
#   waits until audio completes ✅
#
# ============================================================================


def _piper_speak(text):

    tts.speak(text)

# ============================================================================
# Talking mouth energy animation
# ============================================================================

_energy_phase = 0.0


def _energy_loop():

    global _energy_phase

    while True:

        with state.lock:
            speaking = state.speaking

        if speaking:

            _energy_phase += 0.18

            slow = abs(math.sin(_energy_phase * 0.9))
            mid = abs(math.sin(_energy_phase * 2.3)) * 0.5
            fast = abs(math.sin(_energy_phase * 5.1)) * 0.2

            raw = (slow + mid + fast) / 1.7

            jitter = random.uniform(-0.08, 0.08)

            energy = max(
                0.0,
                min(1.0, raw + jitter)
            )

            with state.lock:
                state.audio_energy = energy

            time.sleep(0.016)   # ~60 fps mouth animation while speaking

        else:

            _energy_phase = 0.0

            with state.lock:
                state.audio_energy = 0.0

            time.sleep(0.05)    # idle — poll slower, saves CPU on the Pi



threading.Thread(
    target=_energy_loop,
    daemon=True
).start()



# ============================================================================
# Speech lock
# ============================================================================
#
# Prevents two voices talking together.
#
# Brain responses:
#     wait until Luna finishes
#
# Gesture reactions:
#     may be skipped
#
# ============================================================================

_speak_lock = threading.Lock()



def speak(text, can_drop=False):

    """
    Speak text.

    can_drop=False:
        Important replies always play.

    can_drop=True:
        Optional reactions can be skipped.
    """

    if not text:
        return


    if can_drop:

        if not _speak_lock.acquire(blocking=False):
            return

    else:

        _speak_lock.acquire()



    # Defined before the try so the finally block can always measure elapsed
    # time, even if something throws before the real speech starts.
    speech_start = time.time()

    try:

        with state.lock:

            state.speaking = True
            state.luna_mode = "speaking"
            state.frozen_emotion = state.emotion



        print(f"[Luna] {text}")



        # ------------------------------------------------------------
        # Arm movement while Luna speaks
        #
        # A subtle up/down bob, driven directly by the speaking state inside
        # servo_module — it runs only while Luna talks and stops the instant
        # speech ends (no duration estimate, no leftover motion afterward).
        # ------------------------------------------------------------

        servo.talk_start()



        # ------------------------------------------------------------
        # ACTUAL SPEECH
        #
        # Changed:
        # pyttsx3 removed
        # espeak-ng used instead
        # ------------------------------------------------------------

        speech_start = time.time()

        _piper_speak(text)



    finally:

        # stop the talking bob first so the arms ease back to rest immediately
        servo.talk_stop()

        elapsed = time.time() - speech_start



        with state.lock:


            state.speaking = False

            state.audio_energy = 0.0

            state.frozen_emotion = None

            state.luna_mode = "idle"



            # Since espeak-ng blocks correctly,
            # only normal echo protection is needed.
            state.mic_unblock_time = (
                time.time()
                +
                MIC_BLOCK_AFTER_SPEAK
            )


            state.last_spoken_text = text.lower()

            state.last_spoken_time = time.time()



            # Do not consume conversation timeout
            # while Luna is speaking.

            if state.conversation_active:

                state.last_activity_time = time.time()



        print(
            f"[TTS] finished in {elapsed:.1f}s"
        )


        _speak_lock.release()
