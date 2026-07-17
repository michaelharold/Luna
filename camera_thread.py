"""
camera_thread.py — supports both ESP32 MJPEG stream and local USB/Pi camera.

USE_ESP32_CAM = True  → reads from ESP32 WiFi stream
USE_ESP32_CAM = False → reads from local camera (USB or Pi cam)
"""

import cv2
import threading
import time
import numpy as np
from config import (CAMERA_ID, FRAME_WIDTH, FRAME_HEIGHT,
                    FPS, ESP32_STREAM, USE_ESP32_CAM)
from shared_state import state


def _esp32_loop():
    """Read MJPEG stream from ESP32."""
    print(f"[camera] Connecting to ESP32 stream: {ESP32_STREAM}")

    while True:
        cap = cv2.VideoCapture(ESP32_STREAM)

        if not cap.isOpened():
            print("[camera] ESP32 stream not available — retrying in 3s")
            with state.lock:
                state.camera_ok = False
            time.sleep(3)
            continue

        print("[camera] ESP32 stream connected")
        with state.lock:
            state.camera_ok = True

        while True:
            ret, frame = cap.read()

            if not ret:
                print("[camera] ESP32 stream lost — reconnecting")
                break

            # resize to match expected frame size
            frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))

            with state.lock:
                state.frame = frame

        cap.release()
        time.sleep(2)   # wait before reconnecting


def _open_local_camera():
    """Try the configured camera, then fall back to indices 0-2."""
    tried = []
    for cam_id in [CAMERA_ID, 0, 1, 2]:
        if cam_id in tried:
            continue
        tried.append(cam_id)
        cap = cv2.VideoCapture(cam_id)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
            cap.set(cv2.CAP_PROP_FPS,          FPS)
            cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)
            if cam_id != CAMERA_ID:
                print(f"[camera] Camera {CAMERA_ID} unavailable — using {cam_id}")
            return cap
        cap.release()
    return None


def _local_loop():
    """Read from local USB or Pi camera. Retries forever if no camera —
    Luna keeps running (voice + face) without vision."""
    print(f"[camera] Starting local camera {CAMERA_ID}")
    help_printed = False

    while True:
        cap = _open_local_camera()

        if cap is None:
            if not help_printed:
                help_printed = True
                print("[camera] NO CAMERA FOUND — vision disabled, retrying every 5s")
                print("[camera] See README Troubleshooting: 'Camera not found'")
            with state.lock:
                state.camera_ok = False
            time.sleep(5.0)
            continue

        help_printed = False
        with state.lock:
            state.camera_ok = True
        print(f"[camera] Local camera started {FRAME_WIDTH}x{FRAME_HEIGHT} @ {FPS}fps")

        fail_count = 0
        while True:
            ret, frame = cap.read()

            if not ret:
                fail_count += 1
                if fail_count > 60:   # ~3s of failures → reopen device
                    print("[camera] Camera stopped responding — reopening")
                    break
                time.sleep(0.05)
                continue

            fail_count = 0
            with state.lock:
                state.frame = frame

        cap.release()
        time.sleep(2.0)


def start_camera():
    if USE_ESP32_CAM:
        t = threading.Thread(target=_esp32_loop, daemon=True)
    else:
        t = threading.Thread(target=_local_loop, daemon=True)

    t.name = "camera"
    t.start()