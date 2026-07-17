import cv2
import torch
import threading
import time
import numpy as np

from config import (MODEL_PATH, VISION_FPS, DEEPFACE_EVERY,
                    SAD_CONFIDENCE, EMOTION_HISTORY_LEN)
from shared_state import state
from models.emotion_mobilenet import EmotionMobileNet

# ── PyTorch model ─────────────────────────────────────────────────────────────
EMOTIONS_PT = ["Angry", "Disgust", "Fear", "Happy", "Neutral", "Surprise"]

face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

print("[vision] Loading PyTorch emotion model...")
try:
    pt_model = EmotionMobileNet(num_classes=6)
    pt_model.load_state_dict(torch.load(MODEL_PATH, map_location="cpu"))
    pt_model.eval()
    MODEL_OK = True
    print("[vision] PyTorch model ready")
except Exception as e:
    # Degrade gracefully (same philosophy as the camera/mic): without the
    # weights Luna keeps face tracking + eye-follow, emotion just stays Neutral,
    # instead of crashing the whole app on a missing/corrupt .pth file.
    pt_model = None
    MODEL_OK = False
    print(f"[vision] Emotion model unavailable ({e}) — face tracking still "
          f"works, emotion stays Neutral. See README §4b to add the weights.")

# ── DeepFace (TensorFlow) — handles Sad ──────────────────────────────────────
print("[vision] Loading DeepFace...")
try:
    from deepface import DeepFace
    _dummy = np.zeros((48, 48, 3), dtype=np.uint8)
    try:
        DeepFace.analyze(_dummy, actions=["emotion"],
                         enforce_detection=False, silent=True)
    except Exception:
        pass
    DEEPFACE_OK = True
    print("[vision] DeepFace ready")
except ImportError:
    DEEPFACE_OK = False
    print("[vision] DeepFace not installed — Sad detection disabled")

DEEPFACE_MAP = {
    "angry":   "Angry",   "disgust": "Disgust",
    "fear":    "Fear",    "happy":   "Happy",
    "sad":     "Sad",     "surprise":"Surprise",
    "neutral": "Neutral",
}

_history    = []
_df_counter = 0


def _majority(history):
    if not history:
        return "Neutral"
    return max(set(history), key=history.count)


def _run_pytorch(gray_48):
    face   = gray_48.astype("float32") / 255.0
    tensor = torch.from_numpy(face).unsqueeze(0).unsqueeze(0)
    with torch.no_grad():
        pred = int(torch.argmax(pt_model(tensor)))
    return EMOTIONS_PT[pred]


def _run_deepface(bgr_crop):
    try:
        r = DeepFace.analyze(bgr_crop, actions=["emotion"],
                             enforce_detection=False, silent=True)
        if isinstance(r, list):
            r = r[0]
        dominant = r["dominant_emotion"]
        conf     = r["emotion"].get(dominant, 0.0)
        return DEEPFACE_MAP.get(dominant.lower(), "Neutral"), conf
    except Exception:
        return None


def vision_loop():
    global _df_counter
    sleep_time  = 1.0 / VISION_FPS
    target_size = (48, 48)

    while True:
        t0 = time.monotonic()

        with state.lock:
            frame = state.frame

        if frame is None:
            time.sleep(0.1)
            continue

        gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.2,
            minNeighbors=5,
            minSize=(60, 60),
            flags=cv2.CASCADE_SCALE_IMAGE
        )

        face_detected = len(faces) > 0
        emotion       = "Neutral"

        if face_detected:
            x, y, w, h = faces[0]

            # Face position is always available (drives eye-tracking) even when
            # the emotion model failed to load — emotion just stays Neutral then.
            if MODEL_OK:
                gray_crop  = gray[y:y+h, x:x+w]
                gray_48    = cv2.resize(gray_crop, target_size,
                                        interpolation=cv2.INTER_NEAREST)
                pt_emotion = _run_pytorch(gray_48)

                df_emotion  = None
                _df_counter += 1

                if DEEPFACE_OK and _df_counter >= DEEPFACE_EVERY:
                    _df_counter = 0
                    bgr_crop    = frame[y:y+h, x:x+w]
                    result      = _run_deepface(bgr_crop)
                    if result is not None:
                        df_label, df_conf = result
                        if df_label == "Sad" and df_conf >= SAD_CONFIDENCE:
                            df_emotion = "Sad"
                        elif pt_emotion == "Neutral" and df_label != "Neutral":
                            df_emotion = df_label

                raw = df_emotion if df_emotion else pt_emotion
                _history.append(raw)
                if len(_history) > EMOTION_HISTORY_LEN:
                    _history.pop(0)
                emotion = _majority(_history)

            face_cx = (x + w / 2) / frame.shape[1]
            face_cy = (y + h / 2) / frame.shape[0]

            with state.lock:
                state.emotion       = emotion
                state.face_detected = True
                state.face_x        = face_cx
                state.face_y        = face_cy
        else:
            _history.clear()
            with state.lock:
                state.emotion       = "Neutral"
                state.face_detected = False

        elapsed   = time.monotonic() - t0
        remaining = sleep_time - elapsed
        if remaining > 0:
            time.sleep(remaining)


def start_vision():
    t = threading.Thread(target=vision_loop, daemon=True)
    t.name = "vision"
    t.start()