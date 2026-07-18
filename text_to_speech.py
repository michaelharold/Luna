
"""
text_to_speech.py — Luna TTS system

Voice output is produced by **Piper** (offline neural TTS) via piper_tts.py:
Piper renders the text to a wav, then TTS_PLAYER (paplay) plays it. See the
README "Piper voice (TTS)" section for install/config.

Why Piper (and why pyttsx3 was removed):
  - pyttsx3 returned from runAndWait() immediately on Debian 13 + PipeWire, so
    Luna "finished" speaking before the audio played — the mic opened early and
    echo protection failed ("[TTS] engine returned early (0.0s...)").
  - Piper's player subprocess blocks until playback actually completes, which
    keeps the mic-blocking + echo protection correct.

Everything around the engine is unchanged:
  - speaking state lock          - talking mouth animation
  - microphone blocking          - talking servo bob
  - echo protection
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
# pyttsx3 was intentionally removed (see module docstring).
#
# Now (streaming — see piper_tts.py):
#
#   piper --output_raw  ->  player (raw stdin)
#        |
#        v
#   playback starts on the FIRST synthesised chunk (sub-second), and
#   on_audio_start fires at that exact moment so lips + servo bob begin
#   in sync with the sound — not seconds before it.
#
# ============================================================================


def _on_audio_start():
    """Called by piper_tts the instant real audio begins playing."""
    with state.lock:
        state.audio_playing = True
    servo.talk_start()


def _piper_speak(text):

    tts.speak(text, on_audio_start=_on_audio_start)

# ============================================================================
# Talking mouth energy animation
# ============================================================================

_energy_phase = 0.0


def _energy_loop():

    global _energy_phase

    while True:

        # Key the mouth on audio_playing (real sound), not speaking (the whole
        # call incl. synth time) — lips no longer flap during silent synth.
        with state.lock:
            speaking = state.audio_playing

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
        # ACTUAL SPEECH — Piper streams; playback starts on the first
        # synthesised chunk. The talking servo bob and the mouth animation
        # are both started from _on_audio_start() at the exact moment sound
        # begins, so there's no silent lip-flap while Piper synthesises.
        # ------------------------------------------------------------

        speech_start = time.time()

        _piper_speak(text)



    finally:

        # stop the talking bob first so the arms ease back to rest immediately
        servo.talk_stop()

        elapsed = time.time() - speech_start



        with state.lock:


            state.speaking = False

            state.audio_playing = False

            state.audio_energy = 0.0

            state.frozen_emotion = None

            state.luna_mode = "idle"



            # Since Piper's player blocks until playback finishes,
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
