"""
behavior_engine.py — reacts to gestures with face state + voice + servos.

Wave       → happy face + "Hi there!" + servo wave
Thumbs up  → excited face (starburst) + "Thank you!" + both arms up
Peace      → excited face (starburst) + "Peace!" + right arm up
Open palm  → happy face (silent friendly acknowledgement)
Point      → eyes follow direction (handled in robot_face via look_dir)

Interrupt rules (order matters — answering ALWAYS wins):
  • Luna speaking or processing an answer  → gestures ignored completely
  • Conversation window active (attentive) → face reaction ONLY — no speech
    (would talk over the user) and no servo motion (the user's natural hand
    movements while talking easily read as gestures; moving arms mid-question
    is distracting and adds mic noise)
  • Fully idle                             → full reaction with speech + servo
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
        try:
            _behavior_step(speak)
        except Exception as e:
            # a reaction error must never kill the behavior thread
            print(f"[behavior] loop error (recovering): {e}")
            time.sleep(1.0)
        time.sleep(0.2)


def _behavior_step(speak):
    with state.lock:
        gesture = state.gesture
        busy    = state.speaking or state.luna_mode in ("processing",
                                                        "speaking")
        in_convo = state.conversation_active

    if busy:
        return

    # In an active conversation the user is (or is about to be) mid-question —
    # their natural hand movements while talking easily read as WAVE/PEACE.
    # React with the FACE only: no speech (would talk over them) and no servo
    # motion (arm noise/motion mid-question is distracting and can leak into
    # the mic). Full reactions only when Luna is fully idle.
    quiet = in_convo

    if gesture == "WAVE" and _cooled("WAVE"):
        _set_face("happy")
        if not quiet:
            servo.wave()
            speak("Hi there! I am " + ROBOT_NAME, can_drop=True)

    elif gesture == "THUMBS_UP" and _cooled("THUMBS_UP"):
        _set_face("excited")
        if not quiet:
            servo.arms_up()
            speak("Thank you! You are awesome!", can_drop=True)

    elif gesture == "PEACE" and _cooled("PEACE"):
        _set_face("excited")
        if not quiet:
            servo.arm_up("right")
            speak("Peace!", can_drop=True)

    elif gesture == "OPEN_PALM" and _cooled("OPEN_PALM"):
        # friendly acknowledgement — happy face + a little wave
        _set_face("happy")
        if not quiet:
            servo.wave()

    # HEAD DISABLED FOR NOW — hands only. Re-enable to make Luna
    # turn her head toward a pointed direction.
    # elif gesture == "POINT_LEFT" and _cooled("POINT_LEFT"):
    #     servo.head_look("left")
    #
    # elif gesture == "POINT_RIGHT" and _cooled("POINT_RIGHT"):
    #     servo.head_look("right")


def start_behavior():
    t = threading.Thread(target=behavior_loop, daemon=True)
    t.name = "behavior"
    t.start()
