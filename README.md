# Luna 🤖🌙

Luna is a friendly desktop/college robot assistant that runs on a Raspberry Pi (or any Mac/Windows/Linux machine for development). She:

- **Sees** — detects faces and emotions (custom MobileNet + optional DeepFace), tracks you with her eyes
- **Understands gestures** — wave, thumbs-up 👍, peace ✌, open palm, pointing (MediaPipe hands)
- **Listens** — offline speech recognition (Vosk), wake words: *"hello"*, *"luna"*, *"hey luna"*
- **Thinks** — Groq LLM (llama-3.3-70b) with a local knowledge-base fallback that works fully offline
- **Speaks** — pyttsx3 / espeak / macOS `say`, with an animated talking mouth that never gets talked over or skipped
- **Feels** — an expressive animated face (happy, sad, angry, surprised, sleeping, excited ✨, love 💕), in **two selectable styles**
- **Moves** — head-pan + two arm servos (wave, nod, arms up, talking sway)

> Changes to the project are logged in [UPDATES.txt](UPDATES.txt).

---

## Table of contents

1. [Project layout](#1-project-layout)
2. [Prerequisites](#2-prerequisites)
3. [Clone the repo](#3-clone-the-repo)
4. [Required downloads (not stored in git)](#4-required-downloads-not-stored-in-git)
5. [API key setup](#5-api-key-setup)
6. [Create the environment & install requirements](#6-create-the-environment--install-requirements)
   - [macOS](#macos)
   - [Windows](#windows)
   - [Raspberry Pi](#raspberry-pi-4--5-64-bit-os-recommended)
7. [Running Luna](#7-running-luna)
8. [Using Luna](#8-using-luna)
9. [Face styles](#9-face-styles)
10. [Troubleshooting](#10-troubleshooting)
    - [Microphone not found / wrong device / sample rate](#-microphone-not-found)
    - [Speaker not found / no sound](#-speaker-not-found--no-sound)
    - [Camera / webcam not found or wrong device](#-camera-not-found)
    - [No GROQ_API_KEY set](#-no-groq_api_key-set)
    - [Slow on Raspberry Pi](#-slow-on-raspberry-pi)
    - [Other common errors](#-other-common-errors)
11. [Credits](#11-credits)

---

## 1. Project layout

| File | Role |
|---|---|
| `main.py` | Entry point — starts all threads, clean shutdown |
| `config.py` | **All settings live here** (FPS, devices, wake words, servos, face style) |
| `shared_state.py` | Thread-safe shared state between all modules |
| `camera_thread.py` | Camera capture (local USB/Pi cam or ESP32 stream) |
| `vision_module.py` | Face detection + emotion recognition |
| `gesture_module.py` | Hand gesture recognition (MediaPipe) |
| `behavior_engine.py` | Reacts to gestures (face + voice + servos) — never interrupts Luna mid-answer |
| `speech_to_text.py` | Vosk STT, wake words, mic auto-detect, conversation-timeout handling |
| `brain.py` | Groq LLM + offline knowledge base (`data/knowledge.txt`) |
| `text_to_speech.py` | TTS + talking-mouth energy animation, serialized so answers are never dropped |
| `robot_face.py` / `face_renderer.py` | The animated pygame face (2 selectable styles) |
| `servo_module.py` | Servo control (simulation mode when `ENABLE_SERVOS=False`) |
| `models/` | Emotion model architecture + weights *(weights downloaded separately — see §4)* |
| `data/knowledge.txt` | Offline knowledge base used when there's no internet/API key |
| `pi_inst.txt` | Extra Raspberry Pi tuning notes (swap, GPU split, governor) |
| `requirements.txt` | Python dependencies |
| `.env.example` | Template for your local `.env` (never commit the real one) |

---

## 2. Prerequisites

- **Python 3.11** (the pinned dependency versions — torch 2.3.1, tensorflow 2.15.0, mediapipe 0.10.9 — are built/tested against 3.11; newer Pythons may fail to install some of these wheels)
- **git**
- A working **microphone** and **camera** (both optional — Luna degrades gracefully and keeps running without them, see [Troubleshooting](#10-troubleshooting))
- macOS: **Homebrew** (for `portaudio`)
- Windows: **Python launcher** (`py`), installed with the standard python.org installer
- Raspberry Pi: **64-bit Raspberry Pi OS** recommended, Pi 4 or Pi 5

Check your Python version:

```bash
python3 --version        # macOS/Linux
py -3.11 --version        # Windows
```

If you don't have Python 3.11, install it first:

```bash
# macOS
brew install python@3.11

# Windows — download the 3.11 installer from python.org and check
# "Add python.exe to PATH" during install

# Raspberry Pi / Debian
sudo apt update
sudo apt install python3.11 python3.11-venv python3.11-dev -y
```

---

## 3. Clone the repo

```bash
git clone https://github.com/michaelharold/Luna.git
cd Luna
```

(If you were given a zip file or a different remote URL instead, just `cd` into wherever you extracted/cloned it — every step below is relative to the project root.)

---

## 4. Required downloads (not stored in git)

Two files are intentionally **git-ignored** because they're large binary weights that don't belong in version control — download them once, locally:

### 4a. Vosk speech model

```bash
curl -LO https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip
rm vosk-model-small-en-us-0.15.zip
```

This must extract to a folder named exactly `vosk-model-small-en-us-0.15` in the **project root** (matching `VOSK_MODEL_PATH` in `config.py`). Verify:

```bash
ls vosk-model-small-en-us-0.15/    # should show am/, conf/, graph/, ivector/, etc.
```

### 4b. Emotion model weights

`models/emotion_raf_mobilenet_finetuned.pth` (~10 MB) is not in git. Get it from whoever shared this repo with you (or your own backup) and place it at exactly that path:

```bash
ls models/emotion_raf_mobilenet_finetuned.pth
```

Without it Luna still runs — face tracking and eye-follow keep working; only emotion detection is disabled (emotion stays *Neutral*) and a `[vision] Emotion model unavailable …` warning is printed until you add the weights.

---

## 5. API key setup

Copy the template and paste your Groq key (get one free at <https://console.groq.com>):

```bash
cp .env.example .env
# edit .env → GROQ_API_KEY=gsk_your_key_here
```

`.env` is git-ignored — **never** put the key in `config.py` or commit it. No key? Luna still runs fully offline using `data/knowledge.txt` (see [No GROQ_API_KEY set](#-no-groq_api_key-set)).

---

## 6. Create the environment & install requirements

### macOS

```bash
brew install portaudio            # needed by sounddevice
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Notes:
- If `pip install` fails partway on a slow connection, just re-run the same `pip install -r requirements.txt` — pip resumes/skips already-installed packages.
- TTS uses the built-in `say` command automatically if pyttsx3 fails.
- macOS will ask for **Microphone** and **Camera** permission the first time — grant both (System Settings → Privacy & Security).
- Servos run in simulation mode (`ENABLE_SERVOS = False`) — you'll see `[SERVO] ...` prints instead.
- **If your shell also has conda's `(base)` environment active**, run `conda deactivate` *after* `source venv/bin/activate` so the venv's `python`/`pip` win on `PATH`. Verify with `which python3` — it must point inside `venv/bin/`.

### Windows

```powershell
py -3.11 -m venv venv
venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

Notes:
- pyttsx3 uses the built-in SAPI5 voices — no extra install needed.
- If `sounddevice` install fails: `pip install pipwin && pipwin install pyaudio`, then retry.
- Set the key with `setx GROQ_API_KEY "gsk_..."` **or** use the `.env` file (recommended).

### Raspberry Pi (4 / 5, 64-bit OS recommended)

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y portaudio19-dev python3-pyaudio python3-opencv \
    libatlas-base-dev libhdf5-dev espeak espeak-data libespeak-dev

python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

If `mediapipe` fails to install on Pi 4/5, install the Pi-specific wheel instead:

```bash
pip install mediapipe-rpi4 --break-system-packages   # Pi 4
pip install mediapipe-rpi5 --break-system-packages   # Pi 5
```

More Pi-specific tuning (swap size, GPU split, performance governor) is in [pi_inst.txt](pi_inst.txt). Highlights:

- **Pi 4 low on RAM during TensorFlow install/run** — increase swap: edit `/etc/dphys-swapfile`, set `CONF_SWAPSIZE=2048`, then `sudo systemctl restart dphys-swapfile`.
- **More headroom for ML inference** — add `gpu_mem=128` to `/boot/config.txt` (Pi 4) or `/boot/firmware/config.txt` (Pi 5).
- **Performance governor**: `echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor`

**Servos:** wire head-pan → GPIO 17, left arm → GPIO 18, right arm → GPIO 27 (BCM numbering, 50 Hz PWM), then set `ENABLE_SERVOS = True` in `config.py`.

---

## 7. Running Luna

```bash
source venv/bin/activate      # Windows: venv\Scripts\activate
python3 main.py                # Windows: python main.py
```

On first run you should see startup logs for each subsystem (camera, vision model, DeepFace, gesture model, brain/knowledge base, servo, mic stream) followed by the face window opening. Press **Ctrl+C** in the terminal, or close the face window, to shut down cleanly (servos re-center, GPIO releases).

**Sanity check before troubleshooting anything else** — run this once to confirm the environment itself is fine:

```bash
python3 -c "import torch, cv2, mediapipe, pygame, pyttsx3, sounddevice, vosk, groq, sentence_transformers, deepface, tensorflow; print('ALL_OK')"
```

If that doesn't print `ALL_OK`, fix the import error first (usually a missed `pip install -r requirements.txt` step or wrong Python version) before trying to run Luna itself.

---

## 8. Using Luna

| You do | Luna does |
|---|---|
| Say **"hello"** / **"luna"** / **"hey luna"** | Wakes up (a short "Yes?" acknowledgement if you say the wake word alone), conversation mode for 10 s after each exchange |
| Ask a question | Groq LLM answer (or offline knowledge base) spoken aloud — answers are never skipped, even if a gesture happens mid-answer |
| 👋 Wave your hand | Happy face + waves arm + "Hi there!" (silent face-only reaction if you're already mid-conversation, so it won't talk over you) |
| 👍 Thumbs up | Excited face with stars + both arms up + "Thank you!" |
| ✌ Peace sign | Excited face + right arm up + "Peace!" |
| ✋ Open palm | Friendly happy face |
| ☝ Point left/right/up/down | Her eyes follow your finger |
| Say "I love you" / "good job" | Heart-eyes 💕 face with floating hearts |
| Walk away for 30 s | She falls asleep (zzz…) and wakes when you return |
| Conversation window times out (10 s of silence) | A subtle "going to rest" cue plays (soft blink, dimming glow dot) — say a wake word again to resume |

---

## 9. Face styles

Two selectable looks, switchable **live** by pressing **1** or **2** on the face window, or by setting `FACE_STYLE` in `config.py` (persists as the startup default):

- **`1` — Luna classic**: soft purple palette, rounded shapes, organic mouth
- **`2` — Robo**: cyan palette, sharp corners, square sensor-style pupils, equalizer-bar talking mouth (modern robot look)

Switching back to `1` always restores the exact original face — nothing is lost by trying style 2.

---

## 10. Troubleshooting

### 🎤 Microphone not found

Luna prints `[STT] NO MICROPHONE FOUND` but **keeps running** and retries every 5 s. To fix:

```bash
# 1. List all audio devices and their sample rates:
python3 -c "import sounddevice as sd; print(sd.query_devices())"
```

Look for lines with `> ` (default input) and `max_input_channels > 0`. Example output:

```
  0 MacBook Pro Microphone, Core Audio (1 in, 0 out)   48000.0 Hz
  1 USB PnP Sound Device,   Core Audio (1 in, 0 out)   44100.0 Hz
```

```bash
# 2. If the wrong device is picked, set the index in config.py:
AUDIO_INPUT_DEVICE = 1        # the number from the list above
```

- **Linux/Pi** — also check the mic is visible to ALSA: `arecord -l`. If nothing shows, re-seat the USB mic and check `dmesg | tail`.
- **Pi permission issue** — add yourself to the audio group: `sudo usermod -aG audio $USER`, then reboot.
- **macOS** — System Settings → Privacy & Security → Microphone → enable for Terminal (or your IDE).
- **Windows** — Settings → Privacy → Microphone → allow desktop apps.

#### Multiple mics / wrong sample rate

`MIC_SAMPLE_RATE = None` (default) auto-detects the device's native rate and Luna resamples internally to the 16 kHz Vosk needs — any rate works (16k/32k/44.1k/48k).

If recognition sounds "off" or fails, pin it manually:

```bash
# find the default sample rate of device index 1:
python3 -c "import sounddevice as sd; print(sd.query_devices(1)['default_samplerate'])"
```

then in `config.py`:

```python
AUDIO_INPUT_DEVICE = 1
MIC_SAMPLE_RATE    = 48000    # the value printed above
```

#### Mic stream opens but nothing is ever recognised

```bash
# Record 3 seconds and check the file isn't silent/corrupt:
python3 -c "
import sounddevice as sd, soundfile as sf
data = sd.rec(int(3*16000), samplerate=16000, channels=1, dtype='int16')
sd.wait()
sf.write('/tmp/mictest.wav', data, 16000)
print('wrote /tmp/mictest.wav — play it back to confirm audio is present')
"
```
(`pip install soundfile` if you don't have it — it's only needed for this one-off test.) Play `/tmp/mictest.wav` back; if it's silent, the wrong device/gain is selected at the OS level, not a Luna bug.

### 🔊 Speaker not found / no sound

Luna never crashes on missing speakers — she prints the reply text instead.

- **Pi/Linux**: test with `speaker-test -t wav -c 2`. Install espeak if missing: `sudo apt install espeak`. Pick the right output: `sudo raspi-config` → System → Audio (or `alsamixer` → F6 to select the card, check nothing is muted `MM` → press M).
- **macOS**: test with `say hello`. Check output device in System Settings → Sound.
- **Windows**: check the default playback device in Settings → Sound; pyttsx3 uses it automatically.
- HDMI screens on the Pi often steal audio — force the headphone jack: `amixer cset numid=3 1` (or select in raspi-config).

### 📷 Camera not found

Luna prints `[camera] NO CAMERA FOUND`, keeps running (voice still works), tries device indices 0–2 and retries every 5 s.

```bash
# Linux/Pi — list video devices:
ls /dev/video*
# Pi camera module specifically:
libcamera-hello --list-cameras
# quick test that OpenCV can read index 0:
python3 -c "import cv2; c=cv2.VideoCapture(0); print('opened:', c.isOpened())"
```

```bash
# macOS/Windows — try each index until one opens:
python3 -c "
import cv2
for i in range(4):
    c = cv2.VideoCapture(i)
    print(i, 'opened:', c.isOpened())
    c.release()
"
```

- If your camera is at another index, set `CAMERA_ID` in `config.py`.
- **Pi camera module**: enable it via `sudo raspi-config` → Interface Options → Camera, then reboot.
- **macOS**: grant Camera permission to Terminal (Privacy & Security → Camera).
- **Windows**: Settings → Privacy → Camera → allow desktop apps; close any other app (Zoom/Teams) that might be holding the camera open.
- **ESP32 stream**: set `USE_ESP32_CAM = True` and put the stream URL in `ESP32_STREAM` (the ESP32 must be on the same Wi-Fi; test the URL in a browser first).

### 🧠 "No GROQ_API_KEY set"

Luna answers from the local knowledge base only. Create `.env` from `.env.example` and add your key (see [§5](#5-api-key-setup)). Verify it's actually being picked up:

```bash
python3 -c "from config import GROQ_API_KEY; print('key loaded:', bool(GROQ_API_KEY))"
```

If that prints `False`, double-check `.env` is in the project root (same folder as `config.py`) and the line is exactly `GROQ_API_KEY=gsk_...` with no quotes/spaces issues.

### 🐌 Slow on Raspberry Pi

Lower `VISION_FPS`, `GESTURE_FPS`, `RENDER_FPS` in `config.py`; see [pi_inst.txt](pi_inst.txt) for swap/governor tuning. DeepFace's first call after boot is always slow — that's the warm-up, expected.

### Other common errors

| Error | Cause / fix |
|---|---|
| `ModuleNotFoundError: No module named 'torch'` (or any package) | The venv isn't activated, or `pip install -r requirements.txt` didn't finish. Run `which python3` (macOS/Linux) or `where python` (Windows) and confirm it points inside `venv/`. Re-run the install. |
| `[vision] Emotion model unavailable …` warning at startup | You skipped [§4b](#4b-emotion-model-weights) — the weights file isn't downloaded/placed. Luna keeps running with face tracking; emotion stays *Neutral* until you add it. |
| Vosk fails to load / `Model path does not exist` | The Vosk model folder isn't named exactly `vosk-model-small-en-us-0.15` or isn't in the project root — re-check [§4a](#4a-vosk-speech-model). |
| `pygame.error: No available video device` (Pi headless / SSH) | Luna needs a display. Run with a physical monitor attached, or over VNC/X-forwarding, or set `SDL_VIDEODRIVER=dummy` if you only want to test non-visual behavior. |
| Install hangs/fails on `mediapipe` (Raspberry Pi) | Use the Pi-specific wheel — see the [Raspberry Pi setup](#raspberry-pi-4--5-64-bit-os-recommended) section above. |
| `ReferenceError: weakly-referenced object no longer exists` from pyttsx3 | Already handled — `text_to_speech.py` keeps a persistent engine and falls back to `say`/`espeak` automatically. If you still see it, check you're on an unmodified copy of `text_to_speech.py`. |
| Gestures/wave never seem to trigger a spoken reply | Expected if Luna is already mid-answer or in an active conversation window — gestures react with face + servo only in that case so they never talk over you (see [§8](#8-using-luna)). |

---

## 11. Credits

Luna is a Computer Science Department project developed by **Michael Harold Sony, Sreenadhana, and Devadathan**.
