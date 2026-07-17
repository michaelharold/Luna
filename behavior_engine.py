"""
behavior_engine.py — reacts to gestures with face state + voice + servos.

Wave       → happy face + "Hi there!" + servo wave
Thumbs up  → excited face (starburst) + "Thank you!" + both arms up
Peace      → excited face (starburst) + "Peace!" + right arm up
Open palm  → happy face (silent friendly acknowledgement)
Point      → eyes follow direction (handled in robot_face via look_dir)

Interrupt rules (order matters — answering ALWAYS wins):
  • Luna speaking or processing an answer  → gestures ignored completely
  • Conversation window active (attentive) → face + servo only, no speech,
    so a wave never talks over the user's next question
  • Fully idle                             → full reaction with speech
"""

import threading
import time
from shared_state import state
from servo_module import servo
from config import ROBOT_NAME, GESTURE_REACT_COOLDOWN, FACE_OVERRIDE_SECS

_last_react = {}   # gesture name → last reaction time


def _cooled(gesture):
    now = time.time()
    if now - _last_react.get(gesture, 0.0) < GESTURE_REACT_COOLDOWN:
        return False
    _last_react[gesture] = now
    return True


def _set_face(override):
    # face_override survives the vision loop (which rewrites state.emotion
    # several times a second and used to erase direct emotion writes)
    with state.lock:
        state.face_override       = override
        state.face_override_until = time.time() + FACE_OVERRIDE_SECS


def behavior_loop():
    from text_to_speech import speak   # deferred — avoids circular import

    while True:
        with state.lock:
            gesture = state.gesture
            busy    = state.speaking or state.luna_mode in ("processing",
                                                            "speaking")
            in_convo = state.conversation_active

        if not busy:
            # in an active conversation react silently (face + servo only)
            quiet = in_convo

            if gesture == "WAVE" and _cooled("WAVE"):
                _set_face("happy")
                servo.wave()
                if not quiet:
                    speak("Hi there! I am " + ROBOT_NAME, can_drop=True)

            elif gesture == "THUMBS_UP" and _cooled("THUMBS_UP"):
                _set_face("excited")
                servo.arms_up()
                if not quiet:
                    speak("Thank you! You are awesome!", can_drop=True)

            elif gesture == "PEACE" and _cooled("PEACE"):
                _set_face("excited")
                servo.arm_up("right")
                if not quiet:
                    speak("Peace!", can_drop=True)

            elif gesture == "OPEN_PALM" and _cooled("OPEN_PALM"):
                # friendly acknowledgement — happy face + a little wave
                _set_face("happy")
                servo.wave()

            # HEAD DISABLED FOR NOW — hands only. Re-enable to make Luna
            # turn her head toward a pointed direction.
            # elif gesture == "POINT_LEFT" and _cooled("POINT_LEFT"):
            #     servo.head_look("left")
            #
            # elif gesture == "POINT_RIGHT" and _cooled("POINT_RIGHT"):
            #     servo.head_look("right")

        time.sleep(0.2)


def start_behavior():
    t = threading.Thread(target=behavior_loop, daemon=True)
    t.name = "behavior"
    t.start()
