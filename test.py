"""
test_esp32_cam.py — test ESP32 camera stream + emotion model predictions.

Shows live camera feed with emotion predictions overlaid.
Press Q to quit.
"""

import cv2
import torch
import numpy as np
from models.emotion_mobilenet import EmotionMobileNet
from config import ESP32_STREAM, MODEL_PATH, FRAME_WIDTH, FRAME_HEIGHT

EMOTIONS = ["Angry", "Disgust", "Fear", "Happy", "Neutral", "Surprise"]

face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

# load emotion model
print("[test] Loading emotion model...")
model = EmotionMobileNet(num_classes=6)
model.load_state_dict(torch.load(MODEL_PATH, map_location="cpu"))
model.eval()
print("[test] Model ready")

# connect to ESP32 stream
print(f"[test] Connecting to {ESP32_STREAM}")
cap = cv2.VideoCapture(ESP32_STREAM)

if not cap.isOpened():
    print("[test] ERROR: Could not connect to ESP32 stream")
    print("[test] Make sure ESP32 is powered and on the same WiFi")
    exit()

print("[test] Stream connected — press Q to quit")

while True:
    ret, frame = cap.read()

    if not ret:
        print("[test] Frame grab failed — retrying")
        continue

    frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
    gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    faces = face_cascade.detectMultiScale(
    gray,
    scaleFactor=1.1,    # was 1.2 — smaller = more sensitive
    minNeighbors=3,     # was 5 — lower = detects more faces
    minSize=(30, 30)    # was 40x40 — smaller minimum face size
)

    if len(faces) > 0:
        x, y, w, h = faces[0]

        # draw face box
        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)

        # run emotion model
        face_crop = gray[y:y+h, x:x+w]
        face_48   = cv2.resize(face_crop, (48, 48))
        face_f    = face_48.astype("float32") / 255.0
        tensor    = torch.from_numpy(face_f).unsqueeze(0).unsqueeze(0)

        with torch.no_grad():
            logits = model(tensor)
            probs  = torch.softmax(logits, dim=1)[0]

        # get top prediction
        best_idx   = int(torch.argmax(probs))
        best_label = EMOTIONS[best_idx]
        best_conf  = float(probs[best_idx]) * 100

        # draw emotion label
        label = f"{best_label} {best_conf:.1f}%"
        cv2.putText(frame, label, (x, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        # draw all emotion scores on side
        for i, (emo, prob) in enumerate(zip(EMOTIONS, probs)):
            bar_w = int(float(prob) * 150)
            color = (0, 255, 0) if i == best_idx else (180, 180, 180)
            cv2.rectangle(frame, (5, 10 + i*22),
                          (5 + bar_w, 28 + i*22), color, -1)
            cv2.putText(frame, f"{emo}: {float(prob)*100:.1f}%",
                        (5, 24 + i*22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (255, 255, 255), 1)

        print(f"[test] {best_label} ({best_conf:.1f}%)")

    else:
        cv2.putText(frame, "No face detected", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    cv2.imshow("Luna — ESP32 Cam Test", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
print("[test] Done")