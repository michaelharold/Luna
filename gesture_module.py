"""
gesture_module.py — detects hand gestures and pointing direction.

Gestures detected:
  WAVE       — hand present + wrist moving horizontally (smile + "hi" + servo wave)
  THUMBS_UP  — thumb up, other fingers folded (excited face + thank-you)
  PEACE      — index + middle up, others folded (excited face + starburst)
  OPEN_PALM  — all five fingers extended and still (friendly acknowledgement)
  POINT_LEFT / POINT_RIGHT / POINT_UP / POINT_DOWN — index finger direction
  HAND       — generic hand visible

All gestures come from the same MediaPipe hand landmarks — no extra models,
no extra CPU cost on the Pi.
"""

import mediapipe as mp
import threading
import time
from config import GESTURE_FPS
from shared_state import state

mp_hands = mp.solutions.hands

hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    model_complexity=0
)

# Wave detection state
_prev_wrist_x  = None
_wave_dx_hist  = []
_WAVE_THRESH   = 0.04    # normalised wrist displacement per frame to count as wave
_WAVE_HIST_LEN = 8       # frames


def _get_landmark(lm_list, idx):
    lm = lm_list[idx]
    return lm.x, lm.y


def _finger_states(lm):
    """Return dict of which fingers are extended.
    A finger counts as extended when its tip is farther from the wrist
    than its PIP joint (scale-invariant, works at any distance)."""
    wrist = lm[0]

    def dist(a):
        return ((a.x - wrist.x) ** 2 + (a.y - wrist.y) ** 2) ** 0.5

    return {
        # thumb: tip vs IP joint
        "thumb":  dist(lm[4])  > dist(lm[3])  * 1.1,
        "index":  dist(lm[8])  > dist(lm[6])  * 1.1,
        "middle": dist(lm[12]) > dist(lm[10]) * 1.1,
        "ring":   dist(lm[16]) > dist(lm[14]) * 1.1,
        "pinky":  dist(lm[20]) > dist(lm[18]) * 1.1,
    }


def _classify(landmarks):
    """Return gesture string or None."""
    global _prev_wrist_x, _wave_dx_hist

    wrist     = landmarks[0]
    index_tip = landmarks[8]
    index_mcp = landmarks[5]

    wrist_x = wrist.x

    # ── Wave detection ──────────────────────────────────────────────────────
    if _prev_wrist_x is not None:
        dx = abs(wrist_x - _prev_wrist_x)
        _wave_dx_hist.append(dx)
        if len(_wave_dx_hist) > _WAVE_HIST_LEN:
            _wave_dx_hist.pop(0)
        if len(_wave_dx_hist) == _WAVE_HIST_LEN:
            avg_dx = sum(_wave_dx_hist) / _WAVE_HIST_LEN
            if avg_dx > _WAVE_THRESH:
                _prev_wrist_x = wrist_x
                return "WAVE"

    _prev_wrist_x = wrist_x

    # ── Static hand poses ───────────────────────────────────────────────────
    fingers  = _finger_states(landmarks)
    n_up     = sum(fingers.values())
    thumb_up = landmarks[4].y < landmarks[2].y   # thumb tip above its base

    # THUMBS_UP — thumb up, all four fingers folded
    if fingers["thumb"] and thumb_up and n_up == 1:
        return "THUMBS_UP"

    # PEACE — index + middle extended, ring + pinky folded
    if (fingers["index"] and fingers["middle"]
            and not fingers["ring"] and not fingers["pinky"]):
        return "PEACE"

    # OPEN_PALM — all five fingers extended
    if n_up == 5:
        return "OPEN_PALM"

    # ── Pointing direction (index finger extended) ──────────────────────────
    # vector from MCP (knuckle) to tip
    vec_x = index_tip.x - index_mcp.x
    vec_y = index_tip.y - index_mcp.y   # y increases downward in image coords
    magnitude = (vec_x**2 + vec_y**2) ** 0.5

    if magnitude > 0.08:   # finger clearly extended
        if abs(vec_x) > abs(vec_y):
            return "POINT_LEFT" if vec_x < 0 else "POINT_RIGHT"
        else:
            return "POINT_UP" if vec_y < 0 else "POINT_DOWN"

    return "HAND"


def gesture_loop():
    while True:
        try:
            _gesture_iteration_loop()
        except Exception as e:
            # never let a bad frame / mediapipe hiccup kill the gesture thread
            print(f"[gesture] loop error (recovering): {e}")
            time.sleep(1.0)


def _gesture_iteration_loop():
    sleep_time = 1.0 / GESTURE_FPS

    while True:
        t0 = time.monotonic()

        with state.lock:
            frame = state.frame

        if frame is None:
            time.sleep(0.1)
            continue

        rgb     = frame[:, :, ::-1]
        results = hands.process(rgb)

        gesture  = None
        look_dir = None

        if results.multi_hand_landmarks:
            landmarks = results.multi_hand_landmarks[0].landmark
            gesture   = _classify(landmarks)

            # Map pointing gestures to look directions for the eyes
            if gesture == "POINT_LEFT":
                look_dir = "left"
            elif gesture == "POINT_RIGHT":
                look_dir = "right"
            elif gesture == "POINT_UP":
                look_dir = "up"
            elif gesture == "POINT_DOWN":
                look_dir = "down"

        with state.lock:
            state.gesture  = gesture
            state.look_dir = look_dir

        elapsed = time.monotonic() - t0
        rem = sleep_time - elapsed
        if rem > 0:
            time.sleep(rem)


def start_gesture():
    t = threading.Thread(target=gesture_loop, daemon=True)
    t.name = "gesture"
    t.start()