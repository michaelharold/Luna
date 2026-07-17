import time
from shared_state import state
from robot_face import RobotFace
from config import SLEEP_AFTER_FRAMES

EMOTION_MAP = {
    "Happy":    "happy",
    "Surprise": "surprised",
    "Angry":    "angry",
    "Disgust":  "angry",
    "Fear":     "surprised",
    "Sad":      "sad",
    "Neutral":  "neutral",
}


def renderer_loop():
    face = RobotFace()

    while True:
        now = time.time()
        with state.lock:
            emotion       = state.emotion
            face_detected = state.face_detected
            speaking      = state.speaking
            listening     = state.listening
            override      = state.face_override
            override_end  = state.face_override_until
            # expire stale overrides
            if override and now > override_end:
                state.face_override = None
                override = None

        # ── Gesture/compliment override (excited / love) wins ────────────
        if override:
            face.set_state(override)

        # ── Sleep when idle ───────────────────────────────────────────────
        elif face.idle_frames > SLEEP_AFTER_FRAMES:
            face.set_state("sleeping")

        # ── Speaking — emotion stays, mouth is driven by audio_energy ────
        elif speaking:
            pass

        # ── Normal emotion from vision ────────────────────────────────────
        else:
            mapped = EMOTION_MAP.get(emotion, "neutral")
            face.set_state(mapped)

        face.draw()
